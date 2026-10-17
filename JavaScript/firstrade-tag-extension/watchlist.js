/* ============================================================================
 * Firstrade 自选股助手 watchlist.js  v11      仅在 /app/watchlist 生效
 *
 * v11 变更:
 *   ★ Earning 系列分组：源清单按「每组上限(默认35，可配)」分配到 Earning / Earning1 / Earning2 …
 *     不够自动新建、用不上的自动删除（Earning 永久保留）；已在组内且仍合规的标的原地不动（最少点击）
 *   ★ 新建 / 删除分组（⋮ → 管理自选股组合 → 新建 / 🗑）
 *   ★ 分组切换改为精确匹配（Earning1 不会再误切到 Earning10）
 *   ★ 行情抓取覆盖整个 Earning 系列，每条记录带 group
 *   ★ 「清空非保留分组」把整个 Earning 系列视为保留
 * ==========================================================================*/
(() => {
  if (window.__FT_WATCHLIST_V9__) return;
  window.__FT_WATCHLIST_V9__ = true;

  const LOG = '[FT-WL]';
  const JOB_KEY = 'ftWlJob';
  const MANUAL_KEY = 'ftWlManualList';
  const BACKUP_KEY = 'ftWlClearBackup';

  let DEBUG = false;
  let AUTO_WATCHLIST = false;

  const SRC = { mode: 'earnings', back: 1, ahead: 0 };
  const SRC_LABEL = { earnings: '财报日历', sectors: 'Sectors_All', manual: '本地清单' };

  const TARGET = { group: 'Earning', strictSync: true, backToOrigin: true };

  const CFG = {
    perSymbolDelay: 380, jitter: 220, typeSettle: 70, suggestTimeout: 7000,
    verifyTimeout: 3200, verifyTimeout2: 1800, maxRetry: 2, maxPasses: 3,
    reloadEvery: 300, reopenPanelEvery: 40, consecutiveFailAbort: 8,
    checkpointEvery: 10, strictExact: true, scrollWait: 180,
    clearDelay: 450, clearJitter: 250, clearScrollWait: 220, menuTimeout: 2400,
    menuCloseTimeout: 1500, removeVerifyTimeout: 3000, removeVerifyTimeout2: 2000,
    deleteSettle: 600, deleteMaxTry: 3, clearFailAbort: 6, clearReloadEvery: 400,
    clearCountdown: 5,
    groupSwitchTimeout: 7000, gridSettleTimeout: 8000,
    /* ★ v11 Earning 系列 */
    groupCap: 35,            // 每组最多写入多少只（popup 可改）
    groupHardMax: 38,        // Firstrade 实测单组上限
    maxFamilyGroups: 15      // 系列分组数量安全上限
  };
  let RUN = Object.assign({}, CFG);

  function prepareRun(total) {
    const keep = { clearDelay: RUN.clearDelay, clearJitter: RUN.clearJitter };
    RUN = Object.assign({}, CFG, keep);
    if (total > 0 && total <= 30) {
      RUN.reloadEvery = 0;
      RUN.maxPasses = Math.min(RUN.maxPasses, 2);
    }
  }

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const log = (...a) => { if (DEBUG) console.log(LOG, ...a); };
  const isWatchlistPage = () => /\/watchlist/i.test(location.pathname || '');
  const toast = (t) => { try { (window.__FT_TOAST__ || console.log)(t); } catch (e) { } };

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
  const normGroup = (s) => String(s || '')
    .replace(/[（(][^）)]*[）)]\s*$/g, '')
    .replace(/\s+/g, '')
    .toUpperCase();
  const stripCount = (s) => String(s || '').replace(/\u00a0/g, ' ').replace(/[（(]\s*\d+\s*[）)]\s*$/, '').trim();

  /* ★ v11：Earning 系列分组识别  base=0, base1=1, base2=2 … （Earning01 之类不算） */
  function familyIndex(name, base) {
    const n = normGroup(stripCount(name)), b = normGroup(base || TARGET.group || 'Earning');
    if (!n || !b) return -1;
    if (n === b) return 0;
    if (!n.startsWith(b)) return -1;
    const rest = n.slice(b.length);
    return /^[1-9]\d*$/.test(rest) ? parseInt(rest, 10) : -1;
  }
  const familyName = (base, i) => i === 0 ? base : `${base}${i}`;
  const isFamily = (name, base) => familyIndex(name, base) >= 0;
  function groupCap() {
    const n = parseInt(CFG.groupCap, 10);
    return Math.max(1, Math.min(CFG.groupHardMax || 38, Number.isFinite(n) ? n : 35));
  }

  function cleanText(el) {
    const t = (el && (el.innerText || el.textContent)) || '';
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

  /* ==========================================================================
   *                        弹层作用域定位
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

  /* ==========================================================================
   *                     分组选择器：识别 / 列举 / 切换
   * ========================================================================*/
  function groupTriggerEl() {
    const all = Array.from(document.querySelectorAll('[data-select-trigger]'))
      .filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE));
    const inMain = all.filter(el => el.closest('main'));
    return inMain[0] || all[0] || null;
  }

  function groupName() {
    const t = groupTriggerEl();
    return t ? cleanText(t) : '';
  }

  function groupOptions() {
    const roots = Array.from(document.querySelectorAll(
      '[data-select-content], [role="listbox"], [data-popover-content]'
    )).filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE));
    let items = [];
    roots.forEach(r => {
      items = items.concat(Array.from(r.querySelectorAll('[data-select-item], [role="option"]')));
    });
    if (!items.length) {
      items = Array.from(document.querySelectorAll('[data-select-item], [role="option"]'))
        .filter(el => !el.closest(FORBIDDEN_SCOPE) && !el.closest('[data-command-root]'));
    }
    return items.filter(isVisible);
  }

  /* ★ v11：精确优先；前缀兜底仅在唯一且「后一个字符不是数字」时才用（防 Earning1 → Earning10） */
  function matchOption(opts, want) {
    const w = normGroup(want);
    if (!w) return null;
    const hit = opts.find(o => normGroup(cleanText(o)) === w);
    if (hit) return { el: hit, exact: true };
    const cand = opts.filter(o => {
      const c = normGroup(cleanText(o));
      return c.startsWith(w) && !/^\d/.test(c.slice(w.length));
    });
    return cand.length === 1 ? { el: cand[0], exact: false } : null;
  }

  /* ★ v11.2：分组下拉（bits-ui Select）是否展开 / 稳妥收起
   *   旧版只往 trigger 发 Escape —— 焦点已在下拉内容里，收不到 → 下拉残留，
   *   导致随后点「⋮」的第一次按下被当成「点外部关下拉」吞掉 */
  const selOpenState = (el) => !!el && (el.getAttribute('aria-expanded') === 'true' || el.getAttribute('data-state') === 'open');
  function groupSelectContents() {
    return Array.from(document.querySelectorAll('[data-select-content], [role="listbox"]'))
      .filter(el => isVisible(el) && el.getAttribute('data-state') !== 'closed' &&
        !el.closest(FORBIDDEN_SCOPE) && !el.closest('[data-command-root]') &&
        !el.closest('[data-combobox-content]') && !el.closest('#ft-trade-layer') &&
        !el.closest('[role="dialog"], [data-dialog-content]'));
  }
  function groupSelectOpen() {
    return selOpenState(groupTriggerEl()) || groupSelectContents().length > 0;
  }
  async function closeGroupSelect() {
    for (let i = 0; i < 4 && groupSelectOpen(); i++) {
      const t = groupTriggerEl();
      if (i < 2) {
        const box = groupSelectContents()[0];
        const ae = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
        [ae, box, t, document.body].filter(Boolean).forEach(el => { try { sendKey(el, 'Escape', 27); } catch (e) { } });
      } else {
        /* 兜底：点「当前分组」那一项 —— 选中自身 = 不切换，但一定会关闭下拉 */
        const cur = normGroup(groupName());
        const opt = groupOptions().find(o => normGroup(cleanText(o)) === cur);
        if (opt) fireMouseSeq(opt); else if (t) fireMouseSeq(t);
      }
      await waitFor(() => !groupSelectOpen(), 900, 80);
    }
    await sleep(120);
    return !groupSelectOpen();
  }

  async function listGroupOptions() {
    const trig = groupTriggerEl();
    if (!trig) return { ok: false, error: '找不到分组选择器 [data-select-trigger]' };
    await closeGroupSelect();
    fireMouseSeq(groupTriggerEl() || trig);
    const opts = await waitFor(() => { const o = groupOptions(); return o.length ? o : null; }, 3500, 120);
    const names = opts ? opts.map(o => cleanText(o)).filter(Boolean) : [];
    await closeGroupSelect();
    return { ok: !!names.length, current: groupName(), options: names };
  }

  async function waitGridSettled(timeout) {
    timeout = timeout || RUN.gridSettleTimeout || 8000;
    const t0 = Date.now();
    let last = null, same = 0;
    while (Date.now() - t0 < timeout) {
      const n = gridRowCount();
      const shapeOk = n !== null && (n > 1 || gridSaysEmpty());
      if (shapeOk && n === last) {
        same++;
        if (same >= 3) return n;
      } else { same = 0; last = shapeOk ? n : null; }
      await sleep(200);
    }
    return gridRowCount();
  }

  async function switchGroup(target) {
    const want = normGroup(target);
    if (!want) return { ok: false, error: '目标分组名为空' };
    if (normGroup(groupName()) === want) { await closeGroupSelect(); return { ok: true, changed: false }; }

    if (!groupTriggerEl()) return { ok: false, error: '页面上找不到分组选择器 [data-select-trigger]' };

    for (let attempt = 0; attempt < 3; attempt++) {
      await closeGroupSelect();
      const trig = groupTriggerEl();
      if (!trig) return { ok: false, error: '页面上找不到分组选择器 [data-select-trigger]' };
      fireMouseSeq(trig);
      const opts = await waitFor(() => { const o = groupOptions(); return o.length ? o : null; }, 3500, 120);
      if (!opts) { await closeGroupSelect(); await sleep(420); continue; }

      const m = matchOption(opts, target);
      if (!m) {
        const names = opts.map(o => cleanText(o)).filter(Boolean);
        await closeGroupSelect();
        return { ok: false, options: names, error: `分组「${target}」不存在（页面可选：${names.join(' / ') || '空'}）` };
      }
      const label = cleanText(m.el);
      fireMouseSeq(m.el);
      try { if (m.el.isConnected) m.el.click(); } catch (e) { }
      const ok = await waitFor(() => {
        const cur = normGroup(groupName());
        return cur === want || (!m.exact && cur === normGroup(label));
      }, RUN.groupSwitchTimeout || 7000, 160);
      if (ok) {
        await closeGroupSelect();
        await waitGridSettled();
        await sleep(300);
        return { ok: true, changed: true, group: groupName() };
      }
      await closeGroupSelect();
      await sleep(500);
    }
    return { ok: false, error: `切换到分组「${target}」失败（重试 3 次）` };
  }

  /* ==========================================================================
   *                    行数识别（去重 + 空表识别）
   * ========================================================================*/
  const ROW_EXCLUDE = '.ag-floating-top, .ag-floating-bottom, #app-quote-bar, header, #app-header';

  function domRowIds() {
    const set = new Set();
    document.querySelectorAll('[row-id]').forEach(r => {
      if (r.closest(ROW_EXCLUDE)) return;
      const rid = r.getAttribute('row-id');
      if (rid && symbolFromRowId(rid)) set.add(rid);
    });
    return set;
  }

  const EMPTY_STATE_RE = /自选列表中尚未添加任何内容|尚未添加任何(内容|股票|标的)|添加股票代码以查看表现|Nothing (has been )?added|haven'?t added any|watchlist is empty|No symbols (have been )?added/i;
  const EMPTY_TXT_RE = /没有(任何)?(自选股|股票|标的|数据|记录|结果)|暂无(自选股|股票|数据|记录)?|列表为空|No (symbols|rows|data|results|securities)|is empty|Nothing to show/i;

  function emptyStateEl() {
    const main = document.querySelector('main');
    if (!main) return null;
    const els = main.querySelectorAll('h1, h2, h3, h4, h5, p');
    for (const el of els) {
      if (el.closest('#ft-wl-hud, #ft-trade-layer, [role="grid"], .ag-root')) continue;
      const t = cleanText(el);
      if (!t || t.length > 80 || !EMPTY_STATE_RE.test(t)) continue;
      if (isVisible(el)) return el;
    }
    return null;
  }

  function gridLoading() {
    const ld = document.querySelector('.ag-overlay-loading-wrapper, .ag-overlay-loading-center');
    if (ld && isVisible(ld)) return true;
    const sp = document.querySelector('main [role="grid"] .animate-spin, main .ag-root .animate-spin');
    return !!(sp && isVisible(sp));
  }

  function gridSaysEmpty() {
    if (domRowIds().size > 0) return false;
    if (emptyStateEl()) return true;
    if (gridLoading()) return false;
    const ov = document.querySelector('.ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center');
    if (ov && isVisible(ov)) return true;
    const gs = Array.from(document.querySelectorAll('[role="grid"][aria-rowcount]'))
      .filter(g => !g.closest(ROW_EXCLUDE) && !g.closest('#ft-trade-layer'));
    if (gs.length) {
      const ns = gs.map(g => parseInt(g.getAttribute('aria-rowcount'), 10)).filter(Number.isFinite);
      if (ns.length && ns.every(n => n >= 0 && n <= 1)) return true;
    }
    const main = document.querySelector('main');
    if (main && EMPTY_TXT_RE.test(cleanText(main).slice(0, 5000))) return true;
    return false;
  }

  async function confirmGroupEmpty(want, timeout) {
    const t0 = Date.now();
    let es = 0, strong = 0, weak = 0, why = '';
    while (Date.now() - t0 < (timeout || 7000)) {
      const g = groupName();
      if (!g) why = '找不到分组选择器（页面可能未加载完或已退出登录）';
      else if (want && normGroup(g) !== normGroup(want)) why = `当前分组是「${g}」而不是「${want}」`;
      else if (domRowIds().size > 0) return { empty: false, rowsAppeared: true };
      else if (emptyStateEl()) {
        strong = 0; weak = 0;
        if (++es >= 3) return { empty: true, how: 'empty_state' };
        why = ''; await sleep(350); continue;
      }
      else if (!document.querySelector('[role="grid"], .ag-root, .ag-body-viewport')) {
        why = '页面上既没有表格，也没有「自选列表中尚未添加任何内容」的空状态提示（可能仍在加载）';
      }
      else if (gridLoading()) why = '表格仍在加载中';
      else if (gridSaysEmpty()) { es = 0; weak = 0; if (++strong >= 4) return { empty: true, how: 'strong' }; why = ''; await sleep(350); continue; }
      else if (findAddButton() && dataRowsTotal() === 0) { es = 0; strong = 0; if (++weak >= 9) return { empty: true, how: 'weak' }; why = '表格无行但无空状态标识'; await sleep(350); continue; }
      else why = '表格状态无法判定';
      es = 0; strong = 0; weak = 0;
      await sleep(350);
    }
    return { empty: false, error: why || '确认超时' };
  }

  async function probeSourceCount() {
    if (SRC.mode === 'manual') {
      const m = await manualList();
      return { ok: true, count: m.length, from: '本地备用清单' };
    }
    const r = await bg({ action: 'FT_WL_SOURCE', src: SRC.mode, back: SRC.back, ahead: SRC.ahead });
    if (!r.ok || !r.data) return { ok: false, error: '桥接不可用：' + (r.error || '无响应') };
    const d = r.data;
    if (d.status !== 'ok') return { ok: false, error: d.message || d.status || '数据源异常' };
    return { ok: true, count: d.count || 0, from: d.from || SRC.mode };
  }

  function gridRowCount() {
    const gs = Array.from(document.querySelectorAll('[role="grid"][aria-rowcount]'))
      .filter(g => !g.closest(ROW_EXCLUDE));
    let best = null;
    gs.forEach(g => {
      const n = parseInt(g.getAttribute('aria-rowcount'), 10);
      if (Number.isFinite(n) && (best === null || n > best)) best = n;
    });
    if (best !== null) return best;
    const n = domRowIds().size;
    if (n > 0) return n + 1;
    if (gridSaysEmpty()) return 1;
    if (document.querySelector('.ag-root, [role="grid"], .ag-body-viewport, main') || findAddButton()) return 1;
    return null;
  }

  function dataRowsTotal() {
    const n = gridRowCount();
    if (n === null) return 0;
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
      if (row.closest(ROW_EXCLUDE)) return;
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
    await sleep(200);
    scrapeRows(buf);

    let guard = 0, stagnant = 0;
    while (guard++ < 4000) {
      if (scanState.abort || (job.running && job.stop)) break;
      s = scrollState();
      const before = Object.keys(buf).length;
      const atEnd = (s.top + s.clientH >= s.scrollH - 3);
      const step = Math.max(200, s.clientH - 80);
      if (atEnd) {
        await sleep(180);
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
    await sleep(100);
    scrapeRows(buf);
    s = scrollState();
    s.top = original;
    if (onProgress) onProgress(Object.keys(buf).length);

    if (!(scanState.abort || (job.running && job.stop))) {
      try {
        const M = window.__FT_WL_MEMBER__;
        const g = groupName();
        const keys = Object.keys(buf);
        const total = dataRowsTotal();
        if (M && g) {
          if (keys.length === 0) {
            if (gridSaysEmpty()) M.snapshot(g, [], true, 'collect_empty');
          } else {
            M.snapshot(g, keys, keys.length >= total, 'collect');
          }
        }
      } catch (e) { log('分组归属快照失败', e); }
    }
    return buf;
  }

  /* ---------------- 单只行情读取（交易层 / G 键取数 / 持仓页共用） ---------------- */
  function numOf(t) {
    const m = String(t || '').replace(/,/g, '').match(/-?\d+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : NaN;
  }

  function rowQuote(sym) {
    const k = normKey(sym);
    let out = null;
    document.querySelectorAll('[row-id]').forEach((row) => {
      if (row.closest(ROW_EXCLUDE) || row.closest('#ft-trade-layer')) return;
      const s = symbolFromRowId(row.getAttribute('row-id'));
      if (!s || normKey(s) !== k) return;
      const child = /\bag-row-level-[1-9]/.test(String(row.className || ''));
      out = out || { symbol: s };
      const ch = row.querySelector('[col-id="changePercent"]');
      if (ch && !out.change_pct) {
        const t = cleanText(ch);
        if (t && t !== '--') out.change_pct = t;
        const dv = ch.querySelector('[data-value]');
        if (dv) {
          const n = parseFloat(dv.getAttribute('data-value'));
          if (Number.isFinite(n)) out.change_pct_num = Math.round(n * 1e6) / 1e6;
        }
      }
      const la = row.querySelector('[col-id="last"]');
      if (la && !(out.price > 0)) {
        const t = cleanText(la);
        const n = numOf(t);
        if (n > 0) { out.price = n; out.last = t; }
      }
      const qt = row.querySelector('[col-id="quantity"]');
      if (qt && !child && !(out.quantity > 0)) {
        const n = numOf(cleanText(qt));
        if (n > 0) out.quantity = n;
      }
    });
    return out;
  }

  async function findRowQuote(sym, scroll) {
    let q = rowQuote(sym);
    if (q || !scroll) return q;
    const s0 = scrollState();
    const original = s0.top;
    s0.top = 0;
    await sleep(RUN.scrollWait || 180);
    q = rowQuote(sym);
    let guard = 0;
    while (!q && guard++ < 2000) {
      const s = scrollState();
      if (s.top + s.clientH >= s.scrollH - 3) break;
      s.top = s.top + Math.max(160, s.clientH - 120);
      await sleep(RUN.scrollWait || 180);
      q = rowQuote(sym);
    }
    if (!q) scrollState().top = original;
    return q;
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
    throw new Error('点击「添加自选股」后未出现弹层输入框');
  }

  function assertSafeInput(input) {
    if (!input) throw new Error('输入框为空');
    if (isForbiddenInput(input)) throw new Error('拒绝写入：命中了页头/报价条搜索框');
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
    return { el: items[0] || null, exact: false, firstValue: items[0] ? itemValue(items[0]) : '' };
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

  function hasSymbolInGrid(sym) {
    const k = normKey(sym);
    for (const rid of domRowIds()) {
      const s = symbolFromRowId(rid);
      if (s && normKey(s) === k) return true;
    }
    return false;
  }

  async function verifyAdded(before, timeout, cand) {
    if (before === null) { await sleep(450); return 'assumed'; }
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const cur = gridRowCount();
      if (cur !== null && cur > before) return 'added';
      if (cand && hasSymbolInGrid(cand)) return 'added';
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
          let v = await verifyAdded(before, RUN.verifyTimeout, cand);
          if (v === 'unchanged') {
            const inp2 = getCommandInput();
            if (inp2 && listItems().length) {
              const ok = await keyboardSelect(inp2, cand);
              if (ok) {
                await clickConfirmIfAny();
                v = await verifyAdded(before, RUN.verifyTimeout2, cand);
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
   *          删除：竖三点菜单 → 红色「删除」项（可按 symbol 精准删）
   * ========================================================================*/
  function rowMenuButton(row) {
    return row.querySelector('[col-id="actions"] button[aria-haspopup="menu"]')
      || row.querySelector('button[id^="watchlist-action-menu"]')
      || row.querySelector('button[aria-haspopup="menu"][data-dropdown-menu-trigger]')
      || row.querySelector('button[aria-haspopup="menu"]')
      || row.querySelector('[col-id="actions"] button')
      || null;
  }

  function allDataRows() {
    return Array.from(document.querySelectorAll('[row-id]'))
      .filter(r => !r.closest(ROW_EXCLUDE) && symbolFromRowId(r.getAttribute('row-id')));
  }

  function firstDeletableRow(skip) {
    let best = null, bestIdx = Infinity;
    for (const row of allDataRows()) {
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

  function pickRowBySymbol(sym) {
    const k = normKey(sym);
    for (const row of allDataRows()) {
      const rowId = row.getAttribute('row-id');
      const s = symbolFromRowId(rowId);
      if (!s || normKey(s) !== k) continue;
      const btn = rowMenuButton(row);
      if (btn && isVisible(btn)) return { row, rowId, sym: s, btn };
    }
    return null;
  }

  async function locateRow(sym) {
    let hit = pickRowBySymbol(sym);
    if (hit) return hit;
    const s0 = scrollState();
    s0.top = 0;
    await sleep(RUN.clearScrollWait);
    hit = pickRowBySymbol(sym);
    if (hit) return hit;
    let guard = 0;
    for (; ;) {
      if ((job.running && job.stop) || guard++ > 4000) break;
      const s = scrollState();
      if (s.top + s.clientH >= s.scrollH - 3) break;
      s.top = s.top + Math.max(160, s.clientH - 120);
      await sleep(RUN.clearScrollWait);
      hit = pickRowBySymbol(sym);
      if (hit) return hit;
    }
    return null;
  }

  function menuRoots() {
    return Array.from(document.querySelectorAll('[data-dropdown-menu-content], [role="menu"]'))
      .filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE));
  }

  function findRemoveMenuItemIn(roots) {
    for (let i = roots.length - 1; i >= 0; i--) {
      const items = Array.from(roots[i].querySelectorAll('[role="menuitem"], [data-dropdown-menu-item]'))
        .filter(isVisible);
      let hit = items.find(x => /watchlist-(remove|delete)/i.test(x.id || ''));
      if (hit) return hit;
      hit = items.find(x => /^(删除|移除|移出|删除自选|移除自选|Remove|Remove from watchlist|Delete)$/i.test(cleanText(x)));
      if (hit) return hit;
      hit = items.find(x => /删除|移除|移出|Remove|Delete/i.test(cleanText(x)) &&
        /text-action-down|surface-tint-red|text-red|destructive/i.test(String(x.className || '')));
      if (hit) return hit;
      hit = items.find(x => /删除|移除|移出|Remove|Delete/i.test(cleanText(x)));
      if (hit) return hit;
    }
    return null;
  }
  function findRemoveMenuItem() { return findRemoveMenuItemIn(menuRoots()); }

  const isOpenState = (el) => !!el && (el.getAttribute('aria-expanded') === 'true' || el.getAttribute('data-state') === 'open');

  function menuOwnedBy(btn, root) {
    if (!btn || !root) return false;
    const lb = root.getAttribute('aria-labelledby');
    if (lb && btn.id) return lb === btn.id;
    const ctl = btn.getAttribute('aria-controls');
    if (ctl && root.id) return ctl === root.id;
    return isOpenState(btn);
  }
  const liveMenuRoots = () => menuRoots().filter(r => r.getAttribute('data-state') !== 'closed');
  function findRemoveItemFor(btn) {
    const roots = liveMenuRoots();
    let own = roots.filter(r => menuOwnedBy(btn, r));
    if (!own.length && roots.length === 1 && isOpenState(btn)) own = roots;
    return findRemoveMenuItemIn(own);
  }

  function closeMenus() {
    const roots = menuRoots();
    if (roots.length) sendKey(roots[roots.length - 1], 'Escape', 27);
    sendKey(document.body, 'Escape', 27);
  }

  async function waitMenusClosed(timeout) {
    const lim = timeout || RUN.menuCloseTimeout || 1500;
    const t0 = Date.now();
    let n = 0;
    while (menuRoots().length && Date.now() - t0 < lim) {
      if (liveMenuRoots().length && n % 4 === 0) closeMenus();
      n++;
      await sleep(100);
    }
    return menuRoots().length === 0;
  }

  async function clickDangerConfirm() {
    const dlgs = Array.from(document.querySelectorAll(
      '[role="dialog"], [role="alertdialog"], [data-dialog-content], [data-alert-dialog-content]'
    )).filter(el => isVisible(el) && !el.closest(FORBIDDEN_SCOPE) && !el.querySelector('[data-command-root]') &&
      !el.closest('#ft-trade-layer') && !el.querySelector('#quick-trade-symbol-search'));
    if (!dlgs.length) return false;
    const root = dlgs[dlgs.length - 1];
    const btns = Array.from(root.querySelectorAll('button')).filter(isVisible);
    const ok = btns.find(b => /^(删除|移除|移出|确定|确认|是|Remove|Delete|Confirm|Yes|OK)$/i.test(cleanText(b)));
    if (ok) { fireMouseSeq(ok); await sleep(240); return true; }
    return false;
  }

  function rowExists(rowId) {
    for (const r of document.querySelectorAll('[row-id]')) {
      if (r.getAttribute('row-id') === rowId) return true;
    }
    return false;
  }

  async function waitRowGone(rowId, before, timeout, sym) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const cur = gridRowCount();
      if (before !== null && cur !== null && cur < before) return true;
      if (!rowExists(rowId) && (!sym || !hasSymbolInGrid(sym))) return true;
      await sleep(120);
    }
    return false;
  }

  async function removeCore(findTgt) {
    await waitMenusClosed();
    let tgt = await findTgt();
    if (!tgt) return { status: 'missing' };
    try { tgt.row.scrollIntoView({ block: 'nearest' }); } catch (e) { }
    await sleep(120);
    tgt = pickRowBySymbol(tgt.sym) || tgt;
    const { btn, sym, rowId } = tgt;
    const before = gridRowCount();

    let item = null;
    for (let a = 0; a < 2 && !item; a++) {
      fireMouseSeq(btn);
      item = await waitFor(() => findRemoveItemFor(btn), RUN.menuTimeout, 90);
      if (!item) {
        try { btn.focus(); sendKey(btn, 'Enter', 13); } catch (e) { }
        item = await waitFor(() => findRemoveItemFor(btn), 1200, 90);
      }
      if (!item) await waitMenusClosed();
    }
    if (!item) {
      await waitMenusClosed();
      return { status: 'failed', symbol: sym, rowId, error: '未弹出操作菜单/未找到「删除」项' };
    }
    const owner = btn.isConnected ? btn.closest('[row-id]') : null;
    if (!owner || normKey(symbolFromRowId(owner.getAttribute('row-id'))) !== normKey(sym)) {
      await waitMenusClosed();
      return { status: 'failed', symbol: sym, rowId, error: '菜单打开期间行节点被回收（已放弃点击，防误删）' };
    }

    fireMouseSeq(item);
    await sleep(220);
    await clickDangerConfirm();
    let gone = await waitRowGone(rowId, before, RUN.removeVerifyTimeout, sym);
    if (!gone) {
      const again = findRemoveItemFor(btn);
      if (again) {
        try { again.click(); } catch (e) { }
        await sleep(220);
        await clickDangerConfirm();
        gone = await waitRowGone(rowId, before, RUN.removeVerifyTimeout2, sym);
      }
    }
    await waitMenusClosed();
    if (!gone) return { status: 'failed', symbol: sym, rowId, error: '点了删除但行未消失', clicked: true };

    await waitGridSettled(2500);
    await sleep(RUN.deleteSettle || 600);
    if (hasSymbolInGrid(sym)) {
      return { status: 'failed', symbol: sym, rowId, error: '删除后行又出现（服务器可能拒绝了过快的请求）', clicked: true };
    }
    return { status: 'removed', symbol: sym, rowId };
  }

  async function deleteTopRow(skip) {
    const s = scrollState();
    if (s.top > 2) { s.top = 0; await sleep(RUN.clearScrollWait); }
    const find = async () => {
      let t = firstDeletableRow(skip);
      if (!t) { await sleep(350); t = firstDeletableRow(skip); }
      return t;
    };
    let r = null;
    const tries = RUN.deleteMaxTry || 3;
    for (let i = 0; i < tries; i++) {
      r = await removeCore(find);
      if (r.status === 'missing') return { status: 'empty' };
      if (r.status === 'removed') return r;
      await sleep(900 + i * 900);
    }
    return r;
  }

  async function deleteSymbol(sym) {
    let last = null, clicked = false;
    const tries = RUN.deleteMaxTry || 3;
    for (let i = 0; i < tries; i++) {
      if (job.running && job.stop) return { status: 'aborted', symbol: sym };
      const r = await removeCore(() => locateRow(sym));
      if (r.status === 'removed') return r;
      if (r.status === 'missing') {
        return clicked ? { status: 'removed', symbol: sym, late: true } : { status: 'missing', symbol: sym };
      }
      clicked = clicked || !!r.clicked;
      last = r;
      log(`删除 ${sym} 第 ${i + 1} 次失败：${r.error}，稍后重试`);
      await sleep(900 + i * 900);
    }
    return last || { status: 'failed', symbol: sym, error: '未知' };
  }

  /* ==========================================================================
   *     ★ v11.2 分组管理：「添加自选股」右侧 ⋮ → 「管理自选股组合」→ 新建 / 🗑 删除
   * ========================================================================*/
  const GROUP_MENU_RE = /管理自选股组合|管理自选|管理组合|Manage\s*(Watch\s*lists?|Groups?|Portfolios?)/i;
  const NEW_GROUP_RE = /新建自选股组合|新建组合|Create\s*(Watch\s*list|Group)|New\s*(Watch\s*list|Group)/i;
  const SAVE_RE = /^(储存|保存|存储|确定|确认|Save|OK|Create)$/i;
  const CANCEL_RE = /^(取消|Cancel)$/i;
  const DEL_CONFIRM_RE = /^(删除|Delete|确认删除|确定)$/i;
  const DOTS_PATH_RE = /M12 5m-1 0a1 1 0 1 0 2 0|M12 12m-1 0a1 1 0 1 0 2 0|M12 19m-1 0a1 1 0 1 0 2 0/;

  function visDialogs() {
    return Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"], [data-dialog-content]'))
      .filter(d => isVisible(d) && !d.closest('#ft-trade-layer') && !d.closest(FORBIDDEN_SCOPE));
  }

  /* ⋮ 按钮：无文字 + 菜单触发器 + 绝不是分组下拉(listbox) */
  function isDotsMenuBtn(b) {
    if (!b || b.tagName !== 'BUTTON' || !isVisible(b)) return false;
    if (b.getAttribute('aria-haspopup') === 'listbox' || b.hasAttribute('data-select-trigger')) return false;
    if (b.closest('[row-id], [role="grid"], .ag-root, #ft-wl-hud, #ft-trade-layer, ' + FORBIDDEN_SCOPE)) return false;
    if (cleanText(b)) return false;
    return b.getAttribute('aria-haspopup') === 'menu' || b.hasAttribute('data-dropdown-menu-trigger');
  }
  const hasDotsIcon = (b) => Array.from(b.querySelectorAll('path')).some(p => DOTS_PATH_RE.test(p.getAttribute('d') || ''));

  function groupMenuButton() {
    const add = findAddButton();
    if (add) {
      /* ① 「添加自选股」后面紧挨着的第一个 ⋮ */
      let p = add.parentElement;
      for (let i = 0; i < 3 && p; i++, p = p.parentElement) {
        const after = Array.from(p.querySelectorAll('button')).filter(isDotsMenuBtn)
          .filter(b => add.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
        const hit = after.find(hasDotsIcon) || after[0];
        if (hit) return hit;
      }
    }
    /* ② 兜底：main 里带三点图标的菜单按钮 */
    const main = document.querySelector('main');
    if (!main) return null;
    const all = Array.from(main.querySelectorAll('button')).filter(isDotsMenuBtn);
    return all.find(hasDotsIcon) || null;
  }

  function newGroupBtnIn(d) {
    const btns = Array.from(d.querySelectorAll('button')).filter(isVisible);
    return btns.find(b => /新建自选股组合/.test(cleanText(b))) || btns.find(b => NEW_GROUP_RE.test(cleanText(b))) || null;
  }
  function manageDialog() {
    const ds = visDialogs();
    for (let i = ds.length - 1; i >= 0; i--) if (newGroupBtnIn(ds[i])) return ds[i];
    return null;
  }

  function manageRows(dlg) {
    if (!dlg) return [];
    const out = [];
    const pathOf = (b) => Array.from(b.querySelectorAll('path')).map(p => p.getAttribute('d') || '').join(' ');
    dlg.querySelectorAll('div').forEach(div => {
      const sp = div.querySelector(':scope > span');
      if (!sp) return;
      const btns = Array.from(div.querySelectorAll('button')).filter(isVisible);
      if (!btns.length || btns.length > 3 || btns.some(b => cleanText(b))) return;   // 只认纯图标按钮行
      const name = cleanText(sp);
      if (!name) return;
      const del = btns.find(b => /M4 7l16 0|M10 11l0 6|M9 7v-3/.test(pathOf(b))) || (btns.length === 2 ? btns[1] : null);
      out.push({ name, el: div, del, edit: btns.find(b => b !== del) || null });
    });
    return out;
  }
  /* 管理窗口里是否有该分组：true / false / null(窗口不在) */
  function manageHas(name) {
    const d = manageDialog();
    if (!d) return null;
    return manageRows(d).some(r => normGroup(r.name) === normGroup(name));
  }

  async function closeDialogs() {
    for (let i = 0; i < 6; i++) {
      const ds = visDialogs();
      if (!ds.length) return true;
      const top = ds[ds.length - 1];
      const x = top.querySelector('[data-dialog-close], button[aria-label="Close Dialog"], button[aria-label="Close"]');
      const cancel = Array.from(top.querySelectorAll('button')).filter(isVisible).find(b => CANCEL_RE.test(cleanText(b)));
      if (x && isVisible(x)) fireMouseSeq(x);
      else if (cancel) fireMouseSeq(cancel);
      else { sendKey(top, 'Escape', 27); sendKey(document.body, 'Escape', 27); }
      await waitFor(() => !top.isConnected || !isVisible(top), 1500, 100);
    }
    return !visDialogs().length;
  }

  function groupMenuItem(btn) {
    const roots = liveMenuRoots();
    const own = roots.filter(r => menuOwnedBy(btn, r));
    for (const r of (own.length ? own : roots)) {
      const it = Array.from(r.querySelectorAll('[role="menuitem"], [data-dropdown-menu-item]'))
        .filter(isVisible).find(x => GROUP_MENU_RE.test(cleanText(x)));
      if (it) return it;
    }
    return null;
  }

  async function openManageDialog() {
    let d = manageDialog();
    if (d) return d;
    await closeGroupSelect();                    // ★ 关键：残留的分组下拉会吞掉对 ⋮ 的点击
    await closeDialogs();
    if (menuRoots().length) { closeMenus(); await waitMenusClosed(); }
    for (let a = 0; a < 4; a++) {
      const btn = groupMenuButton();
      if (!btn) return null;
      try { btn.scrollIntoView({ block: 'nearest' }); } catch (e) { }
      if (isOpenState(btn)) { closeMenus(); await waitMenusClosed(); }
      if (a % 2 === 0) fireMouseSeq(btn);
      else { try { btn.focus(); } catch (e) { } sendKey(btn, 'Enter', 13); }
      let item = await waitFor(() => groupMenuItem(btn), 2000, 100);
      if (!item) {                                // 鼠标没打开 → 键盘再试一次
        try { btn.focus(); sendKey(btn, 'ArrowDown', 40); } catch (e) { }
        item = await waitFor(() => groupMenuItem(btn), 1000, 100);
      }
      if (!item) { closeMenus(); await waitMenusClosed(); await closeGroupSelect(); await sleep(300); continue; }
      fireMouseSeq(item);
      d = await waitFor(manageDialog, 4000, 120);
      if (!d && item.isConnected) { try { item.click(); } catch (e) { } d = await waitFor(manageDialog, 2000, 120); }
      if (d) { await sleep(250); return d; }
      closeMenus(); await waitMenusClosed();
    }
    return null;
  }

  async function groupListHas(name) {
    for (let i = 0; i < 3; i++) {
      const lr = await listGroupOptions();
      await sleep(250);
      if (lr.ok) return lr.options.some(o => normGroup(stripCount(o)) === normGroup(name));
      await sleep(600);
    }
    return null;
  }

  async function createGroup(name) {
    name = String(name || '').trim();
    if (!name || name.length > 20) return { ok: false, error: '分组名为空或超过 20 个字符' };
    try {
      const dlg = await openManageDialog();
      if (!dlg) return { ok: false, error: '打不开「管理自选股组合」（「添加自选股」右侧 ⋮ 菜单未弹出）' };
      await sleep(200);
      if (manageRows(dlg).some(r => normGroup(r.name) === normGroup(name))) { await closeDialogs(); return { ok: true, existed: true }; }
      const nb = newGroupBtnIn(dlg);
      if (!nb) { await closeDialogs(); return { ok: false, error: '找不到「新建自选股组合」按钮' }; }
      fireMouseSeq(nb);
      const inp = await waitFor(() => {
        const ds = visDialogs();
        for (let i = ds.length - 1; i >= 0; i--) {
          const d = ds[i];
          if (d === dlg && newGroupBtnIn(d)) continue;
          const x = d.querySelector('input[placeholder*="组合名称"]') ||
            Array.from(d.querySelectorAll('input')).find(el => isVisible(el) && !/checkbox|radio|hidden/i.test(el.type || ''));
          if (x && isVisible(x)) return x;
        }
        return null;
      }, 4000, 100);
      if (!inp) { await closeDialogs(); return { ok: false, error: '点「新建」后未出现名称输入框' }; }
      const cdlg = inp.closest('[role="dialog"], [data-dialog-content]') || inp.parentElement;
      inp.focus();
      setNativeValue(inp, '');
      await sleep(80);
      setNativeValue(inp, name);
      inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: name.slice(-1) }));
      await sleep(250);
      if (inp.value !== name) { await closeDialogs(); return { ok: false, error: `名称写入失败（实际「${inp.value}」）` }; }
      const save = await waitFor(() => {
        const b = Array.from(cdlg.querySelectorAll('button')).filter(isVisible).find(x => SAVE_RE.test(cleanText(x)));
        return b && !b.disabled && b.getAttribute('aria-disabled') !== 'true' ? b : null;
      }, 3000, 100);
      if (!save) { await closeDialogs(); return { ok: false, error: '「储存」按钮不可点' }; }
      fireMouseSeq(save);
      await waitFor(() => !cdlg.isConnected || !isVisible(cdlg) || !cdlg.contains(inp), 5000, 120);
      const errTxt = (cdlg.isConnected && isVisible(cdlg) && cdlg.contains(inp)) ? cleanText(cdlg).slice(0, 120) : '';
      /* ★ 先看仍打开的管理窗口里有没有新行（不用再开关下拉框） */
      let has = errTxt ? null : await waitFor(() => manageHas(name) === true, 3000, 150);
      await sleep(300);
      await closeDialogs();
      await sleep(300);
      if (!has && !errTxt) has = await groupListHas(name);
      if (has) return { ok: true, created: true };
      return { ok: false, error: errTxt ? `新建未生效：${errTxt}` : '新建后分组列表里没出现该分组' };
    } catch (e) {
      try { await closeDialogs(); } catch (_) { }
      return { ok: false, error: String((e && e.message) || e) };
    }
  }

  async function deleteGroup(name, base) {
    base = base || TARGET.group || 'Earning';
    const n = normGroup(name);
    if (!n || n === 'WRONG' || familyIndex(name, base) === 0) return { ok: false, error: `拒绝删除保护分组「${name}」` };
    try {
      if (normGroup(groupName()) === n) {
        const sr = await switchGroup(base);
        if (!sr.ok) return { ok: false, error: '删除前切离该分组失败：' + sr.error };
      }
      const dlg = await openManageDialog();
      if (!dlg) return { ok: false, error: '打不开「管理自选股组合」（「添加自选股」右侧 ⋮ 菜单未弹出）' };
      await sleep(200);
      const rows = manageRows(dlg);
      const row = rows.find(r => normGroup(r.name) === n);
      if (!row) { await closeDialogs(); return { ok: true, missing: true }; }
      if (!row.del) { await closeDialogs(); return { ok: false, error: '该行找不到 🗑 删除按钮' }; }
      const findConfirm = () => {
        const ds = visDialogs();
        for (let i = ds.length - 1; i >= 0; i--) {
          if (ds[i] === dlg && newGroupBtnIn(ds[i])) continue;
          const b = Array.from(ds[i].querySelectorAll('button')).filter(isVisible).find(x => DEL_CONFIRM_RE.test(cleanText(x)));
          if (b) return b;
        }
        return null;
      };
      fireMouseSeq(row.del);
      let btn = await waitFor(findConfirm, 3000, 100);
      if (!btn && row.del.isConnected) { try { row.del.click(); } catch (e) { } btn = await waitFor(findConfirm, 2500, 100); }
      if (!btn) { await closeDialogs(); return { ok: false, error: '点 🗑 后未出现删除确认框' }; }
      const cd = btn.closest('[role="dialog"], [role="alertdialog"], [data-dialog-content]');
      const ct = normGroup(cd ? cleanText(cd) : '');
      if (ct && !ct.includes(n)) {
        const other = rows.find(r => { const rn = normGroup(r.name); return rn !== n && !n.includes(rn) && ct.includes(rn); });
        if (other) { await closeDialogs(); return { ok: false, error: `确认框提到的是「${other.name}」，已取消（防误删）` }; }
      }
      fireMouseSeq(btn);
      await waitFor(() => !cd || !cd.isConnected || !isVisible(cd), 5000, 120);
      const gone = await waitFor(() => manageHas(name) === false, 3000, 150);
      await sleep(300);
      await closeDialogs();
      await sleep(300);
      if (gone) return { ok: true, deleted: true };
      const has = await groupListHas(name);
      if (has === false) return { ok: true, deleted: true };
      return { ok: false, error: has === null ? '删除后无法读取分组列表' : '删除后分组仍在列表中' };
    } catch (e) {
      try { await closeDialogs(); } catch (_) { }
      return { ok: false, error: String((e && e.message) || e) };
    }
  }

  /* ---------------- 备份 ---------------- */
  async function backupCurrentList() {
    renderHud('正在备份当前分组清单（删除前保险）…');
    const buf = await collectWatchlist(n => renderHud(`备份中：已读取 ${n} 只…`));
    const symbols = Object.keys(buf);
    await storeSet({
      [BACKUP_KEY]: { group: groupName(), ts: Date.now(), count: symbols.length, src: SRC.mode, symbols }
    });
    console.log(LOG, `已备份 ${symbols.length} 只到 storage.${BACKUP_KEY}`, symbols);
    return symbols;
  }

  async function guardGroup() {
    const g = groupName();
    if (!g || !job.group || normGroup(g) === normGroup(job.group)) return true;
    renderHud(`⚠ 分组变成了「${g}」，正在自动切回「${job.group}」…`);
    const r = await switchGroup(job.group);
    if (r.ok) return true;
    job.paused = true;
    renderHud(`⚠ 分组已从「${job.group}」变为「${g}」且切回失败，已暂停`);
    await sleep(1200);
    return false;
  }

  /* ---------------- 删除阶段 A：清空整个分组 ---------------- */
  async function runClearAllPhase(skipCountdown) {
    job.phase = 'clear';
    job.clearStartedAt = job.clearStartedAt || Date.now();
    job.clearTotal = (job.cleared || 0) + (dataRowsTotal() || 0);
    if ((dataRowsTotal() || 0) <= 0 && !firstDeletableRow()) return 'done';

    if (!skipCountdown) {
      for (let i = RUN.clearCountdown; i > 0 && !job.stop; i--) {
        renderHud(`⚠️ ${i} 秒后开始清空「${job.group || '当前分组'}」内 ${dataRowsTotal()} 只…点「停止」可取消`);
        await sleep(1000);
      }
    }
    if (job.stop) return 'stopped';

    let consec = 0, guard = 0;
    while (!job.stop && guard++ < 6000) {
      while (job.paused && !job.stop) { renderHud(); await sleep(400); }
      if (job.stop) break;
      if (!(await guardGroup())) continue;
      const left = dataRowsTotal();
      if (left === 0 && !firstDeletableRow()) break;
      const r = await deleteTopRow(job.clearSkip);
      if (r.status === 'empty') break;
      if (r.status === 'removed') {
        job.cleared++; job.current = r.symbol; consec = 0;
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
    await waitMenusClosed();
    job.clearSkip.clear();
    job.removeQueue = [];
    return job.stop ? 'stopped' : 'done';
  }

  /* ---------------- 删除阶段 B：只删指定 symbol（逐只确认 + 收尾复核） ---------------- */
  async function runRemovePhase(list, silentCountdown) {
    job.phase = 'clear';
    job.removeQueue = (list || []).slice();
    job.clearStartedAt = job.clearStartedAt || Date.now();
    job.clearTotal = (job.cleared || 0) + job.removeQueue.length;
    if (!job.removeQueue.length) return 'done';

    if (!silentCountdown) {
      for (let i = RUN.clearCountdown; i > 0 && !job.stop; i--) {
        renderHud(`⚠️ ${i} 秒后从「${job.group}」删除 ${job.removeQueue.length} 只「不在数据源里」的标的…点「停止」可取消`);
        await sleep(1000);
      }
    }
    if (job.stop) return 'stopped';

    const state = Object.create(null);
    const mark = (sym, st, err) => {
      const prev = state[sym];
      if (prev === 'removed') job.cleared--;
      if (prev === 'failed') job.clearFailed = job.clearFailed.filter(f => f.symbol !== sym);
      state[sym] = st;
      if (st === 'removed') job.cleared++;
      if (st === 'failed') { job.clearFailed.push({ symbol: sym, error: err || '未知' }); job.lastError = err || ''; }
    };

    let consec = 0, n = 0;
    while (job.removeQueue.length && !job.stop) {
      while (job.paused && !job.stop) { renderHud(); await sleep(400); }
      if (job.stop) break;
      if (!(await guardGroup())) continue;
      const sym = job.removeQueue[0];
      job.current = sym;
      renderHud();
      const r = await deleteSymbol(sym);
      if (r.status === 'aborted') break;
      job.removeQueue.shift();
      n++;
      if (r.status === 'removed') { mark(sym, 'removed'); consec = 0; }
      else if (r.status === 'missing') { mark(sym, 'missing'); consec = 0; }
      else {
        mark(sym, 'failed', r.error);
        consec++;
        if (consec >= RUN.clearFailAbort) {
          job.paused = true; consec = 0;
          renderHud(`⚠ 连续删除失败（${job.lastError}），已自动暂停，请人工检查`);
          await persist(true);
        }
      }
      renderHud();
      if (n % RUN.checkpointEvery === 0) await persist(true);
      await sleep(RUN.clearDelay + Math.random() * RUN.clearJitter);
    }

    for (let round = 0; round < 2 && !job.stop; round++) {
      const targets = Object.keys(state).filter(s => state[s] !== 'missing');
      if (!targets.length) break;
      renderHud(`复核删除结果（第 ${round + 1} 轮）…`);
      await waitMenusClosed();
      await sleep(800);
      const have = await collectWatchlist();
      const haveSet = new Set(Object.keys(have).map(normKey));
      targets.filter(s => !haveSet.has(normKey(s)) && state[s] === 'failed').forEach(s => mark(s, 'removed'));
      const still = targets.filter(s => haveSet.has(normKey(s)));
      if (!still.length) break;
      for (const sym of still) {
        if (job.stop) break;
        if (!(await guardGroup())) break;
        job.current = sym;
        renderHud(`复核：${sym} 仍在表内，重新删除…`);
        await sleep(800);
        const r = await deleteSymbol(sym);
        if (r.status === 'removed' || r.status === 'missing') mark(sym, 'removed');
        else if (r.status !== 'aborted') mark(sym, 'failed', r.error);
        renderHud();
        await sleep(RUN.clearDelay + Math.random() * RUN.clearJitter);
      }
    }
    await waitMenusClosed();
    return job.stop ? 'stopped' : 'done';
  }

  /* ================= HUD 面板 ================= */
  let hudEl = null;
  let hudMode = 'job';
  const HUD_TITLE = {
    job: '自选股同步(对账)', scan: '自选股行情抓取', diff: '差集比对',
    test: '单只操作自检', task: '🤖 远程添加(来自 Python)'
  };
  const PHASE_LABEL = {
    idle: '待开始', group: '切换/管理分组', diff: '比对中',
    clear: '删除中', add: '添加中', verify: '复核中'
  };

  function buildHud() {
    hudEl = document.createElement('div');
    hudEl.id = 'ft-wl-hud';
    hudEl.innerHTML = `
      <div class="ft-wl-head">
        <span class="ft-wl-title">自选股同步(对账)</span>
        <span class="ft-wl-x" title="隐藏面板">✕</span>
      </div>
      <div class="ft-wl-line ft-wl-job-only" id="ft-wl-group">分组: --</div>
      <div class="ft-wl-line ft-wl-job-only" id="ft-wl-sub"
           style="color:#81A1C1 !important;font-size:11px !important;">--</div>
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

  function renderHud(extra) {
    const el = ensureHud('job');
    const clearing = job.phase === 'clear';
    el.classList.toggle('ft-wl-danger', clearing);
    el.querySelector('.ft-wl-title').textContent = clearing ? '⚠️ 正在删除自选股标的' : HUD_TITLE.job;

    let total, done, stat;
    if (clearing) {
      total = job.clearTotal || 0;
      done = job.cleared || 0;
      stat = `已删 ${done}/${total}  失败 ${job.clearFailed.length}` +
        etaText(done, total, job.clearStartedAt) + (job.paused ? '  ⏸已暂停' : '');
    } else {
      total = job.total || 0;
      done = job.done || 0;
      const p = total ? Math.min(100, Math.round(done / total * 100)) : 0;
      stat = `${done}/${total} (${p}%)  成功 ${job.added}  失败 ${job.failed.length}` +
        etaText(done, total, job.addStartedAt) + (job.paused ? '  ⏸已暂停' : '');
    }
    const pct = total ? Math.min(100, Math.round(done / total * 100)) : 0;

    el.querySelector('#ft-wl-group').textContent =
      `分组: ${job.group || '--'}｜${PHASE_LABEL[job.phase] || job.phase}` +
      (clearing ? '' : `｜第 ${job.pass || 1} 趟`);
    el.querySelector('#ft-wl-sub').textContent =
      (job.family ? `「${job.targetGroup}」系列 每组≤${groupCap()}` : `目标「${job.targetGroup || '-'}」`) +
      `｜源 ${SRC_LABEL[SRC.mode] || SRC.mode}` +
      `｜待删 ${job.removeQueue.length}｜待加 ${job.queue.length}` +
      `｜严格同步 ${job.strictSync ? '开' : '关'}`;
    el.querySelector('#ft-wl-bar-i').style.width = pct + '%';
    el.querySelector('#ft-wl-stat').textContent = stat;
    el.querySelector('#ft-wl-cur').textContent = extra || (job.current ? `当前: ${job.current}` : '');
    el.querySelector('#ft-wl-pause').textContent = job.paused ? '继续' : '暂停';
  }

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
    running: false, paused: false, stop: false, finishing: false,
    phase: 'idle', clearFirst: false, clearOnly: false,
    strictSync: true, targetGroup: 'Earning', originGroup: '',
    group: '', pass: 1, total: 0, done: 0, added: 0,
    failed: [], queue: [], current: '', lastError: '',
    cleared: 0, clearTotal: 0, clearFailed: [], clearSkip: new Set(),
    removeQueue: [], backedUp: false,
    clearStartedAt: 0, addStartedAt: 0,
    startedAt: 0, sinceReload: 0, sinceReopen: 0,
    srcFrom: '', srcCount: 0, haveCount: 0,
    multi: null, skipQuotes: false,
    family: false, famText: '', famCreated: [], famDeleted: []
  };

  const scanState = { running: false, abort: false };

  function syncBusy() {
    window.__FT_AUTOMATION__ = !!(job.running || job.finishing || scanState.running ||
      window.__FT_AGENT_BUSY__ || window.__FT_TRADE_BUSY__);
  }

  async function persist(autoResume) {
    await storeSet({
      [JOB_KEY]: {
        v: 11, phase: job.phase, clearFirst: job.clearFirst, clearOnly: job.clearOnly,
        strictSync: job.strictSync, targetGroup: job.targetGroup, originGroup: job.originGroup,
        group: job.group, pass: job.pass, total: job.total, done: job.done,
        added: job.added, failed: job.failed, queue: job.queue, src: SRC.mode,
        cleared: job.cleared, clearTotal: job.clearTotal, clearFailed: job.clearFailed,
        removeQueue: job.removeQueue, backedUp: job.backedUp, skipQuotes: job.skipQuotes,
        autoResume: !!autoResume && !job.multi && !job.family,   // ★ 多分组任务不做断点续跑
        ts: Date.now()
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
    if (!r.ok || !r.data) {
      throw new Error('桥接服务不可用（' + (r.error || '无响应') + '）。为防止按错误清单增删已中止；' +
        '请先运行 bridge_server.py，或在 popup 把数据源切到「本地备用清单」');
    }
    const d = r.data;
    if (d.status === 'disabled') throw new Error(d.message || `数据源 ${SRC.mode} 已在 bridge_server.py 中停用`);
    if (d.status === 'error') throw new Error(d.message || '数据源返回错误');
    if (!Array.isArray(d.symbols)) throw new Error('数据源返回格式异常（缺少 symbols）');
    return { symbols: d.symbols.slice(), from: d.from || SRC.mode, detail: d.dates || null, empty: d.symbols.length === 0 };
  }

  /* 单分组双向差集（只清空目标分组 / 旧任务续跑使用） */
  async function computeDiff() {
    const src = await getSourceSymbols();
    hudInfo(`来源 ${src.from}：${src.symbols.length} 只，正在抓取「${groupName()}」全表…`);
    let have = await collectWatchlist(n => hudInfo(`已读取 ${n} 只…`));
    let haveSymbols = Object.keys(have);
    if (!haveSymbols.length && !(scanState.abort || (job.running && job.stop))) {
      const g = groupName();
      hudInfo(`「${g || '?'}」没读到任何行，正在确认是「空分组」还是「页面未加载」…`);
      const ce = await confirmGroupEmpty(g, 8000);
      if (ce.rowsAppeared) {
        have = await collectWatchlist(n => hudInfo(`已读取 ${n} 只…`));
        haveSymbols = Object.keys(have);
      }
      if (!haveSymbols.length && !ce.empty) {
        throw new Error(`页面异常：${ce.error || '无法确认分组为空'}（分组「${g || '?'}」，为防按错误数据增删已中止，未做任何修改）`);
      }
    }
    const haveSet = new Set(haveSymbols.map(normKey));
    const srcSet = new Set(src.symbols.map(normKey));
    const missing = src.symbols.filter(s => !haveSet.has(normKey(s)));
    const extra = haveSymbols.filter(s => !srcSet.has(normKey(s)));
    return {
      srcFrom: src.from, srcCount: src.symbols.length, srcDetail: src.detail,
      srcSymbols: src.symbols, haveCount: haveSymbols.length, haveSymbols, missing, extra
    };
  }

  /* ==========================================================================
   *                ★ v11 Earning 系列：读取 → 分配 → 执行
   * ========================================================================*/
  const halted = () => !!(scanState.abort || (job.running && job.stop));

  async function readGroupSymbols(g) {
    const sr = await switchGroup(g);
    if (!sr.ok) throw new Error(`切换到「${g}」失败：${sr.error}（已中止，未做修改）`);
    if (job.running) job.group = groupName() || g;
    await waitGridSettled();
    let buf = await collectWatchlist();
    let syms = Object.keys(buf);
    if (!syms.length && !halted()) {
      const ce = await confirmGroupEmpty(g, 8000);
      if (ce.rowsAppeared) { buf = await collectWatchlist(); syms = Object.keys(buf); }
      if (!syms.length && !ce.empty) throw new Error(`页面异常：${ce.error || '无法确认分组为空'}（分组「${g}」，已中止，未做修改）`);
    }
    return syms;
  }

  function planFamily(srcSyms, base, famNames, contents, cap, strict, wipe) {
    const srcKeys = new Set(srcSyms.map(normKey));
    const byIdx = new Map();
    famNames.forEach(n => { const i = familyIndex(n, base); if (i >= 0 && !byIdx.has(i)) byIdx.set(i, n); });
    const maxIdx = byIdx.size ? Math.max(...byIdx.keys()) : 0;
    const pruning = strict || wipe;
    const K = pruning ? Math.max(1, Math.ceil(srcSyms.length / cap)) : maxIdx + 1;
    const mk = (i) => {
      const ex = byIdx.has(i);
      const name = ex ? byIdx.get(i) : familyName(base, i);
      return { index: i, name, exists: ex, cur: ex ? (contents[name] || []).slice() : [], keep: [], remove: [], add: [] };
    };
    const slots = [], taken = new Set();
    for (let i = 0; i < K; i++) {
      const s = mk(i);
      s.cur.forEach(sym => {
        const k = normKey(sym);
        if (wipe) s.remove.push(sym);
        else if (!pruning) { s.keep.push(sym); taken.add(k); }
        else if (srcKeys.has(k) && !taken.has(k) && s.keep.length < cap) { s.keep.push(sym); taken.add(k); }
        else s.remove.push(sym);
      });
      slots.push(s);
    }
    const pool = [];
    srcSyms.forEach(sym => { const k = normKey(sym); if (!taken.has(k)) { taken.add(k); pool.push(sym); } });
    for (let i = 0; pool.length; i++) {
      if (i >= slots.length) {
        if (slots.length >= (CFG.maxFamilyGroups || 15)) break;
        slots.push(mk(slots.length));
      }
      const s = slots[i];
      const free = cap - s.keep.length;
      if (free > 0) s.add = s.add.concat(pool.splice(0, free));
    }
    const surplus = pruning
      ? Array.from(byIdx.entries()).filter(([i]) => i >= 1 && i >= slots.length).sort((a, b) => a[0] - b[0]).map(([, n]) => n)
      : [];
    const used = slots.filter(s => s.exists || s.add.length);
    const text = used.map(s => `${s.name}${s.exists ? '' : '(新建)'} ${s.keep.length + s.add.length}只(+${s.add.length}/-${s.remove.length})`).join('｜') +
      (surplus.length ? `｜删除分组 ${surplus.join('/')}` : '');
    return {
      slots, surplus, overflow: pool, text,
      addTotal: slots.reduce((a, s) => a + s.add.length, 0),
      removeTotal: slots.reduce((a, s) => a + s.remove.length, 0),
      createTotal: slots.filter(s => !s.exists && s.add.length).length
    };
  }

  async function computeFamilyPlan(opts) {
    const base = opts.base || TARGET.group || 'Earning';
    const cap = groupCap();
    hudInfo('正在读取数据源…');
    const src = await getSourceSymbols();
    hudInfo(`来源 ${src.from}：${src.symbols.length} 只，正在读取分组列表…`);
    const lr = await listGroupOptions();
    await sleep(300);
    if (!lr.ok) throw new Error('读不到页面分组列表（' + (lr.error || '下拉框没有选项') + '），已中止未修改');
    const names = Array.from(new Set((lr.options || []).map(stripCount).filter(Boolean)));
    const fam = names.filter(n => familyIndex(n, base) >= 0).sort((a, b) => familyIndex(a, base) - familyIndex(b, base));
    const cur = normGroup(groupName());
    const order = fam.slice().sort((a, b) => (normGroup(b) === cur) - (normGroup(a) === cur));   // 当前分组先读，省一次切换
    const contents = {};
    for (const g of order) {
      if (halted()) throw new Error('已停止');
      hudInfo(`读取「${g}」现有标的…`);
      contents[g] = await readGroupSymbols(g);
    }
    const P = planFamily(src.symbols, base, fam, contents, cap, !!opts.strict, !!opts.wipe);
    return Object.assign(P, {
      src, fam, contents, cap, base,
      haveCount: Object.values(contents).reduce((a, x) => a + x.length, 0)
    });
  }

  async function addIntoGroup(s) {
    job.phase = 'add';
    job.addStartedAt = job.addStartedAt || Date.now();
    try {
      const inp = await ensureInput();
      assertSafeInput(inp);
      pressEscape();
      await sleep(200);
    } catch (e) {
      const err = '输入框自检失败: ' + String((e && e.message) || e);
      s.add.forEach(x => job.failed.push({ symbol: x, error: err }));
      job.done += s.add.length; job.lastError = err;
      return;
    }
    const state = Object.create(null);
    const mark = (sym, ok, err) => {
      const prev = state[sym];
      if (prev === 'ok') job.added--;
      if (prev === 'fail') job.failed = job.failed.filter(f => normKey(f.symbol) !== normKey(sym));
      state[sym] = ok ? 'ok' : 'fail';
      if (ok) job.added++;
      else { job.failed.push({ symbol: sym, error: err || '未知' }); job.lastError = err || ''; }
    };
    let consec = 0;
    const runList = async (list, counting) => {
      job.queue = list.slice();
      while (job.queue.length && !job.stop) {
        while (job.paused && !job.stop) { renderHud(); await sleep(400); }
        if (job.stop) break;
        if (!(await guardGroup())) continue;
        const sym = job.queue[0];
        job.current = sym;
        renderHud();
        const r = await addOneSymbol(sym);
        if (r.status === 'aborted') break;
        job.queue.shift();
        if (counting) job.done++;
        mark(sym, r.status === 'added', r.error);
        consec = r.status === 'added' ? 0 : consec + 1;
        if (consec >= RUN.consecutiveFailAbort) {
          job.paused = true; consec = 0;
          renderHud(`⚠ 连续失败过多（最后: ${job.lastError}），已自动暂停，请人工检查`);
        }
        renderHud();
        await sleep(RUN.perSymbolDelay + Math.random() * RUN.jitter);
      }
      try { pressEscape(); } catch (e) { }
      cleanNavSearch();
    };
    await runList(s.add, true);
    for (let pass = 2; pass <= RUN.maxPasses && !job.stop; pass++) {
      job.phase = 'verify'; job.pass = pass;
      renderHud(`复核「${s.name}」…`);
      await sleep(500);
      const have = new Set(Object.keys(await collectWatchlist()).map(normKey));
      s.add.forEach(x => { if (have.has(normKey(x)) && state[x] !== 'ok') mark(x, true); });
      const miss = s.add.filter(x => !have.has(normKey(x)));
      if (!miss.length) break;
      job.phase = 'add';
      renderHud(`「${s.name}」仍缺 ${miss.length} 只，补加…`);
      await runList(miss, false);
    }
    job.queue = [];
    job.pass = 1;
  }

  async function runFamilyPipeline() {
    job.family = true;
    RUN.reloadEvery = 0; RUN.clearReloadEvery = 0;
    const base = job.targetGroup || TARGET.group || 'Earning';
    job.targetGroup = base;
    job.phase = 'diff';
    renderHud(`正在比对「${base}」系列分组与数据源…`);
    const P = await computeFamilyPlan({ base, strict: job.strictSync, wipe: job.clearFirst });
    if (job.stop) return finishJob();
    job.srcFrom = P.src.from; job.srcCount = P.src.symbols.length; job.haveCount = P.haveCount;
    job.famText = P.text;
    job.total = P.addTotal;
    renderHud(`源 ${P.src.from}：${P.src.symbols.length} 只｜每组≤${P.cap}｜${P.text}`);
    await sleep(900);

    if (P.overflow.length) {
      P.overflow.forEach(x => job.failed.push({ symbol: x, error: `超出 ${CFG.maxFamilyGroups} 个分组上限，未写入` }));
      toast(`⚠ 有 ${P.overflow.length} 只超出分组上限未写入`);
    }
    if (!P.addTotal && !P.removeTotal && !P.createTotal && !P.surplus.length) {
      toast(`✅ 「${base}」系列已与数据源完全一致，无需任何改动`);
      renderHud(`✅ 已一致：${P.text || '空'}，未做任何点击`);
      return finishJob();
    }

    if (P.removeTotal || P.surplus.length) {
      try { await storeSet({ [BACKUP_KEY]: buildMultiBackup(P.contents) }); job.backedUp = true; } catch (e) { }
      if (P.src.symbols.length === 0) toast('⚠ 数据源在目标日期无数据（不回退）→ 将清空 Earning 系列');
      for (let i = RUN.clearCountdown; i > 0 && !job.stop; i--) {
        renderHud(`⚠️ ${i} 秒后：删除 ${P.removeTotal} 只多余标的` +
          (P.surplus.length ? `、删除分组 ${P.surplus.join('/')}` : '') + '…点「停止」可取消（已备份）');
        await sleep(1000);
      }
      if (job.stop) return finishJob();
    }

    /* ① 新建缺少的分组 */
    for (const s of P.slots) {
      if (job.stop) break;
      if (s.exists || !s.add.length) continue;
      job.phase = 'group';
      renderHud(`新建分组「${s.name}」…`);
      const r = await createGroup(s.name);
      if (r.ok) { job.famCreated.push(s.name); s.exists = true; }
      else {
        s.skip = true; job.lastError = r.error;
        s.add.forEach(x => job.failed.push({ symbol: x, error: `新建分组「${s.name}」失败：${r.error}` }));
        job.done += s.add.length;
        toast(`❌ 新建分组「${s.name}」失败：${r.error}`);
      }
    }

    /* ② 逐组：删多余 → 补缺失 → 复核 */
    for (const s of P.slots) {
      if (job.stop) break;
      if (s.skip || !s.exists || (!s.remove.length && !s.add.length)) continue;
      job.phase = 'group'; job.group = s.name;
      renderHud(`切到「${s.name}」…`);
      const sr = await switchGroup(s.name);
      if (!sr.ok) {
        s.add.forEach(x => job.failed.push({ symbol: x, error: `切换到「${s.name}」失败` }));
        s.remove.forEach(x => job.clearFailed.push({ symbol: x, error: `切换到「${s.name}」失败` }));
        job.done += s.add.length; job.lastError = sr.error;
        continue;
      }
      job.group = groupName() || s.name;
      await waitGridSettled();
      if (s.remove.length) {
        const r = await runRemovePhase(s.remove, true);
        if (r === 'stopped') break;
      }
      if (s.add.length && !job.stop) await addIntoGroup(s);
    }

    /* ③ 删除用不上的分组（永不删 base / 非系列分组） */
    if (!job.stop && P.surplus.length) {
      job.phase = 'group';
      if (familyIndex(groupName(), base) !== 0) await switchGroup(base);
      for (const g of P.surplus) {
        if (job.stop) break;
        if (familyIndex(g, base) < 1) continue;
        renderHud(`删除用不上的分组「${g}」…`);
        const r = await deleteGroup(g, base);
        if (r.ok) {
          job.famDeleted.push(g);
          bg({ action: 'FT_WL_MEMBERSHIP', payload: { group: g, drop: true } });
        } else {
          job.clearFailed.push({ symbol: `[${g}]`, error: r.error || '删除分组失败' });
          job.lastError = r.error || '';
        }
      }
    }
    return finishJob();
  }

  function familyDiffResponse(P) {
    const adds = [].concat(...P.slots.map(s => s.add));
    const rms = [].concat(...P.slots.map(s => s.remove));
    return {
      ok: true, srcFrom: P.src.from, srcCount: P.src.symbols.length, srcDetail: P.src.detail,
      srcSymbols: P.src.symbols.slice(0, 60), haveCount: P.haveCount,
      missing: adds.length, extraCount: rms.length, extraSample: rms.slice(0, 20), sample: adds.slice(0, 20),
      group: groupName(), targetGroup: P.base, onTarget: isFamily(groupName(), P.base),
      cap: P.cap, planText: P.text, surplus: P.surplus, overflow: P.overflow.length
    };
  }

  /* ================= 一键 pipeline ================= */
  function resetJob(opts) {
    opts = opts || {};
    job.running = true; job.paused = false; job.stop = false; job.finishing = false;
    job.phase = 'idle';
    job.clearFirst = !!opts.clearFirst;
    job.clearOnly = !!opts.clearOnly;
    job.strictSync = (opts.strictSync !== undefined) ? !!opts.strictSync : !!TARGET.strictSync;
    job.targetGroup = (opts.targetGroup || TARGET.group || '').trim();
    job.originGroup = groupName();
    job.group = job.originGroup;
    job.pass = 1; job.total = 0; job.done = 0; job.added = 0;
    job.failed = []; job.queue = []; job.current = ''; job.lastError = '';
    job.cleared = 0; job.clearTotal = 0; job.clearFailed = []; job.clearSkip = new Set();
    job.removeQueue = []; job.backedUp = false;
    job.clearStartedAt = 0; job.addStartedAt = 0;
    job.startedAt = Date.now(); job.sinceReload = 0; job.sinceReopen = 0;
    job.srcFrom = ''; job.srcCount = 0; job.haveCount = 0;
    job.multi = null;
    job.skipQuotes = !!opts.skipQuotes;
    job.family = false; job.famText = ''; job.famCreated = []; job.famDeleted = [];
    RUN = Object.assign({}, CFG);
    scanState.abort = false;
    syncBusy();
  }

  async function startJob(opts) {
    opts = opts || {};
    if (!isWatchlistPage()) return { ok: false, error: '当前不在 /app/watchlist 页面' };
    if (job.running || job.finishing) return { ok: false, error: '任务已在运行中' };
    if (window.__FT_TRADE_BUSY__) return { ok: false, error: '快速交易进行中，请稍后' };
    if (scanState.running) return { ok: false, error: '行情抓取进行中，请稍后再启动' };

    const pageReady = document.querySelector('.ag-root, [role="grid"], .ag-body-viewport, main, [data-select-trigger]');
    if (!pageReady && !findAddButton()) {
      return { ok: false, error: '未识别到自选股页面元素，请等页面加载完成后重试' };
    }

    resetJob(opts);
    cleanNavSearch();
    ensureHud('job');
    renderHud('正在启动…');

    const runner = job.clearOnly ? runPipeline({}) : runFamilyPipeline();
    runner.catch(e => {
      job.lastError = String((e && e.message) || e);
      renderHud('❌ ' + job.lastError);
      toast('❌ ' + job.lastError);
      finishJob();
    });

    return {
      ok: true, started: true, group: job.group,
      targetGroup: job.targetGroup, strictSync: job.strictSync,
      clearFirst: job.clearFirst, clearOnly: job.clearOnly,
      family: !job.clearOnly, cap: groupCap(), rows: dataRowsTotal()
    };
  }

  /* 单分组 pipeline：只清空目标分组 / 旧版断点续跑 */
  async function runPipeline(opts) {
    opts = opts || {};
    job.phase = 'group';
    if (!job.originGroup) job.originGroup = groupName();
    const want = job.targetGroup;
    if (want && normGroup(groupName()) !== normGroup(want)) {
      renderHud(`正在从「${job.originGroup || '?'}」切换到目标分组「${want}」…`);
      const sr = await switchGroup(want);
      if (!sr.ok) {
        job.lastError = sr.error || '切换分组失败';
        renderHud('❌ ' + job.lastError);
        toast('❌ ' + job.lastError);
        return finishJob();
      }
      await waitGridSettled();
    }
    job.group = groupName() || want;
    if (job.stop) return finishJob();

    if (!job.clearOnly) {
      const addBtn = await waitFor(findAddButton, 6000, 200);
      if (!addBtn) {
        job.lastError = `分组「${job.group}」里找不到「添加自选股」按钮（该分组可能不支持添加）`;
        renderHud('❌ ' + job.lastError);
        toast('❌ ' + job.lastError);
        return finishJob();
      }
    }
    renderHud(`已定位到分组「${job.group}」（表内 ${dataRowsTotal()} 只）`);
    await sleep(300);

    if (opts.resume && (job.queue.length || job.removeQueue.length)) {
      prepareRun(job.queue.length);
      renderHud(`续跑：待删 ${job.removeQueue.length}｜待加 ${job.queue.length}`);
    } else {
      job.phase = 'diff';
      renderHud('正在读取数据源并比对差集…');
      const d = await computeDiff();
      if (job.stop) return finishJob();
      job.srcFrom = d.srcFrom; job.srcCount = d.srcCount; job.haveCount = d.haveCount;
      if (job.clearOnly) { job.queue = []; job.removeQueue = d.haveSymbols.slice(); }
      else if (job.clearFirst) { job.queue = d.srcSymbols.slice(); job.removeQueue = d.haveSymbols.slice(); }
      else { job.queue = d.missing.slice(); job.removeQueue = job.strictSync ? d.extra.slice() : []; }
      job.total = job.queue.length;
      prepareRun(job.total);
      renderHud(`源 ${d.srcFrom}: ${d.srcCount} 只｜「${job.group}」现有 ${d.haveCount}` +
        `｜待删 ${job.removeQueue.length}｜待加 ${job.total}`);
      await sleep(700);
      if (!job.removeQueue.length && !job.queue.length) {
        toast(`✅ 分组「${job.group}」无需任何改动`);
        renderHud(`✅ 已一致：${d.haveCount} 只，未做任何点击`);
        return finishJob();
      }
    }

    if (job.removeQueue.length && !job.stop) {
      if (!job.backedUp) {
        try { await backupCurrentList(); job.backedUp = true; }
        catch (e) { log('备份失败（继续执行）', e); }
      }
      if (job.stop) return finishJob();
      const wipeAll = (job.clearFirst || job.clearOnly);
      const r = wipeAll ? await runClearAllPhase() : await runRemovePhase(job.removeQueue);
      if (r === 'reload') return;
      if (r === 'stopped') return finishJob();
      renderHud(`✅ 删除阶段完成：删除 ${job.cleared} 只，失败 ${job.clearFailed.length}`);
      await sleep(700);
    }
    if (job.clearOnly || job.stop) return finishJob();

    job.phase = 'add';
    job.addStartedAt = job.addStartedAt || Date.now();
    if (job.queue.length) {
      try {
        const inp = await ensureInput();
        assertSafeInput(inp);
        pressEscape();
        await sleep(200);
      } catch (e) {
        job.lastError = '输入框自检失败: ' + String((e && e.message) || e);
        renderHud('❌ ' + job.lastError);
        return finishJob();
      }
    }
    await persist(true);
    const r = await runAddLoop();
    if (r === 'reload') return;
    return finishJob();
  }

  async function runAddLoop() {
    let consecutiveFail = 0;
    for (; ;) {
      job.phase = 'add';
      while (job.queue.length && !job.stop) {
        while (job.paused && !job.stop) { renderHud(); await sleep(400); }
        if (job.stop) break;
        if (!(await guardGroup())) continue;
        const sym = job.queue[0];
        job.current = sym;
        renderHud();
        const r = await addOneSymbol(sym);
        if (r.status === 'aborted') break;
        job.queue.shift();
        job.done++; job.sinceReload++; job.sinceReopen++;
        if (r.status === 'added') { job.added++; consecutiveFail = 0; }
        else {
          job.failed.push({ symbol: sym, error: r.error || '未知' });
          job.lastError = r.error || '';
          consecutiveFail++;
        }
        renderHud();
        if (job.done % RUN.checkpointEvery === 0) await persist(true);
        if (consecutiveFail >= RUN.consecutiveFailAbort) {
          job.paused = true; consecutiveFail = 0;
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

      job.phase = 'verify';
      renderHud('本趟结束，正在复核分组与数据源是否一致…');
      try {
        if (!(await guardGroup())) continue;
        const d = await computeDiff();
        const extra = job.strictSync ? d.extra : [];
        if (!d.missing.length && !extra.length) { renderHud('✅ 复核通过'); break; }
        job.pass++;
        if (extra.length) {
          const rr = await runRemovePhase(extra, true);
          if (rr === 'stopped') break;
        }
        if (!d.missing.length) { if (job.pass >= RUN.maxPasses) break; continue; }
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
    job.finishing = true;
    job.running = false;
    job.current = '';
    job.phase = 'idle';
    syncBusy();
    try {
      await persist(false);
      const bits = [];
      if (job.multi) bits.push(`清空分组 ${job.multi.join('/')}`);
      if (job.family && job.famText) bits.push(job.famText);
      if (job.famCreated.length) bits.push(`新建分组 ${job.famCreated.join('/')}`);
      if (job.famDeleted.length) bits.push(`删除分组 ${job.famDeleted.join('/')}`);
      if (job.cleared > 0 || job.clearFailed.length) bits.push(`删除 ${job.cleared}（失败 ${job.clearFailed.length}）`);
      if (!job.clearOnly) bits.push(`新增 ${job.added}（失败 ${job.failed.length}）`);
      const summary = bits.join(' ｜ ') || '无操作';
      renderHud(job.stop ? '⏹ 已手动停止：' + summary : `✅ 完成：${summary}`);
      toast(job.stop ? '⏹ 自选股任务已停止' : `✅ 自选股任务完成：${summary}`);

      if (!job.stop && !job.clearOnly && !job.skipQuotes) { try { await fullScanQuotes(true); } catch (e) { } }
      else if (!job.stop && job.clearOnly && !job.multi) { try { await collectWatchlist(); } catch (e) { } }

      try {
        const originGone = job.famDeleted.some(g => normGroup(g) === normGroup(job.originGroup));
        if (TARGET.backToOrigin && job.originGroup && !originGone && normGroup(groupName()) !== normGroup(job.originGroup)) {
          renderHud(`正在切回原分组「${job.originGroup}」…`);
          await switchGroup(job.originGroup);
          renderHud(`✅ ${summary}｜已切回「${job.originGroup}」`);
        }
      } catch (e) { log('切回原分组失败', e); }
    } finally {
      job.finishing = false;
      syncBusy();
    }
  }

  /* ================= 一键清空非保留分组（Earning 系列整体保留） ================= */
  const NOT_A_GROUP_RE = /新建|创建|管理|编辑|重命名|删除|new|create|manage|edit|rename|delete/i;
  const ALWAYS_KEEP = ['Earning', 'Wrong'];

  function snapshotEmpty(g) {
    try { const M = window.__FT_WL_MEMBER__; if (M && g) M.snapshot(g, [], true, 'clear_groups'); } catch (e) { }
  }
  function buildMultiBackup(b) {
    const all = [].concat(...Object.values(b));
    return { group: Object.keys(b).join(' + '), ts: Date.now(), count: all.length, src: 'clear_groups', symbols: all, groups: b };
  }

  async function startClearGroups(opts) {
    opts = opts || {};
    if (!isWatchlistPage()) return { ok: false, error: '当前不在 /app/watchlist 页面' };
    if (job.running || job.finishing) return { ok: false, error: '已有自选股任务在运行中' };
    if (scanState.running || window.__FT_AGENT_BUSY__ || window.__FT_TRADE_BUSY__) {
      return { ok: false, error: '行情抓取/远程任务/交易进行中，请稍后' };
    }
    const keep = Array.from(new Set(ALWAYS_KEEP.concat(Array.isArray(opts.keep) ? opts.keep : [])
      .map(s => String(s).trim()).filter(Boolean)));
    const keepN = new Set(keep.map(normGroup));
    const lr = await listGroupOptions();
    await sleep(300);
    if (!lr.ok) return { ok: false, error: '读不到页面分组列表：' + (lr.error || '下拉框没有选项') };
    const all = Array.from(new Set((lr.options || []).map(stripCount).filter(Boolean)));
    const famKeep = all.filter(n => isFamily(n, TARGET.group));
    const groups = all.filter(n => !NOT_A_GROUP_RE.test(n) && !keepN.has(normGroup(n)) && !isFamily(n, TARGET.group));
    const keepAll = Array.from(new Set(keep.concat(famKeep)));
    if (!groups.length) return { ok: true, started: false, keep: keepAll, groups: [], message: '除保留分组外没有其它分组，无需清空' };

    resetJob({ clearOnly: true, targetGroup: groups[0], strictSync: false });
    job.multi = groups.slice();
    RUN.clearReloadEvery = 0;
    ensureHud('job');
    renderHud(`准备清空 ${groups.length} 个分组：${groups.join(' / ')}`);
    runMultiClear(groups, keepAll).catch(e => {
      job.lastError = String((e && e.message) || e);
      renderHud('❌ ' + job.lastError);
      finishJob();
    });
    return { ok: true, started: true, groups, keep: keepAll };
  }

  async function runMultiClear(groups, keep) {
    for (let i = RUN.clearCountdown; i > 0 && !job.stop; i--) {
      renderHud(`⚠️ ${i} 秒后依次清空：${groups.join(' / ')}（保留 ${keep.join(' / ')}）…点「停止」可取消`);
      await sleep(1000);
    }
    const backups = {};
    for (let gi = 0; gi < groups.length && !job.stop; gi++) {
      const g = groups[gi];
      job.phase = 'group';
      job.targetGroup = g;
      renderHud(`(${gi + 1}/${groups.length}) 切换到「${g}」…`);
      const sr = await switchGroup(g);
      if (!sr.ok) {
        job.clearFailed.push({ symbol: `[${g}]`, error: sr.error || '切换失败' });
        job.lastError = sr.error || '';
        continue;
      }
      job.group = groupName() || g;
      await waitGridSettled();
      await sleep(300);
      if ((dataRowsTotal() || 0) === 0 && !firstDeletableRow()) { snapshotEmpty(job.group); continue; }
      try {
        renderHud(`(${gi + 1}/${groups.length}) 备份「${job.group}」…`);
        backups[job.group] = Object.keys(await collectWatchlist());
        await storeSet({ [BACKUP_KEY]: buildMultiBackup(backups) });
      } catch (e) { log('备份失败', e); }
      if (job.stop) break;
      const r = await runClearAllPhase(true);
      if (r === 'stopped') break;
      if ((dataRowsTotal() || 0) === 0) snapshotEmpty(job.group);
    }
    return finishJob();
  }

  async function resumeJob(saved) {
    resetJob({
      clearFirst: saved.clearFirst, clearOnly: saved.clearOnly,
      strictSync: saved.strictSync, targetGroup: saved.targetGroup || TARGET.group
    });
    job.originGroup = saved.originGroup || job.originGroup;
    job.group = saved.group || groupName();
    job.pass = saved.pass || 1;
    job.queue = saved.queue || [];
    job.removeQueue = saved.removeQueue || [];
    job.total = saved.total || job.queue.length;
    job.done = saved.done || 0;
    job.added = saved.added || 0;
    job.failed = saved.failed || [];
    job.cleared = saved.cleared || 0;
    job.clearTotal = saved.clearTotal || 0;
    job.clearFailed = saved.clearFailed || [];
    job.backedUp = !!saved.backedUp;
    cleanNavSearch();
    ensureHud('job');
    renderHud('已从上次进度续跑');
    runPipeline({ resume: true }).catch(e => {
      job.lastError = String((e && e.message) || e);
      renderHud('❌ ' + job.lastError);
      finishJob();
    });
  }

  /* ================= ★ v11 变更% 快照：覆盖整个 Earning 系列 ================= */
  async function fullScanQuotes(silent) {
    if (!isWatchlistPage()) return { ok: false, error: '当前不在 /app/watchlist 页面' };
    if (!silent) await waitFor(() => !job.finishing, 30000, 300);
    if (!silent && job.running) return { ok: false, error: '批量任务进行中，请先停止后再抓行情' };
    if (!silent && window.__FT_TRADE_BUSY__) return { ok: false, error: '快速交易进行中，请稍后' };
    if (scanState.running) return { ok: false, error: '已有抓取任务在进行中' };

    scanState.running = true;
    scanState.abort = false;
    syncBusy();
    const base = TARGET.group || 'Earning';
    const origin = groupName();
    let switched = false;
    const say = (t) => { if (!silent) renderScan(t, 'scan'); };
    try {
      say('读取 Earning 系列分组列表…');
      let fam = [];
      const lr = await listGroupOptions();
      await sleep(250);
      if (lr.ok) fam = Array.from(new Set(lr.options.map(stripCount).filter(Boolean))).filter(n => isFamily(n, base));
      if (!fam.length) fam = [base];
      const cur = normGroup(origin);
      fam.sort((a, b) => ((normGroup(b) === cur) - (normGroup(a) === cur)) || (familyIndex(a, base) - familyIndex(b, base)));

      const all = Object.create(null);
      const per = [];
      for (const g of fam) {
        if (scanState.abort) break;
        if (normGroup(groupName()) !== normGroup(g)) {
          say(`切换到「${g}」…`);
          const sr = await switchGroup(g);
          if (!sr.ok) {
            const err = `页面异常：切换到「${g}」失败：${sr.error}（为防写入错误数据，已中止）`;
            say('❌ ' + err);
            return { ok: false, error: err, pageError: true };
          }
          switched = true;
          await waitGridSettled();
        }
        say(`抓取「${g}」的「变更%」…（请勿操作本标签页）`);
        let buf = await collectWatchlist(n => say(`「${g}」已抓 ${n} 只…`));
        if (Object.keys(buf).length && Object.values(buf).some(r => !/%/.test(r.change_pct || ''))) {
          await sleep(1200);
          Object.assign(buf, await collectWatchlist());
        }
        let n = Object.keys(buf).length;
        if (!n && !scanState.abort) {
          const ce = await confirmGroupEmpty(g, 7000);
          if (ce.rowsAppeared) { buf = await collectWatchlist(); n = Object.keys(buf).length; }
          if (!n && !ce.empty) {
            const err = `页面异常：${ce.error || '无法确认分组为空'}（分组「${g}」，为防误清本机数据已中止，未写入）`;
            say('❌ ' + err);
            if (!silent) toast('❌ ' + err);
            return { ok: false, error: err, pageError: true, count: 0, group: g };
          }
        }
        const gc = stripCount(groupName() || g);
        Object.keys(buf).forEach(s => { if (!all[s]) all[s] = Object.assign({}, buf[s], { group: gc }); });
        per.push({ group: gc, count: n });
      }
      if (scanState.abort) {
        say('⏹ 已中止（未写入本机）');
        return { ok: false, error: '用户中止', count: Object.keys(all).length };
      }

      const total = Object.keys(all).length;
      const resp = await bg({ action: 'FT_SYNC_WATCHLIST', payload: all, overwrite: true, group: base, groups: per.map(p => p.group) });
      if (!resp.ok) {
        const err = `桥接异常：写入本机失败（${resp.error || '无响应'}），bridge_server.py 是否在运行？`;
        say('❌ ' + err);
        if (!silent) toast('❌ ' + err);
        return { ok: false, error: err, bridgeError: true, count: total, group: base, server: resp };
      }
      const gtxt = per.map(p => `${p.group}:${p.count}`).join(' / ');
      if (!total) {
        const empty = await probeSourceCount();
        let message;
        if (empty.ok && empty.count === 0) message = `「${base}」系列为空：数据源（${empty.from}）在目标日期没有标的 → 已清空本机行情 JSON`;
        else if (empty.ok) message = `⚠ 「${base}」系列为空，但数据源有 ${empty.count} 只（一键同步可能未完成）→ 已按页面实际情况清空本机 JSON`;
        else message = `「${base}」系列为空（数据源核对失败：${empty.error}）→ 已按页面实际情况清空本机 JSON`;
        say('✅ ' + message);
        if (!silent) toast('✅ ' + message.slice(0, 90));
        return { ok: true, count: 0, empty: true, srcOk: !!empty.ok, srcCount: empty.ok ? empty.count : null, message, server: resp, group: base, groups: per };
      }
      say(`✅ 已覆盖写入 ${total} 只行情（${gtxt}）`);
      if (!silent) toast(`✅ 已保存 ${total} 只「变更%」（${gtxt}）`);
      return { ok: true, count: total, server: resp, group: gtxt, groups: per };
    } finally {
      if (switched && !silent && TARGET.backToOrigin && origin && normGroup(groupName()) !== normGroup(origin)) {
        try { renderScan(`正在切回原分组「${origin}」…`); await switchGroup(origin); } catch (e) { }
      }
      scanState.running = false;
      syncBusy();
    }
  }

  let autoTimer = null;
  function autoTickSoon(delay = 2500) {
    if (!AUTO_WATCHLIST) return;
    clearTimeout(autoTimer);
    autoTimer = setTimeout(async () => {
      if (!AUTO_WATCHLIST || !isWatchlistPage() || job.running || scanState.running || window.__FT_AUTOMATION__) return;
      const g = groupName();
      if (!g || !isFamily(g, TARGET.group)) return;     // 只在 Earning 系列分组时增量写
      const buf = scrapeRows(Object.create(null));
      if (!Object.keys(buf).length) return;
      const gc = stripCount(g);
      Object.keys(buf).forEach(s => { buf[s].group = gc; });
      const r = await bg({ action: 'FT_SYNC_WATCHLIST', payload: buf, overwrite: false, group: gc });
      log('自动增量同步自选股', Object.keys(buf).length, r.ok ? 'ok' : r.error);
    }, delay);
  }

  /* ================= 设置 & 引导 ================= */
  function loadSettings() {
    chrome.storage.local.get(
      ['ftDebug', 'ftAutoWatchlist', 'ftWlCfg', 'ftWlSource', 'ftWlBack', 'ftWlAhead',
        'ftWlTargetGroup', 'ftWlStrictSync', 'ftWlRestoreGroup', 'ftWlGroupCap'],
      (res) => {
        DEBUG = !!res.ftDebug;
        AUTO_WATCHLIST = res.ftAutoWatchlist === true;
        if (res.ftWlCfg && typeof res.ftWlCfg === 'object') Object.assign(CFG, res.ftWlCfg);
        const cap = parseInt(res.ftWlGroupCap, 10);
        if (Number.isFinite(cap) && cap > 0) CFG.groupCap = cap;
        SRC.mode = res.ftWlSource || 'earnings';
        const b = parseInt(res.ftWlBack, 10);
        const a = parseInt(res.ftWlAhead, 10);
        SRC.back = Number.isFinite(b) ? Math.max(0, b) : 1;
        SRC.ahead = Number.isFinite(a) ? Math.max(0, a) : 0;
        let tg = (res.ftWlTargetGroup === undefined || res.ftWlTargetGroup === null ||
          String(res.ftWlTargetGroup).trim() === '') ? 'Earning' : String(res.ftWlTargetGroup).trim();
        if (normGroup(tg) === 'ALL') tg = 'Earning';
        TARGET.group = tg;
        TARGET.strictSync = res.ftWlStrictSync !== false;
        TARGET.backToOrigin = res.ftWlRestoreGroup !== false;
        if (!job.running) RUN = Object.assign({}, CFG);
        log('设置: AUTO =', AUTO_WATCHLIST, 'SRC =', SRC, 'TARGET =', TARGET, 'CAP =', groupCap());
      });
  }
  chrome.storage.onChanged.addListener((c, area) => {
    if (area !== 'local') return;
    if (c.ftDebug || c.ftAutoWatchlist || c.ftWlCfg || c.ftWlSource || c.ftWlBack ||
      c.ftWlAhead || c.ftWlTargetGroup || c.ftWlStrictSync || c.ftWlRestoreGroup || c.ftWlGroupCap) loadSettings();
  });

  async function bootstrap() {
    loadSettings();
    if (!isWatchlistPage()) return;
    await waitFor(() => (document.querySelector('.ag-root, [role="grid"], main') &&
      (findAddButton() || document.querySelector('[role="grid"]') || emptyStateEl())), 25000, 400);

    const st = await storeGet([JOB_KEY]);
    const saved = st[JOB_KEY];
    const hasWork = saved && saved.autoResume &&
      ((Array.isArray(saved.queue) && saved.queue.length) ||
        (Array.isArray(saved.removeQueue) && saved.removeQueue.length) ||
        saved.phase === 'clear');
    if (hasWork) {
      ensureHud('job');
      job.group = saved.group; job.total = saved.total; job.done = saved.done;
      job.added = saved.added; job.failed = saved.failed || []; job.pass = saved.pass || 1;
      job.cleared = saved.cleared || 0; job.clearTotal = saved.clearTotal || 0;
      job.queue = saved.queue || []; job.removeQueue = saved.removeQueue || [];
      job.targetGroup = saved.targetGroup || TARGET.group;
      job.phase = saved.phase || 'add';
      const what = (saved.removeQueue && saved.removeQueue.length)
        ? `删除（剩 ${saved.removeQueue.length} 只）` : `添加（剩 ${(saved.queue || []).length} 只）`;
      for (let i = 5; i > 0; i--) {
        renderHud(`检测到未完成任务：${what}，目标分组「${job.targetGroup}」，${i} 秒后自动续跑…点「停止」可取消`);
        await sleep(1000);
        if (job.running) return;
        if (job.stop) {
          await storeSet({ [JOB_KEY]: Object.assign({}, saved, { autoResume: false }) });
          renderHud('⏹ 已取消续跑');
          job.stop = false;
          return;
        }
      }
      if (job.running) return;
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
        targetGroup: TARGET.group, strictSync: TARGET.strictSync, groupCap: groupCap(),
        onTarget: isFamily(groupName(), TARGET.group),
        originGroup: job.originGroup,
        running: job.running, paused: job.paused, pass: job.pass,
        phase: job.phase, clearFirst: job.clearFirst, clearOnly: job.clearOnly,
        scanning: scanState.running,
        total: job.total, done: job.done, added: job.added,
        failed: job.failed.length, toAdd: job.queue.length, toRemove: job.removeQueue.length,
        cleared: job.cleared, clearTotal: job.clearTotal, clearFailed: job.clearFailed.length,
        srcFrom: job.srcFrom, srcCount: job.srcCount, haveCount: job.haveCount,
        finishing: job.finishing, multi: job.multi,
        famText: job.famText, famCreated: job.famCreated, famDeleted: job.famDeleted,
        lastError: job.lastError
      });
      return;
    }

    if (msg.action === 'FT_WL_GROUPS_PROBE') {
      (async () => {
        if (job.running || job.finishing) { sendResponse({ ok: false, error: '任务进行中，勿手动切分组' }); return; }
        const r = await listGroupOptions();
        let switched = null;
        if (msg.switchTo) switched = await switchGroup(msg.switchTo);
        sendResponse({ ok: true, current: groupName(), options: r.options || [], probeError: r.error || '', switched, dataRows: dataRowsTotal() });
      })();
      return true;
    }

    /* ★ v11：手动测试新建 / 删除分组（popup 高级区） */
    if (msg.action === 'FT_WL_GROUP_OP') {
      (async () => {
        if (job.running || job.finishing || scanState.running) { sendResponse({ ok: false, error: '任务进行中，请稍后' }); return; }
        const name = String(msg.name || '').trim();
        if (!name) { sendResponse({ ok: false, error: '请填写分组名' }); return; }
        scanState.running = true; syncBusy();
        try {
          let r;
          if (msg.op === 'create') r = await createGroup(name);
          else if (msg.op === 'delete') {
            if (familyIndex(name, TARGET.group) < 1) r = { ok: false, error: `测试删除只允许 ${TARGET.group}1 / ${TARGET.group}2 … 这类系列分组` };
            else {
              r = await deleteGroup(name, TARGET.group);
              if (r.ok) bg({ action: 'FT_WL_MEMBERSHIP', payload: { group: name, drop: true } });
            }
          } else r = { ok: false, error: '未知操作' };
          sendResponse(Object.assign({ op: msg.op, name }, r));
        } catch (e) { sendResponse({ ok: false, error: String(e.message || e) }); }
        finally { scanState.running = false; syncBusy(); }
      })();
      return true;
    }

    if (msg.action === 'FT_WL_PROBE') {
      (async () => {
        const btn = findAddButton();
        const del = firstDeletableRow();
        const gm = groupMenuButton();
        let info = {
          ok: true,
          addBtn: btn ? `${cleanText(btn).slice(0, 20)} (id=${btn.id || '-'}, state=${btn.getAttribute('data-state') || '-'})` : '未找到',
          groupMenu: gm ? `找到 (id=${gm.id || '-'})` : '未找到',
          popover: popoverRoots().length,
          input: '未打开/未找到', items: 0, itemSample: [],
          rows: gridRowCount(), dataRows: dataRowsTotal(), group: groupName(),
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
        } catch (e) { info.error = String(e.message || e); }
        sendResponse(info);
      })();
      return true;
    }

    if (msg.action === 'FT_WL_PROBE_DEL') {
      (async () => {
        const tgt = msg.symbol ? await locateRow(String(msg.symbol).toUpperCase()) : firstDeletableRow();
        if (!tgt) { sendResponse({ ok: false, error: '未找到带三点菜单的目标行' }); return; }
        closeMenus(); await sleep(100);
        fireMouseSeq(tgt.btn);
        const item = await waitFor(findRemoveMenuItem, 2500, 100);
        const roots = menuRoots();
        const sample = roots.length
          ? Array.from(roots[roots.length - 1].querySelectorAll('[role="menuitem"],[data-dropdown-menu-item]'))
            .map(x => `${cleanText(x)}#${x.id || '-'}`).slice(0, 10)
          : [];
        closeMenus();
        sendResponse({ ok: true, symbol: tgt.sym, rowId: tgt.rowId, menus: roots.length, menuItems: sample, removeFound: !!item, removeId: item ? (item.id || '-') : '-' });
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

    if (msg.action === 'FT_WL_TEST_DEL') {
      if (job.running) { sendResponse({ ok: false, error: '批量任务进行中' }); return; }
      renderScan('测试删除…', 'test');
      const p = msg.symbol ? deleteSymbol(String(msg.symbol).toUpperCase()) : deleteTopRow(new Set());
      p.then(r => { renderScan('测试删除结果: ' + JSON.stringify(r)); sendResponse({ ok: true, result: r }); })
        .catch(e => sendResponse({ ok: false, error: String(e.message || e) }));
      return true;
    }

    if (msg.action === 'FT_WL_DIFF') {
      if (job.running || job.finishing || scanState.running) { sendResponse({ ok: false, error: '任务/抓取进行中，请稍后' }); return; }
      renderScan('正在比对 Earning 系列…（会依次切到各系列分组读取，结束后切回）', 'diff');
      scanState.running = true; scanState.abort = false; syncBusy();
      const origin = groupName();
      (async () => {
        try {
          const P = await computeFamilyPlan({ base: TARGET.group, strict: TARGET.strictSync, wipe: false });
          renderScan(`来源 ${P.src.from}：${P.src.symbols.length}｜系列现有 ${P.haveCount}｜${P.text}`);
          sendResponse(familyDiffResponse(P));
        } catch (e) {
          renderScan('❌ ' + String(e.message || e));
          sendResponse({ ok: false, error: String(e.message || e) });
        } finally {
          try { if (origin && normGroup(groupName()) !== normGroup(origin)) await switchGroup(origin); } catch (e) { }
          scanState.running = false; syncBusy();
        }
      })();
      return true;
    }

    if (msg.action === 'FT_WL_START') {
      startJob({
        clearFirst: !!msg.clearFirst, clearOnly: !!msg.clearOnly,
        strictSync: msg.strictSync, targetGroup: msg.targetGroup, skipQuotes: !!msg.skipQuotes
      }).then(r => sendResponse(r)).catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }

    if (msg.action === 'FT_WL_CLEAR_GROUPS') {
      startClearGroups({ keep: msg.keep }).then(r => sendResponse(r)).catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }

    if (msg.action === 'FT_WL_PAUSE') { togglePause(); sendResponse({ ok: true, paused: job.paused }); return; }
    if (msg.action === 'FT_WL_STOP') { stopJob(); scanState.abort = true; sendResponse({ ok: true }); return; }
    if (msg.action === 'FT_WL_FAILED') { sendResponse({ ok: true, list: job.failed, clearList: job.clearFailed }); return; }
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

  /* ================= 对外 API ================= */
  window.__FT_WL_API__ = {
    version: 11,
    isWatchlistPage, groupName, normGroup, switchGroup, listGroupOptions,
    waitGridSettled, gridRowCount, dataRowsTotal, gridSaysEmpty, normKey,
    collectWatchlist, addOneSymbol, deleteSymbol, hasSymbolInGrid, rowQuote, findRowQuote,
    cleanNavSearch, pressEscape, ensureHud, renderScan, toast,
    familyIndex, isFamily, groupCap, createGroup, deleteGroup,
    targetGroup: () => TARGET.group,
    isBusy: () => !!(job.running || job.finishing || scanState.running),
    clearStopFlags: () => { if (!job.running) job.stop = false; scanState.abort = false; },
    setExternalBusy: (v) => { window.__FT_AGENT_BUSY__ = !!v; syncBusy(); },
    setTradeBusy: (v) => { window.__FT_TRADE_BUSY__ = !!v; syncBusy(); }
  };

  bootstrap();
  console.log(LOG, `watchlist.js v11 就绪（isWatchlist=${isWatchlistPage()}，系列基名 ${TARGET.group}）`);
})();