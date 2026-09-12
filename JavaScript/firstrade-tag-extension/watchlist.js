/* ============================================================================
 * Firstrade 自选股助手 watchlist.js  v6      仅在 /app/watchlist 生效
 *
 * v6 修复（关键）:
 *   ★ 输入框必须位于「添加自选股」弹层 [data-popover-content]/[data-command-root] 内，
 *     彻底拉黑页头全站搜索框 #navigation-symbol-search（placeholder 同为「代号或公司名称」）
 *   ★ 联想项只在当前命令面板作用域内查找，绝不误点页头 combobox 的联想（会跳转页面）
 *   ★ typeInto 增加硬安全阀：目标不在弹层内 → 抛错而不是打字
 *   ★ 等待面板 loading spinner（svg.animate-spin）结束，避免拿到上一次残留联想
 *   ★ 点击失败时用 ArrowDown+Enter 键盘兜底
 *   ★ aria-rowcount 取 main 内最大的 grid，排除底部报价条
 *   + FT_WL_PROBE / FT_WL_TEST_ADD 两个自检入口
 *
 * A) 批量补齐：Sectors_All.json（经桥接） → 逐个「添加自选股」
 *     · 断点续跑（chrome.storage.local）
 *     · 页面内 HUD 进度面板（popup 关掉也能看/暂停/停止）
 *     · 定期自动刷新页面防 DOM 膨胀，刷新后自动续跑
 *     · 多趟收敛 + 精确匹配 + aria-rowcount 校验
 * B) 抓「变更%」快照 → firstrade_watchlist.json
 *     · 手动全量 = 覆盖；自动增量（ftAutoWatchlist）= 合并
 * ==========================================================================*/
