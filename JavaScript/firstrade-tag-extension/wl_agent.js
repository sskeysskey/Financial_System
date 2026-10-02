/* ============================================================================
 * Firstrade 远程代理  wl_agent.js  v3     仅在 /app/watchlist 生效
 *   Python → bridge_server.py 任务队列 → 本脚本轮询领任务
 *   action: add / remove / trade / scan_groups / ★ quote（G 键取「变更%」）
 * ==========================================================================*/
(() => {
  if (window.__FT_WL_AGENT_V3__) return;
  window.__FT_WL_AGENT_V3__ = true;

  const LOG = '[FT-AGENT]';
  const POLL_MS = 2000;
  const FORBIDDEN = 'header, #app-header, nav, #app-quote-bar';
  const ROW_EXCLUDE = '.ag-floating-top, .ag-floating-bottom, #app-quote-bar, header, #app-header';
  const TEMP_GROUP = 'temp';
  const SRC_TXT = { positions: '持仓页', current: '当前分组', group: '自选分组', temp: '临时分组' };

  let ENABLED = true;
  let RESTORE = true;
  let DEBUG = false;
  let busy = false;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const log = (...a) => { if (DEBUG) console.log(LOG, ...a); };
  const isWatchlistPage = () => /\/watchlist/i.test(location.pathname || '');
  const api = () => window.__FT_WL_API__ || null;
  const norm = (s) => String(s || '').replace(/\s+/g, '').trim();
  const toast = (t) => { try { (window.__FT_TOAST__ || console.log)(t); } catch (e) { } };

  function isVisible(el) {
    if (!el) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    if (st.display === 'contents') return true;
    const r = el.getBoundingClientRect();
    return !!(r.width || r.height);
  }
  function cleanText(el) {
    const t = (el && (el.innerText || el.textContent)) || '';
    return t.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
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
  function sendKey(el, key, keyCode) {
    const opt = { bubbles: true, cancelable: true, key, code: key, keyCode, which: keyCode };
    el.dispatchEvent(new KeyboardEvent('keydown', opt));
    el.dispatchEvent(new KeyboardEvent('keyup', opt));
  }
  function fireMouseSeq(el) {
    const r = el.getBoundingClientRect();
    const opt = {
      bubbles: true, cancelable: true, view: window,
      clientX: r.left + Math.max(2, r.width / 2), clientY: r.top + Math.max(2, r.height / 2),
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
  function symFromRowId(rowId) {
    if (!rowId) return '';
    const raw = String(rowId).split('|')[0].trim().toUpperCase();
    return /^[A-Z][A-Z0-9.\-]{0,9}$/.test(raw) ? raw : '';
  }

  function groupTrigger() {
    const all = Array.from(document.querySelectorAll('[data-select-trigger]'))
      .filter(el => isVisible(el) && !el.closest(FORBIDDEN));
    const inMain = all.filter(el => el.closest('main'));
    return inMain[0] || all[0] || null;
  }
  function currentGroup() {
    const a = api();
    if (a && a.groupName) { const g = a.groupName(); if (g) return g; }
    const t = groupTrigger();
    return t ? cleanText(t) : '';
  }
  const sameGroup = (x, y) => {
    const a = api();
    if (a && a.normGroup) return a.normGroup(x) === a.normGroup(y);
    return norm(x).toUpperCase() === norm(y).toUpperCase();
  };
  function selectOptions() {
    const roots = Array.from(document.querySelectorAll(
      '[data-select-content], [role="listbox"], [data-popover-content]'
    )).filter(el => isVisible(el) && !el.closest(FORBIDDEN));
    let items = [];
    roots.forEach(r => { items = items.concat(Array.from(r.querySelectorAll('[data-select-item], [role="option"]'))); });
    if (!items.length) {
      items = Array.from(document.querySelectorAll('[data-select-item], [role="option"]'))
        .filter(el => !el.closest(FORBIDDEN));
    }
    return items.filter(isVisible);
  }
  const optionLabel = (el) => norm(cleanText(el));

  function gridRowCount() {
    const a = api();
    if (a && a.gridRowCount) return a.gridRowCount();
    const gs = Array.from(document.querySelectorAll('[role="grid"][aria-rowcount]'))
      .filter(g => !g.closest(FORBIDDEN));
    let best = null;
    gs.forEach(g => {
      const n = parseInt(g.getAttribute('aria-rowcount'), 10);
      if (Number.isFinite(n) && (best === null || n > best)) best = n;
    });
    return best;
  }
  async function waitGridSettled(timeout = 8000) {
    const t0 = Date.now();
    let last = null, same = 0;
    while (Date.now() - t0 < timeout) {
      const n = gridRowCount();
      if (n !== null && n === last) { same++; if (same >= 3) return n; }
      else { same = 0; last = n; }
      await sleep(200);
    }
    return gridRowCount();
  }

  async function switchGroup(target) {
    const a = api();
    if (a && typeof a.switchGroup === 'function') return a.switchGroup(target);
    return switchGroupLocal(target);
  }
  async function switchGroupLocal(target) {
    const want = norm(target);
    if (!want) return { ok: false, error: '目标分组名为空' };
    if (norm(currentGroup()) === want) return { ok: true, changed: false };
    const trig = groupTrigger();
    if (!trig) return { ok: false, error: '页面上找不到分组选择器 [data-select-trigger]' };
    for (let attempt = 0; attempt < 3; attempt++) {
      if (trig.getAttribute('data-state') === 'open' || trig.getAttribute('aria-expanded') === 'true') {
        sendKey(trig, 'Escape', 27);
        await sleep(250);
      }
      fireMouseSeq(trig);
      const opts = await waitFor(() => { const o = selectOptions(); return o.length ? o : null; }, 3500, 120);
      if (!opts) { await sleep(450); continue; }
      const hit = opts.find(o => optionLabel(o) === want);
      if (!hit) {
        const names = opts.map(optionLabel).filter(Boolean);
        sendKey(trig, 'Escape', 27);
        return { ok: false, error: `分组「${target}」不存在（页面可选：${names.join(' / ') || '空'}）` };
      }
      fireMouseSeq(hit);
      try { hit.click(); } catch (e) { }
      const ok = await waitFor(() => norm(currentGroup()) === want, 7000, 160);
      if (ok) { await waitGridSettled(); return { ok: true, changed: true }; }
      sendKey(trig, 'Escape', 27);
      await sleep(500);
    }
    return { ok: false, error: `切换到分组「${target}」失败（重试 3 次）` };
  }

  async function alreadyHas(sym) {
    const a = api();
    if (!a || !a.collectWatchlist || !a.dataRowsTotal) return false;
    const rows = a.dataRowsTotal();
    if (rows === null || rows <= 0) return false;
    if (rows > 400) return false;
    const buf = await a.collectWatchlist();
    const t = a.normKey(sym);
    return Object.keys(buf).some(k => a.normKey(k) === t);
  }

  /* ★ 分组归属全量扫描任务（Python 图表 M 键） */
  async function handleScanTask(t) {
    const M = window.__FT_WL_MEMBER__;
    let ok = false, msg = '', data = {};
    if (!M) msg = 'wl_membership.js 未加载（请刷新 watchlist 页面）';
    else {
      try {
        const r = await M.scanAllGroups(Array.isArray(t.groups) ? t.groups : null);
        ok = !!r.ok;
        msg = r.message || r.error || '';
        data = { results: r.results || [], groups: r.groups || [] };
      } catch (e) { msg = String((e && e.message) || e); }
    }
    toast((ok ? '✅ ' : '❌ ') + msg);
    console.log(LOG, msg);
    await bg({ action: 'FT_WL_TASK_RESULT', payload: { id: t.id, ok, message: msg, data } });
  }

  async function reportTask(t, ok, msg, data, restore, origin) {
    const a = api();
    try {
      if (restore && origin && !sameGroup(currentGroup(), origin)) await switchGroup(origin);
    } catch (e) { log('切回原分组失败', e); }
    try { a.pressEscape(); a.cleanNavSearch(); } catch (e) { }
    const text = (ok ? '✅ ' : '❌ ') + msg;
    try { a.renderScan(text); } catch (e) { }
    toast(text);
    console.log(LOG, text);
    await bg({ action: 'FT_WL_TASK_RESULT', payload: { id: t.id, ok, message: msg, data } });
  }

  async function handleRemoveTask(t) {
    const a = api();
    const sym = String(t.symbol || '').trim().toUpperCase();
    const grp = String(t.group || '').trim();
    const restore = (t.restore === undefined) ? RESTORE : (!!t.restore && RESTORE);
    const origin = currentGroup();
    let ok = false, msg = '', status = '';
    try { a.ensureHud('task'); a.renderScan(`收到删除任务：${sym} ✕「${grp}」`, 'task'); } catch (e) { }
    try {
      if (!sym) throw new Error('symbol 为空');
      if (!grp) throw new Error('删除任务必须指定分组');
      if (typeof a.deleteSymbol !== 'function') throw new Error('watchlist.js 版本过旧（缺少 deleteSymbol），请刷新页面');
      a.clearStopFlags();
      a.cleanNavSearch();
      const sr = await switchGroup(grp);
      if (!sr.ok) throw new Error(sr.error);
      await waitGridSettled(4000);
      const r = await a.deleteSymbol(sym);
      status = (r && r.status) || '';
      if (status === 'removed') { ok = true; msg = `${sym} 已从「${grp}」删除`; }
      else if (status === 'missing') { ok = true; msg = `${sym} 本就不在「${grp}」中（已同步本机记录）`; }
      else msg = `${sym} 从「${grp}」删除失败：${(r && (r.error || r.status)) || '未知原因'}`;
    } catch (e) { ok = false; msg = String((e && e.message) || e); }
    await reportTask(t, ok, msg, { symbol: sym, group: grp, status }, restore, origin);
  }

  /* ★ 远程交易：at-most-once */
  async function handleTradeTask(t) {
    const T = window.__FT_TRADE__;
    const p = t.params || {};
    const st = await new Promise(r => chrome.storage.local.get(['ftTradeDoneIds'], r));
    const doneIds = Array.isArray(st.ftTradeDoneIds) ? st.ftTradeDoneIds : [];
    if (doneIds.includes(t.id)) {
      await bg({ action: 'FT_WL_TASK_RESULT', payload: { id: t.id, ok: false, message: '该交易任务已执行过（防重复下单，已忽略）' } });
      return;
    }
    await new Promise(r => chrome.storage.local.set({ ftTradeDoneIds: doneIds.concat([t.id]).slice(-300) }, r));
    let ok = false, msg = '', data = {};
    if (!T) msg = 'ft_trade.js 未加载（请刷新 watchlist 页面）';
    else {
      try {
        const r = await T.executeRemote({
          symbol: t.symbol, side: p.side, amount: p.amount, qty: p.qty,
          remove: p.remove !== false, dry: !!p.dry
        });
        ok = !!r.ok; msg = r.message || r.error || ''; data = r;
      } catch (e) { msg = String((e && e.message) || e); }
    }
    toast((ok ? '✅ ' : '❌ ') + msg);
    await bg({ action: 'FT_WL_TASK_RESULT', payload: { id: t.id, ok, message: msg, data } });
  }

  /* ==================== ★ G 键取「变更%」 ==================== */
  function visibleSyms() {
    const out = [], seen = new Set();
    document.querySelectorAll('[row-id]').forEach(r => {
      if (r.closest(ROW_EXCLUDE)) return;
      const s = symFromRowId(r.getAttribute('row-id'));
      if (s && !seen.has(s)) { seen.add(s); out.push(s); }
    });
    return out;
  }
  const quoteReady = (q) => !!(q && /%/.test(q.change_pct || ''));

  async function waitQuote(sym, timeout) {
    const a = api();
    const t0 = Date.now();
    let q = null;
    while (Date.now() - t0 < timeout) {
      q = a.rowQuote(sym) || q;
      if (quoteReady(q) && q.price > 0) return q;
      await sleep(250);
    }
    return q;
  }

  async function quoteInGroup(sym, grp) {
    const a = api();
    const sr = await switchGroup(grp);
    if (!sr.ok) throw new Error(sr.error || '切换失败');
    await waitGridSettled(4000);
    let q = await a.findRowQuote(sym, true);
    if (!q) throw new Error(`「${grp}」里没找到 ${sym}`);
    if (!quoteReady(q)) q = (await waitQuote(sym, 3000)) || q;
    return q;
  }

  async function quoteViaTemp(sym, grp, say) {
    const a = api();
    const sr = await switchGroup(grp);
    if (!sr.ok) throw new Error(`临时分组「${grp}」不可用：${sr.error}（请先在自选股页新建名为 ${grp} 的分组）`);
    await waitGridSettled(4000);
    const onTemp = () => sameGroup(currentGroup(), grp);
    let q = null;
    try {
      q = await a.findRowQuote(sym, false);
      if (!q) {
        say(`➕ 临时加入「${grp}」…`);
        const r = await a.addOneSymbol(sym);
        if (!r || r.status !== 'added') throw new Error(`临时添加失败：${(r && (r.error || r.status)) || '未知'}`);
        await waitGridSettled(3000);
      }
      say('⏳ 等待行情刷新…');
      q = await waitQuote(sym, 9000);
      if (!q) throw new Error('添加后没在表格里看到该股票');
    } finally {
      /* ★ 只在确认身处 temp 分组时才删，绝不误删其它分组 */
      if (onTemp()) {
        say('🧹 清理临时分组…');
        try { await a.deleteSymbol(sym); } catch (e) { }
        for (let i = 0; i < 15 && onTemp(); i++) {
          const left = visibleSyms();
          if (!left.length) break;
          const r = await a.deleteSymbol(left[0]);
          if (!r || (r.status !== 'removed' && r.status !== 'missing')) break;
        }
      }
    }
    return q;
  }

  async function handleQuoteTask(t) {
    const a = api();
    const sym = String(t.symbol || '').trim().toUpperCase();
    const p = t.params || {};
    const origin = currentGroup();
    const say = (x) => { try { a.renderScan(`📈 ${sym}：${x}`, 'task'); } catch (e) { } };
    let plan = Array.isArray(p.plan) && p.plan.length ? p.plan.slice() : [{ src: 'temp', group: TEMP_GROUP }];
    let pi = plan.findIndex(s => s.src !== 'positions');
    if (pi < 0) pi = plan.length;
    plan.splice(pi, 0, { src: 'current' });               // 当前分组可见行 = 零切换最快
    let ok = false, data = { symbol: sym };
    const tried = [];
    try { a.ensureHud('task'); } catch (e) { }
    say('收到取数任务…');
    try {
      if (!sym) throw new Error('symbol 为空');
      if (typeof a.findRowQuote !== 'function') throw new Error('watchlist.js 版本过旧（缺少 findRowQuote），请刷新页面');
      a.clearStopFlags(); a.cleanNavSearch();
      for (const step of plan) {
        let q = null, err = '';
        const label = step.src === 'group' ? `自选「${step.group}」` : (SRC_TXT[step.src] || step.src);
        try {
          if (step.src === 'positions') {
            say('从持仓页读取…');
            const r = await bg({ action: 'FT_POS_QUOTE', symbol: sym });
            if (r && r.ok && r.found) {
              q = Object.assign({}, r.quote || {}, { record: r.record || null });
              if (!q.change_pct && r.record && r.record.day_change) q.change_pct = r.record.day_change;
            } else err = (r && r.error) || '持仓页没有这只股票';
          } else if (step.src === 'current') {
            if (sameGroup(currentGroup(), TEMP_GROUP)) continue;
            q = a.rowQuote(sym);
            if (q && !quoteReady(q)) q = await waitQuote(sym, 1500);
            if (!q) continue;                               // 不在当前视图，静默跳过
            step.group = (window.__FT_WL_MEMBER__ ? window.__FT_WL_MEMBER__.cleanGroup(currentGroup()) : currentGroup());
          } else if (step.src === 'group') {
            say(`切到「${step.group}」读取…`);
            q = await quoteInGroup(sym, step.group);
          } else if (step.src === 'temp') {
            q = await quoteViaTemp(sym, step.group || TEMP_GROUP, say);
          }
        } catch (e) { err = String((e && e.message) || e); }
        if (quoteReady(q)) {
          ok = true;
          data = {
            symbol: sym, source: step.src, group: step.group || '',
            change_pct: q.change_pct, change_pct_num: q.change_pct_num,
            last: q.last || '', price: q.price || null, record: q.record || null
          };
          break;
        }
        tried.push(`${label}：${err || '未取到变更%'}`);
      }
    } catch (e) { tried.push(String((e && e.message) || e)); }
    const srcLabel = data.source === 'group' || data.source === 'current' ? `自选「${data.group}」`
      : (SRC_TXT[data.source] || data.source || '');
    const msg = ok
      ? `${sym} 变更% ${data.change_pct}｜现价 ${data.last || '--'}（${srcLabel}）`
      : `${sym} 取数失败：${tried.join('；') || '未知原因'}`;
    data.tried = tried;
    await reportTask(t, ok, msg, data, RESTORE, origin);
  }

  async function handleTask(t) {
    const action = String(t.action || 'add');
    if (action === 'scan_groups') return handleScanTask(t);
    if (action === 'remove') return handleRemoveTask(t);
    if (action === 'trade') return handleTradeTask(t);
    if (action === 'quote') return handleQuoteTask(t);

    const a = api();
    const sym = String(t.symbol || '').trim().toUpperCase();
    const grp = String(t.group || '').trim();
    const restore = (t.restore === undefined) ? RESTORE : (!!t.restore && RESTORE);
    const origin = currentGroup();
    let ok = false, msg = '';
    try { a.ensureHud('task'); a.renderScan(`收到任务：${sym} → 「${grp || '当前分组'}」`, 'task'); } catch (e) { }
    try {
      if (!sym) throw new Error('symbol 为空');
      a.clearStopFlags();
      a.cleanNavSearch();
      if (grp) {
        const sr = await switchGroup(grp);
        if (!sr.ok) throw new Error(sr.error);
        if (sr.changed) try { a.renderScan(`已切到「${grp}」，正在添加 ${sym}…`); } catch (e) { }
      }
      await waitGridSettled(4000);
      if (await alreadyHas(sym)) {
        ok = true;
        msg = `${sym} 已在「${grp || currentGroup()}」中，无需重复添加`;
      } else {
        const r = await a.addOneSymbol(sym);
        if (r && r.status === 'added') { ok = true; msg = `${sym} 已加入「${grp || currentGroup()}」`; }
        else msg = `${sym} 添加失败：${(r && (r.error || r.status)) || '未知原因'}`;
      }
    } catch (e) { ok = false; msg = String((e && e.message) || e); }
    await reportTask(t, ok, msg, { symbol: sym, group: grp }, restore, origin);
  }

  /* ---------------- 轮询 ---------------- */
  async function poll() {
    if (!ENABLED || busy || !isWatchlistPage()) return;
    const a = api();
    if (!a || !a.addOneSymbol) return;
    if (a.isBusy() || window.__FT_TRADE_BUSY__) return;
    busy = true;                                   // ★ 先占锁，防止 focus+interval 并发领两次
    try {
      const r = await bg({ action: 'FT_WL_TASKS', max: 3 });
      if (!r.ok) return;
      const tasks = (r.data && r.data.tasks) || [];
      if (!tasks.length) return;
      try { a.setExternalBusy(true); } catch (e) { }
      for (const t of tasks) {
        if (!ENABLED) break;
        await handleTask(t);
        await sleep(400);
      }
    } finally {
      busy = false;
      try { a.setExternalBusy(false); } catch (e) { }
    }
  }

  function loadSettings() {
    chrome.storage.local.get(['ftWlAgent', 'ftWlRestoreGroup', 'ftDebug'], (res) => {
      ENABLED = res.ftWlAgent !== false;
      RESTORE = res.ftWlRestoreGroup !== false;
      DEBUG = !!res.ftDebug;
    });
  }
  chrome.storage.onChanged.addListener((c, area) => {
    if (area !== 'local') return;
    if (c.ftWlAgent || c.ftWlRestoreGroup || c.ftDebug) loadSettings();
  });

  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  window.addEventListener('focus', () => poll());

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg) return;
    if (msg.action === 'FT_AGENT_STATUS') {
      sendResponse({
        ok: true, page: isWatchlistPage(), enabled: ENABLED, restore: RESTORE,
        busy, group: currentGroup(), apiReady: !!(api() && api().addOneSymbol)
      });
      return;
    }
    if (msg.action === 'FT_WAKE_UP') { poll(); sendResponse({ ok: true }); return; }
  });

  loadSettings();
  if (isWatchlistPage()) {
    setInterval(poll, POLL_MS);
    setTimeout(poll, 1000);
  }
  console.log(LOG, `wl_agent.js v3 就绪（isWatchlist=${isWatchlistPage()}）`);
})();