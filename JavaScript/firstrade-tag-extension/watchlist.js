/* ============================================================================
 * Firstrade 自选股助手 watchlist.js  v8      仅在 /app/watchlist 生效
 *
 * v8 变更:
 *   ★ 新增「清空当前分组」能力（逐行 三点菜单 → 删除）
 *        - 只删最顶行，规避 ag-Grid 虚拟滚动
 *        - 点击三级兜底（鼠标序列 / el.click / 键盘 ArrowDown+Enter）
 *        - 自动处理二次确认弹窗
 *        - 删除前自动全表备份到 storage.ftWlClearBackup（可复制）
 *        - 每 400 只刷新页面并断点续跑；失败行跳过不死循环
 *   ★ 三步合一 pipeline：清空 → 比对差集 → 批量添加（一个按钮）
 *   ★ HUD 支持 phase(clear/diff/add) + ETA，清空阶段红色警示
 *
 * v7 保留：数据源可切换(earnings/sectors/manual)、job/scan 双模式 HUD、互斥锁
 * v6 保留：弹层作用域定位、拉黑页头搜索框、loading 等待、键盘兜底
 * ==========================================================================*/
(() => {
  if (window.__FT_WATCHLIST_V8__) return;
  window.__FT_WATCHLIST_V8__ = true;

  const LOG = '[FT-WL]';
  const JOB_KEY = 'ftWlJob';
  const MANUAL_KEY = 'ftWlManualList';
  const BACKUP_KEY = 'ftWlClearBackup';

  let DEBUG = false;
  let AUTO_WATCHLIST = false;

  /* ---------------- 数据源设置（popup 可改） ---------------- */
  const SRC = { mode: 'earnings', back: 1, ahead: 0 };
  const SRC_LABEL = { earnings: '财报日历', sectors: 'Sectors_All', manual: '本地清单' };

  /* ---------------- 可调参数（可用 storage.ftWlCfg 覆盖） ---------------- */
  const CFG = {
    /* 添加相关 */
    perSymbolDelay: 380,
    jitter: 220,
    typeSettle: 70,
    suggestTimeout: 7000,
    verifyTimeout: 3200,
    verifyTimeout2: 1800,
    maxRetry: 2,
    maxPasses: 3,
    reloadEvery: 300,
    reopenPanelEvery: 40,
    consecutiveFailAbort: 8,
    checkpointEvery: 10,
    strictExact: true,
    scrollWait: 180,
    /* ★ 清空相关 */
    clearDelay: 180,
    clearJitter: 140,
    clearScrollWait: 220,
    menuTimeout: 2400,
    removeVerifyTimeout: 2400,
    removeVerifyTimeout2: 1600,
    clearFailAbort: 6,
    clearReloadEvery: 400,
    clearCountdown: 5
  };
  let RUN = Object.assign({}, CFG);          // 本次任务实际生效参数

  function prepareRun(total) {
    const keep = { clearDelay: RUN.clearDelay, clearJitter: RUN.clearJitter };
    RUN = Object.assign({}, CFG, keep);
    if (total > 0 && total <= 30) {          // 小清单不必刷新页面、少跑一趟
      RUN.reloadEvery = 0;
      RUN.maxPasses = Math.min(RUN.maxPasses, 2);
    }
  }

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const log = (...a) => { if (DEBUG) console.log(LOG, ...a); };
  const isWatchlistPage = () => /\/watchlist/i.test(location.pathname || '');
  const toast = (t) => { try { (window.__FT_TOAST__ || console.log)(t); } catch (e) { } };

  /* ---------------- 通用工具 ---------------- */
  function isVisible(el) {
    if (!el) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
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
   *                        弹层作用域定位（v6 修复保留）
   * ========================================================================*/
  const FORBIDDEN_SCOPE = 'header, #app-header, nav, #app-quote-bar';

  function isForbiddenInput(el) {
    if (!el) return true;
    if (el.id === 'navigation-symbol-search') return true;
    if (el.hasAttribute && el.hasAttribute('data-combobox-input')) return true;
    if (el.closest && el.closest(FORBIDDEN_SCOPE)) return true;
    return false;
  }

  function popoverRoots() {
    return Array.from(document.querySelectorAll(
      '[data-popover-content], [data-dialog-content], [role="dialog"]'
    )).filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE));
  }

  function getCommandRoot() {
    const roots = popoverRoots();
    for (let i = roots.length - 1; i >= 0; i--) {
      const cr = roots[i].querySelector('[data-command-root]');
      if (cr && isVisible(cr) && cr.querySelector('input')) return cr;
    }
    const all = Array.from(document.querySelectorAll('[data-command-root]'))
      .filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE) &&
        (el.querySelector('input#command-input') || el.querySelector('input[data-command-input]')));
    return all.length ? all[all.length - 1] : null;
  }

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

  /* 表内数据行数（aria-rowcount 含表头行） */
  function dataRowsTotal() {
    const n = gridRowCount();
    if (n === null) return null;
    return Math.max(0, n - 1);
  }

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
        }
      });
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
      if (scanState.abort || job.stop) break;      // ★ 支持中止
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
      await sleep(RUN.scrollWait || CFG.scrollWait);
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

  async function ensureInput() {
    let input = getCommandInput();
    if (input) return input;

    for (let i = 0; i < 3; i++) {
      const btn = findAddButton();
      if (!btn) throw new Error('找不到「添加自选股」按钮');

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
    await sleep(RUN.typeSettle);
    setNativeValue(input, text);
    input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: text.slice(-1) }));
    await sleep(RUN.typeSettle);
  }

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
    for (let attempt = 0; attempt <= RUN.maxRetry; attempt++) {
      for (const cand of candidateForms(sym)) {
        if (job.stop) return { status: 'aborted' };
        try {
          cleanNavSearch();
          const input = await ensureInput();
          const before = gridRowCount();

          await typeInto(input, cand);
          const res = await waitForSuggestion(cand, RUN.suggestTimeout);
          if (!res.el) { lastErr = '无联想结果'; continue; }
          if (RUN.strictExact && !res.exact) {
            lastErr = `无精确匹配(首条=${res.firstValue || '空'})`;
            continue;
          }

          await activateItem(res.el);
          await clickConfirmIfAny();
          let v = await verifyAdded(before, RUN.verifyTimeout);

          if (v === 'unchanged') {
            const inp2 = getCommandInput();
            if (inp2 && listItems().length) {
              const ok = await keyboardSelect(inp2, cand);
              if (ok) {
                await clickConfirmIfAny();
                v = await verifyAdded(before, RUN.verifyTimeout2);
              }
            }
          }

          if (v === 'added' || v === 'assumed') return { status: 'added', form: cand, verify: v };
          lastErr = '行数未增加(可能已存在或被拒绝)';
        } catch (e) {
          lastErr = String((e && e.message) || e);
          try { pressEscape(); } catch (_) { }
          await sleep(300);
        }
      }
      await sleep(350 + attempt * 700);
    }
    return { status: 'failed', error: lastErr };
  }

  /* ==========================================================================
   *                    ★ 清空当前分组（逐行 三点菜单 → 删除）
   * ========================================================================*/
  function rowMenuButton(row) {
    return row.querySelector('[col-id="actions"] button[aria-haspopup="menu"]')
      || row.querySelector('button[aria-haspopup="menu"][data-dropdown-menu-trigger]')
      || row.querySelector('button[aria-haspopup="menu"]')
      || row.querySelector('[col-id="actions"] button')
      || null;
  }

  /* 只取「最顶部」的那一行，规避虚拟滚动 */
  function firstDeletableRow(skip) {
    const rows = Array.from(document.querySelectorAll('[row-id]'))
      .filter(r => !r.closest('.ag-floating-top, .ag-floating-bottom, #app-quote-bar, header, #app-header'));
    let best = null, bestIdx = Infinity;
    for (const row of rows) {
      const rowId = row.getAttribute('row-id');
      const sym = symbolFromRowId(rowId);
      if (!sym) continue;
      if (skip && skip.has(rowId)) continue;
      const btn = rowMenuButton(row);
      if (!btn || !isVisible(btn)) continue;
      const idx = parseInt(row.getAttribute('aria-rowindex'), 10);
      const k = Number.isFinite(idx) ? idx : 99999;
      if (k < bestIdx) { bestIdx = k; best = { row, rowId, sym, btn }; }
    }
    return best;
  }

  function menuRoots() {
    return Array.from(document.querySelectorAll('[data-dropdown-menu-content], [role="menu"]'))
      .filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE));
  }

  function findRemoveMenuItem() {
    const roots = menuRoots();
    for (let i = roots.length - 1; i >= 0; i--) {
      const items = Array.from(roots[i].querySelectorAll('[role="menuitem"], [data-dropdown-menu-item]'))
        .filter(isVisible);
      const hit = items.find(x =>
        /watchlist-remove/i.test(x.id || '') ||
        /^(删除|移除|移除自选|删除自选|Remove|Remove from watchlist|Delete)$/i.test(cleanText(x)));
      if (hit) return hit;
    }
    return null;
  }

  function closeMenus() {
    const roots = menuRoots();
    if (roots.length) sendKey(roots[roots.length - 1], 'Escape', 27);
    sendKey(document.body, 'Escape', 27);
  }

  /* 二次确认弹窗：只认精确文案，避免误点 */
  async function clickDangerConfirm() {
    const dlgs = Array.from(document.querySelectorAll(
      '[role="dialog"], [role="alertdialog"], [data-dialog-content], [data-alert-dialog-content]'
    )).filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE) && !el.querySelector('[data-command-root]'));
    if (!dlgs.length) return false;
    const root = dlgs[dlgs.length - 1];
    const btns = Array.from(root.querySelectorAll('button')).filter(isVisible);
    const ok = btns.find(b => /^(删除|移除|确定|确认|是|Remove|Delete|Confirm|Yes|OK)$/i.test(cleanText(b)));
    if (ok) { fireMouseSeq(ok); await sleep(240); return true; }
    return false;
  }

  function rowExists(rowId) {
    const rows = document.querySelectorAll('[row-id]');
    for (const r of rows) if (r.getAttribute('row-id') === rowId) return true;
    return false;
  }

  async function waitRowGone(rowId, before, timeout) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const cur = gridRowCount();
      if (before !== null && cur !== null && cur < before) return true;
      if (!rowExists(rowId)) return true;
      await sleep(120);
    }
    return false;
  }

  /* 键盘兜底：在菜单里 ArrowDown 到「删除」再 Enter */
  async function keyboardRemove() {
    const roots = menuRoots();
    if (!roots.length) return false;
    const root = roots[roots.length - 1];
    for (let i = 0; i < 12; i++) {
      const hl = root.querySelector('[data-highlighted], [data-highlighted="true"], [aria-selected="true"]');
      if (hl && (/watchlist-remove/i.test(hl.id || '') || /删除|移除|Remove|Delete/i.test(cleanText(hl)))) {
        sendKey(root, 'Enter', 13);
        await sleep(220);
        return true;
      }
      sendKey(root, 'ArrowDown', 40);
      await sleep(80);
    }
    return false;
  }

  async function deleteTopRow(skip) {
    /* 保证目标行在可视区 */
    const s = scrollState();
    if (s.top > 2) { s.top = 0; await sleep(RUN.clearScrollWait); }

    let tgt = firstDeletableRow(skip);
    if (!tgt) { await sleep(450); tgt = firstDeletableRow(skip); }
    if (!tgt) return { status: 'empty' };

    const { btn, sym, rowId } = tgt;
    const before = gridRowCount();

    closeMenus();
    await sleep(90);

    /* 打开三点菜单（含键盘兜底） */
    let item = null;
    for (let attempt = 0; attempt < 2 && !item; attempt++) {
      fireMouseSeq(btn);
      item = await waitFor(findRemoveMenuItem, RUN.menuTimeout, 90);
      if (!item) {
        try { btn.focus(); sendKey(btn, 'Enter', 13); } catch (e) { }
        item = await waitFor(findRemoveMenuItem, 1200, 90);
      }
      if (!item) { closeMenus(); await sleep(320); }
    }
    if (!item) {
      closeMenus();
      return { status: 'failed', symbol: sym, rowId, error: '未弹出操作菜单/未找到「删除」项' };
    }

    /* 点击删除：鼠标序列 → el.click → 键盘 */
    fireMouseSeq(item);
    try { item.click(); } catch (e) { }
    await sleep(140);
    await clickDangerConfirm();

    let gone = await waitRowGone(rowId, before, RUN.removeVerifyTimeout);
    if (!gone) {
      if (findRemoveMenuItem()) {
        await keyboardRemove();
        await clickDangerConfirm();
        gone = await waitRowGone(rowId, before, RUN.removeVerifyTimeout2);
      }
    }
    closeMenus();
    return gone
      ? { status: 'removed', symbol: sym, rowId }
      : { status: 'failed', symbol: sym, rowId, error: '点了删除但行未消失' };
  }

  async function backupCurrentList() {
    renderHud('正在备份当前分组清单（删除前保险）…');
    const buf = await collectWatchlist(n => renderHud(`备份中：已读取 ${n} 只…`));
    const symbols = Object.keys(buf);
    await storeSet({
      [BACKUP_KEY]: {
        group: groupName(), ts: Date.now(), count: symbols.length,
        src: SRC.mode, symbols
      }
    });
    console.log(LOG, `已备份 ${symbols.length} 只到 storage.${BACKUP_KEY}`, symbols);
    return symbols;
  }

  async function runClearPhase() {
    job.phase = 'clear';
    job.clearStartedAt = job.clearStartedAt || Date.now();
    job.clearTotal = (job.cleared || 0) + (dataRowsTotal() || 0);

    /* 5 秒倒计时，给「停止」留后路 */
    for (let i = RUN.clearCountdown; i > 0 && !job.stop; i--) {
      renderHud(`⚠️ ${i} 秒后开始删除「${job.group || '当前分组'}」内 ${job.clearTotal} 只…点「停止」可取消`);
      await sleep(1000);
    }
    if (job.stop) return 'stopped';

    let consec = 0, guard = 0;
    while (!job.stop && guard++ < 6000) {
      while (job.paused && !job.stop) { renderHud(); await sleep(400); }
      if (job.stop) break;

      const grp = groupName();
      if (grp && job.group && grp !== job.group) {
        job.paused = true;
        renderHud(`⚠ 分组已从「${job.group}」变为「${grp}」，已暂停（防误删）`);
        await sleep(1200);
        continue;
      }

      const left = dataRowsTotal();
      if (left === 0) break;

      const r = await deleteTopRow(job.clearSkip);
      if (r.status === 'empty') break;

      if (r.status === 'removed') {
        job.cleared++;
        job.current = r.symbol;
        consec = 0;
      } else {
        consec++;
        if (r.rowId) job.clearSkip.add(r.rowId);
        job.clearFailed.push({ symbol: r.symbol || '?', error: r.error || '未知' });
        job.lastError = r.error || '';
        if (consec >= RUN.clearFailAbort) {
          job.paused = true; consec = 0;
          renderHud(`⚠ 连续删除失败（${job.lastError}），已自动暂停，请人工检查`);
          await persist(true);
        }
      }
      renderHud();

      if (job.cleared > 0 && job.cleared % RUN.checkpointEvery === 0) await persist(true);

      if (RUN.clearReloadEvery > 0 && job.cleared > 0 && job.cleared % RUN.clearReloadEvery === 0
        && (dataRowsTotal() || 0) > 0) {
        renderHud('页面即将刷新以释放内存，随后自动继续清空…');
        await persist(true);
        await sleep(900);
        location.reload();
        return 'reload';
      }

      await sleep(RUN.clearDelay + Math.random() * RUN.clearJitter);
    }

    closeMenus();
    job.clearSkip.clear();
    return job.stop ? 'stopped' : 'done';
  }

  /* ================= HUD 面板（双模式 + 阶段） ================= */
  let hudEl = null;
  let hudMode = 'job';        // 'job' | 'scan'
  const HUD_TITLE = {
    job: '自选股一键补齐',
    scan: '自选股行情抓取',
    diff: '差集比对',
    test: '单只添加自检'
  };
  const PHASE_LABEL = { idle: '待开始', clear: '清空中', diff: '比对中', add: '添加中' };

  function buildHud() {
    hudEl = document.createElement('div');
    hudEl.id = 'ft-wl-hud';
    hudEl.innerHTML = `
      <div class="ft-wl-head">
        <span class="ft-wl-title">自选股一键补齐</span>
        <span class="ft-wl-x" title="隐藏面板">✕</span>
      </div>
      <div class="ft-wl-line ft-wl-job-only" id="ft-wl-group">分组: --</div>
      <div class="ft-wl-bar ft-wl-job-only"><i id="ft-wl-bar-i"></i></div>
      <div class="ft-wl-line ft-wl-job-only" id="ft-wl-stat">等待开始</div>
      <div class="ft-wl-line ft-wl-cur" id="ft-wl-cur"></div>
      <div class="ft-wl-btns ft-wl-job-only">
        <button id="ft-wl-pause">暂停</button>
        <button id="ft-wl-stop">停止</button>
        <button id="ft-wl-copy">复制失败</button>
      </div>
      <div class="ft-wl-btns ft-wl-scan-only">
        <button id="ft-wl-scan-stop">停止抓取</button>
      </div>`;
    document.body.appendChild(hudEl);
    hudEl.querySelector('.ft-wl-x').addEventListener('click', () => { hudEl.style.display = 'none'; });
    hudEl.querySelector('#ft-wl-pause').addEventListener('click', () => togglePause());
    hudEl.querySelector('#ft-wl-stop').addEventListener('click', () => stopJob());
    hudEl.querySelector('#ft-wl-copy').addEventListener('click', () => copyFailed());
    hudEl.querySelector('#ft-wl-scan-stop').addEventListener('click', () => {
      scanState.abort = true;
      renderScan('⏹ 正在中止抓取…');
    });
    return hudEl;
  }

  function setHudMode(mode) {
    if (!mode) return;
    hudMode = (mode === 'job') ? 'job' : 'scan';
    hudEl.classList.toggle('ft-wl-scan', hudMode !== 'job');
    hudEl.querySelector('.ft-wl-title').textContent = HUD_TITLE[mode] || HUD_TITLE[hudMode];
  }

  function ensureHud(mode) {
    if (!hudEl || !document.body.contains(hudEl)) buildHud();
    if (mode) setHudMode(mode);
    hudEl.style.display = 'block';
    return hudEl;
  }

  function etaText(done, total, startedAt) {
    if (!startedAt || done <= 0 || !total || done >= total) return '';
    const per = (Date.now() - startedAt) / done;
    const left = Math.round(per * (total - done) / 1000);
    if (left <= 0) return '';
    return left < 90 ? `  剩~${left}s` : `  剩~${Math.round(left / 60)}min`;
  }

  /* job 模式渲染（按阶段切换指标） */
  function renderHud(extra) {
    const el = ensureHud('job');
    const clearing = job.phase === 'clear';
    el.classList.toggle('ft-wl-danger', clearing);
    el.querySelector('.ft-wl-title').textContent = clearing ? '⚠️ 正在清空自选股分组' : HUD_TITLE.job;

    let total, done, stat;
    if (clearing) {
      total = job.clearTotal || 0;
      done = job.cleared || 0;
      stat = `已删 ${done}/${total}  失败 ${job.clearFailed.length}` +
        etaText(done, total, job.clearStartedAt) + (job.paused ? '  ⏸已暂停' : '');
    } else {
      total = job.total || 0;
      done = job.done || 0;
      const pct = total ? Math.min(100, Math.round(done / total * 100)) : 0;
      stat = `${done}/${total} (${pct}%)  成功 ${job.added}  失败 ${job.failed.length}` +
        etaText(done, total, job.addStartedAt) + (job.paused ? '  ⏸已暂停' : '');
    }
    const pct = total ? Math.min(100, Math.round(done / total * 100)) : 0;

    el.querySelector('#ft-wl-group').textContent =
      `分组: ${job.group || '--'}｜${PHASE_LABEL[job.phase] || job.phase}` +
      (clearing ? '' : `｜第 ${job.pass || 1} 趟`) +
      `｜源: ${SRC_LABEL[SRC.mode] || SRC.mode}`;
    el.querySelector('#ft-wl-bar-i').style.width = pct + '%';
    el.querySelector('#ft-wl-stat').textContent = stat;
    el.querySelector('#ft-wl-cur').textContent = extra || (job.current ? `当前: ${job.current}` : '');
    el.querySelector('#ft-wl-pause').textContent = job.paused ? '继续' : '暂停';
  }

  /* scan 模式渲染（只有一行状态） */
  function renderScan(text, mode) {
    const el = ensureHud(mode || (hudMode === 'job' ? 'scan' : hudMode));
    el.classList.remove('ft-wl-danger');
    el.querySelector('#ft-wl-cur').textContent = text || '';
  }

  function hudInfo(text) {
    if (hudMode === 'job') renderHud(text);
    else renderScan(text);
  }

  function copyFailed() {
    const all = job.failed.map(f => `ADD\t${f.symbol}\t${f.error}`)
      .concat(job.clearFailed.map(f => `DEL\t${f.symbol}\t${f.error}`));
    const txt = all.join('\n');
    navigator.clipboard.writeText(txt || '(无失败项)').then(
      () => toast('📋 失败清单已复制'),
      () => console.log(LOG, '失败清单:\n' + txt));
  }

  /* ================= 任务状态机 ================= */
  const job = {
    running: false, paused: false, stop: false,
    phase: 'idle', clearFirst: false, clearOnly: false,
    group: '', pass: 1, total: 0, done: 0, added: 0,
    failed: [], queue: [], current: '', lastError: '',
    cleared: 0, clearTotal: 0, clearFailed: [], clearSkip: new Set(),
    clearStartedAt: 0, addStartedAt: 0,
    startedAt: 0, sinceReload: 0, sinceReopen: 0,
    srcFrom: '', srcCount: 0, haveCount: 0
  };

  const scanState = { running: false, abort: false };

  function syncBusy() { window.__FT_AUTOMATION__ = !!(job.running || scanState.running); }

  async function persist(autoResume) {
    await storeSet({
      [JOB_KEY]: {
        v: 8, phase: job.phase, clearFirst: job.clearFirst, clearOnly: job.clearOnly,
        group: job.group, pass: job.pass, total: job.total, done: job.done,
        added: job.added, failed: job.failed, queue: job.queue, src: SRC.mode,
        cleared: job.cleared, clearTotal: job.clearTotal, clearFailed: job.clearFailed,
        backedUp: true, autoResume: !!autoResume, ts: Date.now()
      }
    });
  }

  function togglePause() { job.paused = !job.paused; renderHud(); }
  function stopJob() {
    job.stop = true; job.paused = false;
    scanState.abort = true;
    renderHud('正在停止…');
  }

  /* ---------------- 数据源 ---------------- */
  async function manualList() {
    const st = await storeGet([MANUAL_KEY]);
    const arr = st[MANUAL_KEY];
    return Array.isArray(arr) ? arr.filter(Boolean) : [];
  }

  async function getSourceSymbols() {
    if (SRC.mode === 'manual') {
      const m = await manualList();
      if (m.length) return { symbols: m.slice(), from: '本地备用清单', detail: null };
      throw new Error('本地备用清单为空（popup 里保存一份，或切回财报日历）');
    }

    const r = await bg({ action: 'FT_WL_SOURCE', src: SRC.mode, back: SRC.back, ahead: SRC.ahead });
    if (r.ok && r.data) {
      const d = r.data;
      if (d.status === 'disabled') {
        throw new Error(d.message || `数据源 ${SRC.mode} 已在 bridge_server.py 中停用`);
      }
      if (d.status === 'error') throw new Error(d.message || '数据源返回错误');
      if (Array.isArray(d.symbols)) {
        return { symbols: d.symbols.slice(), from: d.from || SRC.mode, detail: d.dates || null };
      }
    }

    const m = await manualList();
    if (m.length) return { symbols: m.slice(), from: '本地备用清单(桥接不可用)', detail: null };
    throw new Error('拿不到 symbol 源：' + (r.error || '桥接不可用') + '，且未设置备用清单');
  }

  async function computeDiff() {
    const src = await getSourceSymbols();
    hudInfo(`来源 ${src.from}：${src.symbols.length} 只，正在抓取当前自选股全表…`);
    const have = await collectWatchlist(n => hudInfo(`已读取 ${n} 只自选股…`));
    const haveSet = new Set(Object.keys(have).map(normKey));
    const missing = src.symbols.filter(s => !haveSet.has(normKey(s)));
    return {
      srcFrom: src.from, srcCount: src.symbols.length, srcDetail: src.detail,
      srcSymbols: src.symbols, haveCount: Object.keys(have).length, missing
    };
  }

  /* ================= 一键 pipeline ================= */
  function resetJob(opts) {
    job.running = true; job.paused = false; job.stop = false;
    job.phase = 'idle';
    job.clearFirst = !!(opts && (opts.clearFirst || opts.clearOnly));
    job.clearOnly = !!(opts && opts.clearOnly);
    job.group = groupName();
    job.pass = 1; job.total = 0; job.done = 0; job.added = 0;
    job.failed = []; job.queue = []; job.current = ''; job.lastError = '';
    job.cleared = 0; job.clearTotal = 0; job.clearFailed = []; job.clearSkip = new Set();
    job.clearStartedAt = 0; job.addStartedAt = 0;
    job.startedAt = Date.now(); job.sinceReload = 0; job.sinceReopen = 0;
    job.srcFrom = ''; job.srcCount = 0; job.haveCount = 0;
    RUN = Object.assign({}, CFG);
    scanState.abort = false;
    syncBusy();
  }

  async function startJob(opts) {
    opts = opts || {};
    if (!isWatchlistPage()) return { ok: false, error: '当前不在 /app/watchlist 页面' };
    if (job.running) return { ok: false, error: '任务已在运行中' };
    if (scanState.running) return { ok: false, error: '行情抓取进行中，请稍后再启动' };
    if (!opts.clearOnly && !findAddButton()) {
      return { ok: false, error: '找不到「添加自选股」按钮，请确认页面已加载完成' };
    }
    if (!document.querySelector('[role="grid"][aria-rowcount]')) {
      return { ok: false, error: '未识别到表格，请等页面加载完成后重试' };
    }

    resetJob(opts);
    cleanNavSearch();
    ensureHud('job');
    renderHud('正在启动…');

    runPipeline({}).catch(e => {
      job.lastError = String((e && e.message) || e);
      renderHud('❌ ' + job.lastError);
      finishJob();
    });

    return {
      ok: true, started: true, group: job.group,
      clearFirst: job.clearFirst, clearOnly: job.clearOnly,
      rows: dataRowsTotal()
    };
  }

  async function runPipeline(opts) {
    opts = opts || {};

    /* ---------- 阶段 1：清空 ---------- */
    if ((job.clearFirst || job.clearOnly) && opts.startPhase !== 'add') {
      if (!opts.skipBackup) {
        try { await backupCurrentList(); }
        catch (e) { log('备份失败（继续执行）', e); }
      }
      if (job.stop) return finishJob();
      const r = await runClearPhase();
      if (r === 'reload') return;                 // 刷新后会自动续跑
      if (r === 'stopped') return finishJob();
      renderHud(`✅ 清空完成：删除 ${job.cleared} 只，失败 ${job.clearFailed.length}`);
      await sleep(800);
      if (job.clearOnly) return finishJob();
    }
    if (job.clearOnly) return finishJob();
    if (job.stop) return finishJob();

    /* ---------- 阶段 2：比对差集（续跑 add 时跳过） ---------- */
    if (opts.resumeAdd && job.queue.length) {
      job.phase = 'add';
      prepareRun(job.queue.length);
    } else {
      job.phase = 'diff';
      renderHud('正在读取数据源并比对差集…');
      const d = await computeDiff();
      if (job.stop) return finishJob();
      job.queue = d.missing.slice();
      job.total = job.queue.length;
      job.srcFrom = d.srcFrom; job.srcCount = d.srcCount; job.haveCount = d.haveCount;
      prepareRun(job.total);
      renderHud(`来源:${d.srcFrom} 共${d.srcCount}｜已有${d.haveCount}｜待加${job.total}`);
      if (!job.total) {
        toast('✅ 数据源里的标的已全部在自选股中，无需补齐');
        return finishJob();
      }
      job.phase = 'add';
    }

    /* ---------- 阶段 3：批量添加 ---------- */
    job.addStartedAt = job.addStartedAt || Date.now();
    try {
      const inp = await ensureInput();
      assertSafeInput(inp);
      log('自检通过，输入框 =', inp.id || inp.placeholder);
    } catch (e) {
      job.lastError = '输入框自检失败: ' + String((e && e.message) || e);
      renderHud('❌ ' + job.lastError);
      return finishJob();
    }

    await persist(true);
    const r = await runAddLoop();
    if (r === 'reload') return;
    return finishJob();
  }

  async function runAddLoop() {
    let consecutiveFail = 0;

    for (; ;) {
      while (job.queue.length && !job.stop) {
        while (job.paused && !job.stop) { renderHud(); await sleep(400); }
        if (job.stop) break;

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

        if (r.status === 'added') { job.added++; consecutiveFail = 0; }
        else {
          job.failed.push({ symbol: sym, error: r.error || '未知' });
          job.lastError = r.error || '';
          consecutiveFail++;
        }
        renderHud();

        if (job.done % RUN.checkpointEvery === 0) await persist(true);

        if (consecutiveFail >= RUN.consecutiveFailAbort) {
          job.paused = true;
          consecutiveFail = 0;
          renderHud(`⚠ 连续失败过多（最后: ${job.lastError}），已自动暂停，请人工检查`);
          await persist(true);
        }

        if (RUN.reopenPanelEvery > 0 && job.sinceReopen >= RUN.reopenPanelEvery) {
          job.sinceReopen = 0;
          try { pressEscape(); } catch (e) { }
          await sleep(450);
        }

        if (RUN.reloadEvery > 0 && job.sinceReload >= RUN.reloadEvery && job.queue.length) {
          renderHud('页面即将刷新以释放内存，随后自动续跑…');
          await persist(true);
          await sleep(900);
          location.reload();
          return 'reload';
        }

        await sleep(RUN.perSymbolDelay + Math.random() * RUN.jitter);
      }

      try { pressEscape(); } catch (e) { }
      cleanNavSearch();

      if (job.stop || job.pass >= RUN.maxPasses) break;

      renderHud('本趟结束，正在复核是否有漏加…');
      try {
        const d = await computeDiff();
        if (!d.missing.length) break;
        job.pass++;
        job.queue = d.missing.slice();
        job.total = job.done + job.queue.length;
        job.sinceReload = 0;
        await persist(true);
        renderHud(`第 ${job.pass} 趟：仍缺 ${job.queue.length} 只`);
      } catch (e) { log('复核失败', e); break; }
    }
    return 'done';
  }

  async function finishJob() {
    job.running = false;
    job.current = '';
    job.phase = 'idle';
    syncBusy();
    await persist(false);
    const bits = [];
    if (job.clearFirst) bits.push(`删除 ${job.cleared}（失败 ${job.clearFailed.length}）`);
    if (!job.clearOnly) bits.push(`新增 ${job.added}（失败 ${job.failed.length}）`);
    const summary = bits.join(' ｜ ') || '无操作';
    renderHud(job.stop ? '⏹ 已手动停止：' + summary : `✅ 完成：${summary}`);
    toast(job.stop ? '⏹ 自选股任务已停止' : `✅ 自选股任务完成：${summary}`);

    // 顺手把最新的「变更%」快照落一次盘（静默）
    if (!job.stop && !job.clearOnly) { try { await fullScanQuotes(true); } catch (e) { } }
  }

  async function resumeJob(saved) {
    resetJob({ clearFirst: saved.clearFirst, clearOnly: saved.clearOnly });
    job.group = saved.group || groupName();
    job.pass = saved.pass || 1;
    job.queue = saved.queue || [];
    job.total = saved.total || job.queue.length;
    job.done = saved.done || 0;
    job.added = saved.added || 0;
    job.failed = saved.failed || [];
    job.cleared = saved.cleared || 0;
    job.clearTotal = saved.clearTotal || 0;
    job.clearFailed = saved.clearFailed || [];
    job.phase = saved.phase === 'clear' ? 'clear' : 'add';
    cleanNavSearch();
    ensureHud('job');
    renderHud('已从上次进度续跑');
    runPipeline({
      skipBackup: true,
      startPhase: job.phase === 'clear' ? 'clear' : 'add',
      resumeAdd: job.phase !== 'clear'
    }).catch(e => {
      job.lastError = String((e && e.message) || e);
      renderHud('❌ ' + job.lastError);
      finishJob();
    });
  }

  /* ================= 变更% 快照（scan 模式，与批量任务完全隔离） ================= */
  async function fullScanQuotes(silent) {
    if (!isWatchlistPage()) return { ok: false, error: '当前不在 /app/watchlist 页面' };
    if (!silent && job.running) return { ok: false, error: '批量任务进行中，请先停止后再抓行情' };
    if (scanState.running) return { ok: false, error: '已有抓取任务在进行中' };

    scanState.running = true;
    scanState.abort = false;
    syncBusy();
    try {
      if (!silent) renderScan('正在全量抓取「变更%」…（约 1~3 分钟，请勿操作本标签页）', 'scan');
      const buf = await collectWatchlist(n => { if (!silent) renderScan(`已抓 ${n} 只行情…`); });
      const n = Object.keys(buf).length;
      if (!n) {
        if (!silent) renderScan('❌ 未抓到任何行（页面是否已加载？）');
        return { ok: false, error: '未抓到任何行（页面是否已加载？）' };
      }
      if (scanState.abort) {
        if (!silent) renderScan(`⏹ 已中止（已抓 ${n} 只，未写入本机）`);
        return { ok: false, error: '用户中止', count: n };
      }
      const resp = await bg({ action: 'FT_SYNC_WATCHLIST', payload: buf, overwrite: true });
      if (!silent) {
        renderScan(resp.ok ? `✅ 已覆盖写入 ${n} 只行情` : ('❌ 写入失败: ' + resp.error));
        toast(resp.ok ? `✅ 已保存 ${n} 只自选股「变更%」` : `❌ 写入失败`);
      }
      return { ok: !!resp.ok, count: n, server: resp };
    } finally {
      scanState.running = false;
      syncBusy();
    }
  }

  let autoTimer = null;
  function autoTickSoon(delay = 2500) {
    if (!AUTO_WATCHLIST) return;
    clearTimeout(autoTimer);
    autoTimer = setTimeout(async () => {
      if (!AUTO_WATCHLIST || !isWatchlistPage() || job.running || scanState.running) return;
      const buf = scrapeRows(Object.create(null));
      if (!Object.keys(buf).length) return;
      const r = await bg({ action: 'FT_SYNC_WATCHLIST', payload: buf, overwrite: false });
      log('自动增量同步自选股', Object.keys(buf).length, r.ok ? 'ok' : r.error);
    }, delay);
  }

  /* ================= 设置 & 引导 ================= */
  function loadSettings() {
    chrome.storage.local.get(
      ['ftDebug', 'ftAutoWatchlist', 'ftWlCfg', 'ftWlSource', 'ftWlBack', 'ftWlAhead'],
      (res) => {
        DEBUG = !!res.ftDebug;
        AUTO_WATCHLIST = res.ftAutoWatchlist === true;
        if (res.ftWlCfg && typeof res.ftWlCfg === 'object') Object.assign(CFG, res.ftWlCfg);
        SRC.mode = res.ftWlSource || 'earnings';
        const b = parseInt(res.ftWlBack, 10);
        const a = parseInt(res.ftWlAhead, 10);
        SRC.back = Number.isFinite(b) ? Math.max(0, b) : 1;
        SRC.ahead = Number.isFinite(a) ? Math.max(0, a) : 0;
        if (!job.running) RUN = Object.assign({}, CFG);
        log('设置: AUTO_WATCHLIST =', AUTO_WATCHLIST, 'SRC =', SRC);
      });
  }
  chrome.storage.onChanged.addListener((c, area) => {
    if (area !== 'local') return;
    if (c.ftDebug || c.ftAutoWatchlist || c.ftWlCfg || c.ftWlSource || c.ftWlBack || c.ftWlAhead) loadSettings();
  });

  async function bootstrap() {
    loadSettings();
    if (!isWatchlistPage()) return;

    await waitFor(() => (document.querySelector('.ag-root') &&
      (findAddButton() || document.querySelector('[role="grid"][aria-rowcount]'))), 25000, 400);

    const st = await storeGet([JOB_KEY]);
    const saved = st[JOB_KEY];
    const hasWork = saved && saved.autoResume &&
      ((saved.phase === 'clear') || (Array.isArray(saved.queue) && saved.queue.length));
    if (hasWork) {
      ensureHud('job');
      job.group = saved.group; job.total = saved.total; job.done = saved.done;
      job.added = saved.added; job.failed = saved.failed || []; job.pass = saved.pass || 1;
      job.cleared = saved.cleared || 0; job.clearTotal = saved.clearTotal || 0;
      job.phase = saved.phase || 'add';
      const g = groupName();
      if (g && saved.group && g !== saved.group) {
        renderHud(`⚠ 检测到未完成任务，但当前分组「${g}」≠ 任务分组「${saved.group}」，未自动续跑`);
        return;
      }
      const what = saved.phase === 'clear'
        ? `清空（已删 ${saved.cleared || 0}）`
        : `添加（剩 ${(saved.queue || []).length} 只）`;
      for (let i = 5; i > 0; i--) {
        renderHud(`检测到未完成任务：${what}，${i} 秒后自动续跑…点「停止」可取消`);
        await sleep(1000);
        if (job.stop) {
          await storeSet({ [JOB_KEY]: Object.assign({}, saved, { autoResume: false }) });
          renderHud('⏹ 已取消续跑');
          job.stop = false;
          return;
        }
      }
      resumeJob(saved);
      return;
    }
    autoTickSoon(4000);
  }

  document.addEventListener('scroll', () => autoTickSoon(3000), true);
  setInterval(() => { if (!job.running && !scanState.running) autoTickSoon(1500); }, 60000);

  /* ================= 与 popup 通信 ================= */
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || !msg.action || !String(msg.action).startsWith('FT_WL_')) return;

    if (msg.action === 'FT_WL_STATUS') {
      sendResponse({
        ok: true, page: isWatchlistPage(), path: location.pathname,
        group: groupName(), gridRows: gridRowCount(), dataRows: dataRowsTotal(),
        auto: AUTO_WATCHLIST,
        src: SRC.mode, srcBack: SRC.back, srcAhead: SRC.ahead,
        running: job.running, paused: job.paused, pass: job.pass,
        phase: job.phase, clearFirst: job.clearFirst, clearOnly: job.clearOnly,
        scanning: scanState.running,
        total: job.total, done: job.done, added: job.added,
        failed: job.failed.length,
        cleared: job.cleared, clearTotal: job.clearTotal, clearFailed: job.clearFailed.length,
        srcFrom: job.srcFrom, srcCount: job.srcCount, haveCount: job.haveCount,
        lastError: job.lastError
      });
      return;
    }

    if (msg.action === 'FT_WL_PROBE') {
      (async () => {
        const btn = findAddButton();
        const del = firstDeletableRow();
        let info = {
          ok: true,
          addBtn: btn ? `${cleanText(btn).slice(0, 20)} (id=${btn.id || '-'}, state=${btn.getAttribute('data-state') || '-'})` : '未找到',
          popover: popoverRoots().length,
          input: '未打开/未找到',
          items: 0, itemSample: [],
          rows: gridRowCount(),
          dataRows: dataRowsTotal(),
          group: groupName(),
          topRow: del ? `${del.sym} (rowId=${del.rowId}, 菜单按钮 id=${del.btn.id || '-'})` : '未找到可删除行'
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
          pressEscape();
        } catch (e) {
          info.error = String(e.message || e);
        }
        sendResponse(info);
      })();
      return true;
    }

    /* ★ 只探测删除链路，不真删（打开菜单看有没有「删除」项） */
    if (msg.action === 'FT_WL_PROBE_DEL') {
      (async () => {
        const tgt = firstDeletableRow();
        if (!tgt) { sendResponse({ ok: false, error: '未找到带三点菜单的行' }); return; }
        closeMenus(); await sleep(100);
        fireMouseSeq(tgt.btn);
        const item = await waitFor(findRemoveMenuItem, 2500, 100);
        const roots = menuRoots();
        const sample = roots.length
          ? Array.from(roots[roots.length - 1].querySelectorAll('[role="menuitem"],[data-dropdown-menu-item]'))
            .map(x => cleanText(x)).slice(0, 8)
          : [];
        closeMenus();
        sendResponse({
          ok: true, symbol: tgt.sym, rowId: tgt.rowId,
          menus: roots.length, menuItems: sample,
          removeFound: !!item, removeId: item ? (item.id || '-') : '-'
        });
      })();
      return true;
    }

    if (msg.action === 'FT_WL_TEST_ADD') {
      const sym = String(msg.symbol || '').trim().toUpperCase();
      if (!sym) { sendResponse({ ok: false, error: '未提供 symbol' }); return; }
      renderScan('测试添加 ' + sym + ' …', 'test');
      addOneSymbol(sym)
        .then(r => { renderScan('测试结果: ' + JSON.stringify(r)); sendResponse({ ok: true, result: r }); })
        .catch(e => sendResponse({ ok: false, error: String(e.message || e) }));
      return true;
    }

    /* ★ 只删一行的自检 */
    if (msg.action === 'FT_WL_TEST_DEL') {
      if (job.running) { sendResponse({ ok: false, error: '批量任务进行中' }); return; }
      renderScan('测试删除最顶行…', 'test');
      deleteTopRow(new Set())
        .then(r => { renderScan('测试删除结果: ' + JSON.stringify(r)); sendResponse({ ok: true, result: r }); })
        .catch(e => sendResponse({ ok: false, error: String(e.message || e) }));
      return true;
    }

    if (msg.action === 'FT_WL_DIFF') {
      if (job.running) { sendResponse({ ok: false, error: '批量任务进行中，请先停止' }); return; }
      renderScan('正在比对差集…', 'diff');
      scanState.running = true; scanState.abort = false; syncBusy();
      computeDiff()
        .then(d => {
          renderScan(`来源 ${d.srcFrom}：${d.srcCount} 只｜已有 ${d.haveCount}｜待加 ${d.missing.length}`);
          sendResponse({
            ok: true, srcFrom: d.srcFrom, srcCount: d.srcCount, srcDetail: d.srcDetail,
            srcSymbols: d.srcSymbols.slice(0, 60),
            haveCount: d.haveCount, missing: d.missing.length,
            sample: d.missing.slice(0, 20), group: groupName()
          });
        })
        .catch(e => {
          renderScan('❌ ' + String(e.message || e));
          sendResponse({ ok: false, error: String(e.message || e) });
        })
        .finally(() => { scanState.running = false; syncBusy(); });
      return true;
    }

    /* ★ 一键 pipeline：msg.clearFirst / msg.clearOnly */
    if (msg.action === 'FT_WL_START') {
      startJob({ clearFirst: !!msg.clearFirst, clearOnly: !!msg.clearOnly })
        .then(r => sendResponse(r)).catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }

    if (msg.action === 'FT_WL_PAUSE') { togglePause(); sendResponse({ ok: true, paused: job.paused }); return; }
    if (msg.action === 'FT_WL_STOP') { stopJob(); scanState.abort = true; sendResponse({ ok: true }); return; }
    if (msg.action === 'FT_WL_FAILED') {
      sendResponse({
        ok: true, list: job.failed,
        clearList: job.clearFailed
      });
      return;
    }
    if (msg.action === 'FT_WL_HUD') {
      ensureHud();
      if (hudMode === 'job') renderHud(); else renderScan();
      sendResponse({ ok: true, mode: hudMode, phase: job.phase });
      return;
    }

    if (msg.action === 'FT_WL_SCAN_QUOTES') {
      fullScanQuotes(false).then(r => sendResponse(r)).catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }
  });

  bootstrap();
  console.log(LOG, `watchlist.js v8 就绪（isWatchlist=${isWatchlistPage()}）`);
})();