(() => {
  if (window.__FT_WATCHLIST_V6__) return;
  window.__FT_WATCHLIST_V6__ = true;

  const LOG = '[FT-WL]';
  const JOB_KEY = 'ftWlJob';
  const MANUAL_KEY = 'ftWlManualList';

  let DEBUG = false;
  let AUTO_WATCHLIST = false;

  /* ---------------- 可调参数（可用 storage.ftWlCfg 覆盖） ---------------- */
  const CFG = {
    perSymbolDelay: 380,      // 每个 symbol 之间基础间隔(ms)
    jitter: 220,              // 随机抖动，避免机械节奏
    typeSettle: 70,
    suggestTimeout: 7000,     // 等联想结果
    verifyTimeout: 3200,      // 等行数增加
    verifyTimeout2: 1800,     // 键盘兜底后的二次校验
    maxRetry: 2,
    maxPasses: 3,             // 整体重跑趟数（自愈漏加）
    reloadEvery: 300,         // 每加 N 个刷新一次页面（0 = 不刷新）
    reopenPanelEvery: 40,     // 每加 N 个关闭再重开弹层，重置面板状态（0 = 不重开）
    consecutiveFailAbort: 8,  // 连续失败次数 → 自动暂停
    checkpointEvery: 10,      // 每 N 个持久化进度
    strictExact: true,        // 只接受精确匹配的联想项
    scrollWait: 180
  };

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const log = (...a) => { if (DEBUG) console.log(LOG, ...a); };
  const isWatchlistPage = () => /\/watchlist/i.test(location.pathname || '');
  const toast = (t) => { try { (window.__FT_TOAST__ || console.log)(t); } catch (e) { } };

  /* ---------------- 通用工具 ---------------- */
  function isVisible(el) {
    if (!el) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    // display:contents 的元素本身没有盒子，交给调用方判断子元素
    if (st.display === 'contents') return true;
    const r = el.getBoundingClientRect();
    return !!(r.width || r.height);
  }

  async function waitFor(fn, timeout = 4000, interval = 100) {
    const t0 = Date.now();
    for (; ;) {
      let v = null;
      try { v = fn(); } catch (e) { v = null; }
      if (v) return v;
      if (Date.now() - t0 > timeout) return null;
      await sleep(interval);
    }
  }

  const normKey = (s) => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');

  function cleanText(el) {
    const t = (el.innerText || el.textContent || '');
    return t.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function symbolFromRowId(rowId) {
    if (!rowId) return '';
    const raw = String(rowId).split('|')[0].trim().toUpperCase();
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(raw)) return '';
    return raw;
  }

  function bg(msg) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (chrome.runtime.lastError) { resolve({ ok: false, error: chrome.runtime.lastError.message }); return; }
          resolve(resp || { ok: false, error: 'no response' });
        });
      } catch (e) { resolve({ ok: false, error: String(e) }); }
    });
  }

  const storeGet = (keys) => new Promise(r => chrome.storage.local.get(keys, r));
  const storeSet = (obj) => new Promise(r => chrome.storage.local.set(obj, r));
  const storeDel = (k) => new Promise(r => chrome.storage.local.remove(k, r));

  /* ==========================================================================
   *                    ★★★ 核心：弹层作用域定位（本次 bug 修复点）★★★
   * ========================================================================*/

  /* 绝对禁止触碰的区域：页头全站搜索、底部报价条、导航 */
  const FORBIDDEN_SCOPE = 'header, #app-header, nav, #app-quote-bar';

  function isForbiddenInput(el) {
    if (!el) return true;
    if (el.id === 'navigation-symbol-search') return true;
    if (el.hasAttribute && el.hasAttribute('data-combobox-input')) return true;
    if (el.closest && el.closest(FORBIDDEN_SCOPE)) return true;
    return false;
  }

  /* 可见的 popover / dialog 容器（bits-ui 会把它挂到 body 末尾） */
  function popoverRoots() {
    return Array.from(document.querySelectorAll(
      '[data-popover-content], [data-dialog-content], [role="dialog"]'
    )).filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE));
  }

  /* 「添加自选股」弹层里的命令面板根节点 */
  function getCommandRoot() {
    const roots = popoverRoots();
    for (let i = roots.length - 1; i >= 0; i--) {   // 后出现的浮层优先
      const cr = roots[i].querySelector('[data-command-root]');
      if (cr && isVisible(cr) && cr.querySelector('input')) return cr;
    }
    // 兜底：全局 data-command-root，但必须不在禁区，且内部含 command-input
    const all = Array.from(document.querySelectorAll('[data-command-root]'))
      .filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE) &&
        (el.querySelector('input#command-input') || el.querySelector('input[data-command-input]')));
    return all.length ? all[all.length - 1] : null;
  }

  /* ★ 只返回弹层内的输入框；找不到就返回 null（绝不退化到页头搜索框） */
  function getCommandInput() {
    const cr = getCommandRoot();
    if (cr) {
      const el = cr.querySelector('input#command-input') ||
        cr.querySelector('input[data-command-input]') ||
        cr.querySelector('input');
      if (el && isVisible(el) && !isForbiddenInput(el)) return el;
    }
    const byId = document.getElementById('command-input');
    if (byId && isVisible(byId) && !isForbiddenInput(byId) &&
      byId.closest('[data-command-root], [data-popover-content]')) return byId;
    return null;
  }

  /* 面板是否还在查询中（那个 animate-spin 的 svg，空闲时 opacity-0） */
  function panelLoading() {
    const cr = getCommandRoot();
    if (!cr) return false;
    const sp = cr.querySelector('svg.animate-spin, [class*="animate-spin"]');
    if (!sp) return false;
    const op = parseFloat(getComputedStyle(sp).opacity || '1');
    return op > 0.05;
  }

  function findAddButton() {
    const btns = Array.from(document.querySelectorAll('button'))
      .filter(b => isVisible(b) && !b.closest(FORBIDDEN_SCOPE));
    let b = btns.find(x => /添加自选股|加入自选|Add\s*(to)?\s*Watchlist|Add\s*Symbol/i.test(cleanText(x)));
    if (b) return b;
    b = btns.find(x => x.getAttribute('aria-haspopup') === 'dialog' && x.hasAttribute('data-popover-trigger'));
    return b || null;
  }

  function groupName() {
    const t = document.querySelector('main [data-select-trigger]') ||
      document.querySelector('[data-select-trigger]');
    return t ? cleanText(t) : '';
  }

  /* 取自选股主表的 aria-rowcount（排除底部报价条 / 取最大的那个） */
  function gridRowCount() {
    const gs = Array.from(document.querySelectorAll('[role="grid"][aria-rowcount]'))
      .filter(g => !g.closest('#app-quote-bar, header, #app-header'));
    let best = null;
    gs.forEach(g => {
      const n = parseInt(g.getAttribute('aria-rowcount'), 10);
      if (Number.isFinite(n) && (best === null || n > best)) best = n;
    });
    return best;
  }

  /* 清掉页头搜索框里可能被污染的残留文字，避免误触发跳转 */
  function cleanNavSearch() {
    const nav = document.getElementById('navigation-symbol-search');
    if (nav && nav.value) {
      try {
        setNativeValue(nav, '');
        nav.blur();
        nav.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Escape', code: 'Escape', keyCode: 27 }));
      } catch (e) { }
      log('已清空页头搜索框残留');
    }
  }

  /* ---------------- 抓 watchlist（symbol + 变更%） ---------------- */
  function scrapeRows(buf) {
    const rows = document.querySelectorAll('[row-id]');
    rows.forEach((row) => {
      if (row.closest('.ag-floating-top, .ag-floating-bottom')) return;
      if (row.closest('#app-quote-bar')) return;
      const sym = symbolFromRowId(row.getAttribute('row-id'));
      if (!sym) return;
      const rec = buf[sym] || (buf[sym] = { symbol: sym });
      row.querySelectorAll('[col-id]').forEach((cell) => {
        const col = cell.getAttribute('col-id');
        if (!col) return;
        const txt = cleanText(cell);
        if (col === 'changePercent') {
          if (txt) rec.change_pct = txt;
          const dv = cell.querySelector('[data-value]');
          if (dv) {
            const n = parseFloat(dv.getAttribute('data-value'));
            if (Number.isFinite(n)) rec.change_pct_num = Math.round(n * 1e6) / 1e6;
          }
        } else if (col === 'last') {
          if (txt) rec.last = txt;
        } else if (col === 'change') {
          if (txt) rec.change_amount = txt;
        }
      });
      rec.updated_at = Date.now() / 1000;
    });
    return buf;
  }

  function scrollState() {
    const vp = document.querySelector('main .ag-body-viewport') ||
      document.querySelector('.ag-body-viewport');
    const useVp = !!(vp && vp.scrollHeight > vp.clientHeight + 4);
    if (useVp) {
      return {
        useVp: true,
        get top() { return vp.scrollTop; },
        set top(v) { vp.scrollTop = v; },
        clientH: vp.clientHeight,
        scrollH: vp.scrollHeight
      };
    }
    const se = document.scrollingElement || document.documentElement;
    return {
      useVp: false,
      get top() { return se.scrollTop; },
      set top(v) { se.scrollTop = v; },
      clientH: se.clientHeight,
      scrollH: se.scrollHeight
    };
  }

  async function collectWatchlist(onProgress) {
    const buf = Object.create(null);
    scrapeRows(buf);

    let s = scrollState();
    const original = s.top;
    s.top = 0;
    await sleep(320);
    scrapeRows(buf);

    let guard = 0, stagnant = 0;
    while (guard++ < 4000) {
      s = scrollState();
      const before = Object.keys(buf).length;
      const atEnd = (s.top + s.clientH >= s.scrollH - 3);
      const step = Math.max(200, s.clientH - 80);
      if (atEnd) {
        await sleep(280);
        scrapeRows(buf);
        break;
      }
      s.top = s.top + step;
      await sleep(CFG.scrollWait);
      scrapeRows(buf);
      const after = Object.keys(buf).length;
      stagnant = (after === before) ? stagnant + 1 : 0;
      if (onProgress && guard % 4 === 0) onProgress(after);
      if (stagnant > 60) break;
    }
    await sleep(150);
    scrapeRows(buf);
    s = scrollState();
    s.top = original;
    if (onProgress) onProgress(Object.keys(buf).length);
    return buf;
  }

  /* ---------------- 输入 & 联想 & 点击 ---------------- */
  function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, 'value') ||
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function sendKey(el, key, keyCode) {
    const opt = { bubbles: true, cancelable: true, key, code: key, keyCode: keyCode, which: keyCode };
    el.dispatchEvent(new KeyboardEvent('keydown', opt));
    el.dispatchEvent(new KeyboardEvent('keyup', opt));
  }

  function pressEscape() {
    const t = getCommandInput() || document.body;
    sendKey(t, 'Escape', 27);
  }

  function fireMouseSeq(el) {
    const r = el.getBoundingClientRect();
    const opt = {
      bubbles: true, cancelable: true, view: window,
      clientX: r.left + Math.max(2, r.width / 2),
      clientY: r.top + Math.max(2, r.height / 2),
      button: 0, buttons: 1, pointerId: 1, isPrimary: true, pointerType: 'mouse'
    };
    try { el.dispatchEvent(new PointerEvent('pointerover', opt)); } catch (e) { }
    try { el.dispatchEvent(new PointerEvent('pointerenter', opt)); } catch (e) { }
    el.dispatchEvent(new MouseEvent('mouseover', opt));
    el.dispatchEvent(new MouseEvent('mousemove', opt));
    try { el.dispatchEvent(new PointerEvent('pointerdown', opt)); } catch (e) { }
    el.dispatchEvent(new MouseEvent('mousedown', opt));
    try { el.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, opt, { buttons: 0 }))); } catch (e) { }
    el.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, opt, { buttons: 0 })));
    el.dispatchEvent(new MouseEvent('click', Object.assign({}, opt, { buttons: 0 })));
  }

  /* 打开「添加自选股」弹层并拿到弹层内输入框；带重试与状态自愈 */
  async function ensureInput() {
    let input = getCommandInput();
    if (input) return input;

    for (let i = 0; i < 3; i++) {
      const btn = findAddButton();
      if (!btn) throw new Error('找不到「添加自选股」按钮');

      // 按钮自称 open 但我们找不到输入框 → 先关掉再重开
      if (btn.getAttribute('data-state') === 'open' || btn.getAttribute('aria-expanded') === 'true') {
        pressEscape();
        await sleep(260);
      }
      fireMouseSeq(btn);
      input = await waitFor(getCommandInput, 4500, 120);
      if (input) { await sleep(180); return input; }

      pressEscape();
      await sleep(420);
    }
    throw new Error('点击「添加自选股」后未出现弹层输入框（DOM 可能已改版）');
  }

  /* ★ 安全阀：只允许往弹层内的输入框打字 */
  function assertSafeInput(input) {
    if (!input) throw new Error('输入框为空');
    if (isForbiddenInput(input)) {
      throw new Error('拒绝写入：命中了页头/报价条搜索框（已阻止误填）');
    }
    if (!input.closest('[data-command-root], [data-popover-content], [role="dialog"]')) {
      throw new Error('拒绝写入：输入框不在「添加自选股」弹层内');
    }
  }

  async function typeInto(input, text) {
    assertSafeInput(input);
    input.focus();
    setNativeValue(input, '');
    await sleep(CFG.typeSettle);
    setNativeValue(input, text);
    input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: text.slice(-1) }));
    await sleep(CFG.typeSettle);
  }

  /* ★ 联想项只在当前命令面板内查找 */
  function listItems() {
    const cr = getCommandRoot();
    if (!cr) return [];
    let items = Array.from(cr.querySelectorAll('[data-item-wrapper][data-value]'));
    if (!items.length) items = Array.from(cr.querySelectorAll('[data-command-item][data-value]'));
    if (!items.length) items = Array.from(cr.querySelectorAll('[role="option"]'));
    return items.filter(w => {
      const child = w.querySelector('[data-command-item], [role="option"]') || w.firstElementChild || w;
      return isVisible(child);
    });
  }

  function itemValue(el) {
    if (!el) return '';
    let v = el.getAttribute('data-value');
    if (v) return v;
    const inner = el.querySelector('[data-value]');
    if (inner) return inner.getAttribute('data-value') || '';
    const sp = el.querySelector('span span, span');
    return sp ? cleanText(sp) : cleanText(el);
  }

  function itemClickable(wrapper) {
    return wrapper.querySelector('[data-command-item]') ||
      wrapper.querySelector('[role="option"]') ||
      wrapper.firstElementChild || wrapper;
  }

  function selectedItem() {
    const cr = getCommandRoot();
    if (!cr) return null;
    return cr.querySelector('[data-command-item][aria-selected="true"], [data-command-item][data-selected="true"], [role="option"][aria-selected="true"]');
  }

  async function waitForSuggestion(target, timeout) {
    const t0 = Date.now();
    const tgt = normKey(target);
    let items = [];
    while (Date.now() - t0 < timeout) {
      if (!panelLoading()) {
        items = listItems();
        const exact = items.find(el => normKey(itemValue(el)) === tgt);
        if (exact) return { el: exact, exact: true, firstValue: itemValue(items[0]) };
        if (items.length && Date.now() - t0 > 1200) {
          // 有结果但没有精确项，再多等一会儿看是否刷新
        }
      }
      await sleep(110);
    }
    items = listItems();
    return {
      el: items[0] || null, exact: false,
      firstValue: items[0] ? itemValue(items[0]) : ''
    };
  }

  async function activateItem(wrapper) {
    fireMouseSeq(itemClickable(wrapper));
    await sleep(170);
  }

  /* 键盘兜底：ArrowDown 把高亮移到目标项，再 Enter */
  async function keyboardSelect(input, wantVal) {
    try { assertSafeInput(input); } catch (e) { return false; }
    const tgt = normKey(wantVal);
    for (let i = 0; i < 10; i++) {
      const sel = selectedItem();
      if (sel && normKey(itemValue(sel)) === tgt) {
        sendKey(input, 'Enter', 13);
        await sleep(180);
        return true;
      }
      sendKey(input, 'ArrowDown', 40);
      await sleep(90);
    }
    return false;
  }

  /* 只在弹层作用域内寻找确认按钮，避免点到页面上的其它按钮 */
  async function clickConfirmIfAny() {
    const roots = popoverRoots();
    if (!roots.length) return false;
    const root = roots[roots.length - 1];
    const btns = Array.from(root.querySelectorAll('button')).filter(isVisible);
    const ok = btns.find(b => /^(确定|确认|添加|保存|完成|Add|Save|Done|OK|Confirm)$/i.test(cleanText(b)));
    if (ok) { fireMouseSeq(ok); await sleep(200); return true; }
    return false;
  }

  async function verifyAdded(before, timeout) {
    if (before === null) { await sleep(500); return 'assumed'; }
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const cur = gridRowCount();
      if (cur !== null && cur > before) return 'added';
      await sleep(140);
    }
    return 'unchanged';
  }

  function candidateForms(sym) {
    const s = String(sym).trim().toUpperCase();
    const out = [];
    if (s.includes('-')) out.push(s.replace(/-/g, '.'));
    out.push(s);
    if (s.includes('.')) out.push(s.replace(/\./g, '-'));
    return Array.from(new Set(out));
  }

  async function addOneSymbol(sym) {
    let lastErr = '';
    for (let attempt = 0; attempt <= CFG.maxRetry; attempt++) {
      for (const cand of candidateForms(sym)) {
        if (job.stop) return { status: 'aborted' };
        try {
          cleanNavSearch();
          const input = await ensureInput();
          const before = gridRowCount();

          await typeInto(input, cand);
          const res = await waitForSuggestion(cand, CFG.suggestTimeout);
          if (!res.el) { lastErr = '无联想结果'; continue; }
          if (CFG.strictExact && !res.exact) {
            lastErr = `无精确匹配(首条=${res.firstValue || '空'})`;
            continue;
          }

          await activateItem(res.el);
          await clickConfirmIfAny();
          let v = await verifyAdded(before, CFG.verifyTimeout);

          if (v === 'unchanged') {
            // 鼠标点击可能被框架忽略 → 键盘兜底再确认一次
            const inp2 = getCommandInput();
            if (inp2 && listItems().length) {
              const ok = await keyboardSelect(inp2, cand);
              if (ok) {
                await clickConfirmIfAny();
                v = await verifyAdded(before, CFG.verifyTimeout2);
              }
            }
          }

          if (v === 'added' || v === 'assumed') return { status: 'added', form: cand, verify: v };
          lastErr = '行数未增加(可能已存在或被拒绝)';
        } catch (e) {
          lastErr = String((e && e.message) || e);
          // 出错时把弹层复位，下一轮重新开
          try { pressEscape(); } catch (_) { }
          await sleep(300);
        }
      }
      await sleep(350 + attempt * 700);
    }
    return { status: 'failed', error: lastErr };
  }

  /* ================= HUD 面板 ================= */
  let hudEl = null;
  function ensureHud() {
    if (hudEl && document.body.contains(hudEl)) return hudEl;
    hudEl = document.createElement('div');
    hudEl.id = 'ft-wl-hud';
    hudEl.innerHTML = `
      <div class="ft-wl-head">
        <span class="ft-wl-title">自选股批量补齐</span>
        <span class="ft-wl-x" title="隐藏面板">✕</span>
      </div>
      <div class="ft-wl-line" id="ft-wl-group">分组: --</div>
      <div class="ft-wl-bar"><i id="ft-wl-bar-i"></i></div>
      <div class="ft-wl-line" id="ft-wl-stat">等待开始</div>
      <div class="ft-wl-line ft-wl-cur" id="ft-wl-cur"></div>
      <div class="ft-wl-btns">
        <button id="ft-wl-pause">暂停</button>
        <button id="ft-wl-stop">停止</button>
        <button id="ft-wl-copy">复制失败</button>
      </div>`;
    document.body.appendChild(hudEl);
    hudEl.querySelector('.ft-wl-x').addEventListener('click', () => { hudEl.style.display = 'none'; });
    hudEl.querySelector('#ft-wl-pause').addEventListener('click', () => togglePause());
    hudEl.querySelector('#ft-wl-stop').addEventListener('click', () => stopJob());
    hudEl.querySelector('#ft-wl-copy').addEventListener('click', () => copyFailed());
    return hudEl;
  }

  function renderHud(extra) {
    const el = ensureHud();
    el.style.display = 'block';
    const total = job.total || 0;
    const done = job.done || 0;
    const pct = total ? Math.min(100, Math.round(done / total * 100)) : 0;
    el.querySelector('#ft-wl-group').textContent = `分组: ${job.group || '--'}｜第 ${job.pass || 1} 趟`;
    el.querySelector('#ft-wl-bar-i').style.width = pct + '%';
    el.querySelector('#ft-wl-stat').textContent =
      `${done}/${total} (${pct}%)  成功 ${job.added}  失败 ${job.failed.length}` +
      (job.paused ? '  ⏸已暂停' : '');
    el.querySelector('#ft-wl-cur').textContent = extra || (job.current ? `当前: ${job.current}` : '');
    el.querySelector('#ft-wl-pause').textContent = job.paused ? '继续' : '暂停';
  }

  function copyFailed() {
    const txt = job.failed.map(f => `${f.symbol}\t${f.error}`).join('\n');
    navigator.clipboard.writeText(txt || '(无失败项)').then(
      () => toast('📋 失败清单已复制'),
      () => console.log(LOG, '失败清单:\n' + txt));
  }

  /* ================= 任务状态机 ================= */
  const job = {
    running: false, paused: false, stop: false,
    group: '', pass: 1, total: 0, done: 0, added: 0,
    failed: [], queue: [], current: '', lastError: '',
    startedAt: 0, sinceReload: 0, sinceReopen: 0
  };

  function markBusy(v) { window.__FT_AUTOMATION__ = !!v; }

  async function persist(autoResume) {
    await storeSet({
      [JOB_KEY]: {
        v: 6, group: job.group, pass: job.pass, total: job.total, done: job.done,
        added: job.added, failed: job.failed, queue: job.queue,
        autoResume: !!autoResume, ts: Date.now()
      }
    });
  }

  function togglePause() { job.paused = !job.paused; renderHud(); }
  function stopJob() { job.stop = true; job.paused = false; renderHud('正在停止…'); }

  async function getSourceSymbols() {
    const r = await bg({ action: 'FT_SECTORS' });
    if (r.ok && r.data && Array.isArray(r.data.symbols) && r.data.symbols.length) {
      return { symbols: r.data.symbols, from: '桥接 /sectors_all' };
    }
    const st = await storeGet([MANUAL_KEY]);
    const manual = st[MANUAL_KEY];
    if (Array.isArray(manual) && manual.length) {
      return { symbols: manual, from: '本地备用清单' };
    }
    throw new Error('拿不到 symbol 源：桥接不可用且未设置备用清单（' + (r.error || '') + '）');
  }

  async function computeDiff() {
    const src = await getSourceSymbols();
    renderHud('正在抓取当前自选股全表…');
    const have = await collectWatchlist(n => renderHud(`已读取 ${n} 只自选股…`));
    const haveSet = new Set(Object.keys(have).map(normKey));
    const missing = src.symbols.filter(s => !haveSet.has(normKey(s)));
    return { srcFrom: src.from, srcCount: src.symbols.length, haveCount: Object.keys(have).length, missing };
  }

  async function startJob() {
    if (!isWatchlistPage()) return { ok: false, error: '当前不在 /app/watchlist 页面' };
    if (job.running) return { ok: false, error: '任务已在运行中' };
    if (!findAddButton()) return { ok: false, error: '找不到「添加自选股」按钮，请确认页面已加载完成' };

    job.running = true; job.paused = false; job.stop = false;
    job.group = groupName(); job.pass = 1; job.done = 0; job.added = 0;
    job.failed = []; job.current = ''; job.startedAt = Date.now();
    job.sinceReload = 0; job.sinceReopen = 0;
    markBusy(true);
    cleanNavSearch();
    ensureHud();

    let d;
    try { d = await computeDiff(); }
    catch (e) {
      job.running = false; markBusy(false);
      renderHud('❌ ' + e.message);
      return { ok: false, error: String(e.message || e) };
    }

    job.queue = d.missing.slice();
    job.total = job.queue.length;
    renderHud(`来源:${d.srcFrom} 共${d.srcCount}｜已有${d.haveCount}｜待加${job.total}`);
    if (!job.total) {
      job.running = false; markBusy(false);
      await storeDel(JOB_KEY);
      toast('✅ 自选股已是最新，无需补齐');
      return { ok: true, total: 0, message: '无需补齐' };
    }

    // 出发前做一次「输入框定位自检」，定位错了立刻失败，绝不乱打字
    try {
      const inp = await ensureInput();
      assertSafeInput(inp);
      log('自检通过，输入框 =', inp.id || inp.placeholder);
    } catch (e) {
      job.running = false; markBusy(false);
      renderHud('❌ 输入框自检失败: ' + e.message);
      return { ok: false, error: '输入框自检失败: ' + String(e.message || e) };
    }

    await persist(true);
    runLoop();      // 不 await：后台跑，popup 可以关
    return { ok: true, total: job.total, group: job.group, srcFrom: d.srcFrom };
  }

  async function resumeJob(saved) {
    job.running = true; job.paused = false; job.stop = false;
    job.group = saved.group; job.pass = saved.pass || 1;
    job.queue = saved.queue || []; job.total = saved.total || job.queue.length;
    job.done = saved.done || 0; job.added = saved.added || 0;
    job.failed = saved.failed || []; job.sinceReload = 0; job.sinceReopen = 0;
    markBusy(true);
    cleanNavSearch();
    ensureHud();
    renderHud('已从上次进度续跑');
    runLoop();
  }

  async function runLoop() {
    let consecutiveFail = 0;

    while (job.queue.length && !job.stop) {
      while (job.paused && !job.stop) { renderHud(); await sleep(400); }
      if (job.stop) break;

      // 分组被改动 → 立即停手，避免加错分组
      const g = groupName();
      if (g && job.group && g !== job.group) {
        job.paused = true;
        renderHud(`⚠ 分组已从「${job.group}」变为「${g}」，已暂停`);
        await sleep(1200);
        continue;
      }

      const sym = job.queue[0];
      job.current = sym;
      renderHud();

      const r = await addOneSymbol(sym);
      if (r.status === 'aborted') break;

      job.queue.shift();
      job.done++;
      job.sinceReload++;
      job.sinceReopen++;

      if (r.status === 'added') {
        job.added++;
        consecutiveFail = 0;
      } else {
        job.failed.push({ symbol: sym, error: r.error || '未知' });
        job.lastError = r.error || '';
        consecutiveFail++;
      }
      renderHud();

      if (job.done % CFG.checkpointEvery === 0) await persist(true);

      if (consecutiveFail >= CFG.consecutiveFailAbort) {
        job.paused = true;
        consecutiveFail = 0;
        renderHud(`⚠ 连续失败过多（最后: ${job.lastError}），已自动暂停，请人工检查`);
        await persist(true);
      }

      // 周期性关闭再重开弹层，重置命令面板内部状态
      if (CFG.reopenPanelEvery > 0 && job.sinceReopen >= CFG.reopenPanelEvery) {
        job.sinceReopen = 0;
        try { pressEscape(); } catch (e) { }
        await sleep(450);
      }

      // 定期刷新页面，防止 ag-Grid DOM 膨胀拖慢/卡死
      if (CFG.reloadEvery > 0 && job.sinceReload >= CFG.reloadEvery && job.queue.length) {
        renderHud('页面即将刷新以释放内存，随后自动续跑…');
        await persist(true);
        await sleep(900);
        location.reload();
        return;
      }

      await sleep(CFG.perSymbolDelay + Math.random() * CFG.jitter);
    }

    // ---- 本趟结束：重新比对，看是否需要下一趟（自愈漏加） ----
    try { pressEscape(); } catch (e) { }
    cleanNavSearch();

    if (!job.stop && job.pass < CFG.maxPasses) {
      renderHud('本趟结束，正在复核是否有漏加…');
      try {
        const d = await computeDiff();
        if (d.missing.length) {
          job.pass++;
          job.queue = d.missing.slice();
          job.total = job.done + job.queue.length;
          job.sinceReload = 0;
          await persist(true);
          renderHud(`第 ${job.pass} 趟：仍缺 ${job.queue.length} 只`);
          return runLoop();
        }
      } catch (e) { log('复核失败', e); }
    }

    job.running = false;
    job.current = '';
    markBusy(false);
    await persist(false);
    renderHud(job.stop ? '⏹ 已手动停止' : `✅ 完成：成功 ${job.added}，失败 ${job.failed.length}`);
    toast(job.stop ? '⏹ 自选股补齐已停止' : `✅ 自选股补齐完成，成功 ${job.added} / 失败 ${job.failed.length}`);

    // 顺手把最新的「变更%」快照落一次盘
    if (!job.stop) { try { await fullScanQuotes(true); } catch (e) { } }
  }

  /* ================= 变更% 快照 ================= */
  async function fullScanQuotes(silent) {
    if (!isWatchlistPage()) return { ok: false, error: '当前不在 /app/watchlist 页面' };
    if (!silent) { ensureHud(); renderHud('正在全量抓取「变更%」…'); }
    const buf = await collectWatchlist(n => { if (!silent) renderHud(`已抓 ${n} 只行情…`); });
    const n = Object.keys(buf).length;
    if (!n) return { ok: false, error: '未抓到任何行（页面是否已加载？）' };
    const resp = await bg({ action: 'FT_SYNC_WATCHLIST', payload: buf, overwrite: true });
    if (!silent) renderHud(resp.ok ? `✅ 已覆盖写入 ${n} 只行情` : ('❌ 写入失败: ' + resp.error));
    if (!silent) toast(resp.ok ? `✅ 已保存 ${n} 只自选股「变更%」` : `❌ 写入失败`);
    return { ok: !!resp.ok, count: n, server: resp };
  }

  let autoTimer = null;
  function autoTickSoon(delay = 2500) {
    if (!AUTO_WATCHLIST) return;
    clearTimeout(autoTimer);
    autoTimer = setTimeout(async () => {
      if (!AUTO_WATCHLIST || !isWatchlistPage() || job.running) return;
      const buf = scrapeRows(Object.create(null));
      if (!Object.keys(buf).length) return;
      const r = await bg({ action: 'FT_SYNC_WATCHLIST', payload: buf, overwrite: false });
      log('自动增量同步自选股', Object.keys(buf).length, r.ok ? 'ok' : r.error);
    }, delay);
  }

  /* ================= 设置 & 引导 ================= */
  function loadSettings() {
    chrome.storage.local.get(['ftDebug', 'ftAutoWatchlist', 'ftWlCfg'], (res) => {
      DEBUG = !!res.ftDebug;
      AUTO_WATCHLIST = res.ftAutoWatchlist === true;
      if (res.ftWlCfg && typeof res.ftWlCfg === 'object') Object.assign(CFG, res.ftWlCfg);
      log('设置: AUTO_WATCHLIST =', AUTO_WATCHLIST);
    });
  }
  chrome.storage.onChanged.addListener((c, area) => {
    if (area === 'local' && (c.ftDebug || c.ftAutoWatchlist || c.ftWlCfg)) loadSettings();
  });

  async function bootstrap() {
    loadSettings();
    if (!isWatchlistPage()) return;

    await waitFor(() => (document.querySelector('.ag-root') && findAddButton()), 25000, 400);

    const st = await storeGet([JOB_KEY]);
    const saved = st[JOB_KEY];
    if (saved && saved.autoResume && Array.isArray(saved.queue) && saved.queue.length) {
      ensureHud();
      job.group = saved.group; job.total = saved.total; job.done = saved.done;
      job.added = saved.added; job.failed = saved.failed || []; job.pass = saved.pass || 1;
      const g = groupName();
      if (g && saved.group && g !== saved.group) {
        renderHud(`⚠ 检测到未完成任务，但当前分组「${g}」≠ 任务分组「${saved.group}」，未自动续跑`);
        return;
      }
      for (let i = 5; i > 0; i--) {
        renderHud(`检测到未完成任务（剩 ${saved.queue.length} 只），${i} 秒后自动续跑…点「停止」可取消`);
        await sleep(1000);
        if (job.stop) {
          await storeSet({ [JOB_KEY]: Object.assign({}, saved, { autoResume: false }) });
          renderHud('⏹ 已取消续跑');
          return;
        }
      }
      resumeJob(saved);
      return;
    }
    autoTickSoon(4000);
  }

  document.addEventListener('scroll', () => autoTickSoon(3000), true);
  setInterval(() => { if (!job.running) autoTickSoon(1500); }, 60000);

  /* ================= 与 popup 通信 ================= */
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || !msg.action || !String(msg.action).startsWith('FT_WL_')) return;

    if (msg.action === 'FT_WL_STATUS') {
      sendResponse({
        ok: true, page: isWatchlistPage(), path: location.pathname,
        group: groupName(), gridRows: gridRowCount(),
        auto: AUTO_WATCHLIST,
        running: job.running, paused: job.paused, pass: job.pass,
        total: job.total, done: job.done, added: job.added,
        failed: job.failed.length, lastError: job.lastError
      });
      return;
    }

    /* 🔬 元素探测：以后再出定位问题，一键看清抓到了谁 */
    if (msg.action === 'FT_WL_PROBE') {
      (async () => {
        const btn = findAddButton();
        let info = {
          ok: true,
          addBtn: btn ? `${cleanText(btn).slice(0, 20)} (id=${btn.id || '-'}, state=${btn.getAttribute('data-state') || '-'})` : '未找到',
          popover: popoverRoots().length,
          input: '未打开/未找到',
          items: 0, itemSample: [],
          rows: gridRowCount(),
          group: groupName()
        };
        try {
          const inp = await ensureInput();
          info.input = `id=${inp.id || '-'} placeholder=${inp.placeholder || '-'} inPopover=${!!inp.closest('[data-popover-content]')} forbidden=${isForbiddenInput(inp)}`;
          await typeInto(inp, msg.symbol ? String(msg.symbol).toUpperCase() : 'LIN');
          const res = await waitForSuggestion(msg.symbol || 'LIN', 5000);
          const items = listItems();
          info.items = items.length;
          info.itemSample = items.slice(0, 5).map(itemValue);
          info.exact = res.exact;
          setNativeValue(inp, '');
        } catch (e) {
          info.error = String(e.message || e);
        }
        sendResponse(info);
      })();
      return true;
    }

    /* 🧪 只添加一只，用来验证链路 */
    if (msg.action === 'FT_WL_TEST_ADD') {
      const sym = String(msg.symbol || '').trim().toUpperCase();
      if (!sym) { sendResponse({ ok: false, error: '未提供 symbol' }); return; }
      ensureHud(); renderHud('测试添加 ' + sym + ' …');
      addOneSymbol(sym)
        .then(r => { renderHud('测试结果: ' + JSON.stringify(r)); sendResponse({ ok: true, result: r }); })
        .catch(e => sendResponse({ ok: false, error: String(e.message || e) }));
      return true;
    }

    if (msg.action === 'FT_WL_DIFF') {
      ensureHud();
      computeDiff()
        .then(d => sendResponse({
          ok: true, srcFrom: d.srcFrom, srcCount: d.srcCount,
          haveCount: d.haveCount, missing: d.missing.length,
          sample: d.missing.slice(0, 20), group: groupName()
        }))
        .catch(e => sendResponse({ ok: false, error: String(e.message || e) }));
      return true;
    }

    if (msg.action === 'FT_WL_START') {
      startJob().then(r => sendResponse(r)).catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }

    if (msg.action === 'FT_WL_PAUSE') { togglePause(); sendResponse({ ok: true, paused: job.paused }); return; }
    if (msg.action === 'FT_WL_STOP') { stopJob(); sendResponse({ ok: true }); return; }
    if (msg.action === 'FT_WL_FAILED') { sendResponse({ ok: true, list: job.failed }); return; }
    if (msg.action === 'FT_WL_HUD') { ensureHud().style.display = 'block'; renderHud(); sendResponse({ ok: true }); return; }

    if (msg.action === 'FT_WL_SCAN_QUOTES') {
      fullScanQuotes(false).then(r => sendResponse(r)).catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }
  });

  bootstrap();
  console.log(LOG, `watchlist.js v6 就绪（isWatchlist=${isWatchlistPage()}）`);
})();