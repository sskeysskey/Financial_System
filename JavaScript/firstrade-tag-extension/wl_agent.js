/* ============================================================================
 * Firstrade 远程添加代理  wl_agent.js  v1     仅在 /app/watchlist 生效
 *
 *   Python(Chart_input_single / Check_Group)
 *        → bridge_server.py 任务队列
 *        → 本脚本每 2s 轮询领任务
 *        → 自动切到目标分组（买/买买/买买买/卖卖卖）
 *        → 复用 watchlist.js 的 addOneSymbol() 完成添加
 *        → 去重 / 回报结果 / 可选切回原分组
 *
 *   与「功能③一键重建」「④行情抓取」严格互斥，绝不并发。
 * ==========================================================================*/
(() => {
  if (window.__FT_WL_AGENT_V1__) return;
  window.__FT_WL_AGENT_V1__ = true;

  const LOG = '[FT-AGENT]';
  const POLL_MS = 2000;
  const FORBIDDEN = 'header, #app-header, nav, #app-quote-bar';

  let ENABLED = true;       // storage.ftWlAgent
  let RESTORE = true;       // storage.ftWlRestoreGroup
  let DEBUG = false;
  let busy = false;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const log = (...a) => { if (DEBUG) console.log(LOG, ...a); };
  const isWatchlistPage = () => /\/watchlist/i.test(location.pathname || '');
  const api = () => window.__FT_WL_API__ || null;
  const norm = (s) => String(s || '').replace(/\s+/g, '').trim();
  const toast = (t) => { try { (window.__FT_TOAST__ || console.log)(t); } catch (e) { } };

  /* ---------------- 通用 DOM 工具（本文件自带，避免依赖过深） ---------------- */
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

  /* ---------------- 分组下拉：定位 / 读取 / 切换 ---------------- */
  function groupTrigger() {
    const all = Array.from(document.querySelectorAll('[data-select-trigger]'))
      .filter(el => isVisible(el) && !el.closest(FORBIDDEN));
    const inMain = all.filter(el => el.closest('main'));
    return inMain[0] || all[0] || null;
  }

  function currentGroup() {
    const a = api();
    if (a && a.groupName) {
      const g = a.groupName();
      if (g) return g;
    }
    const t = groupTrigger();
    return t ? cleanText(t) : '';
  }

  function selectOptions() {
    const roots = Array.from(document.querySelectorAll(
      '[data-select-content], [role="listbox"], [data-popover-content]'
    )).filter(el => isVisible(el) && !el.closest(FORBIDDEN));
    let items = [];
    roots.forEach(r => {
      items = items.concat(Array.from(r.querySelectorAll('[data-select-item], [role="option"]')));
    });
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

  /* 等表格稳定（切分组后 ag-Grid 会重载） */
  async function waitGridSettled(timeout = 8000) {
    const t0 = Date.now();
    let last = null, same = 0;
    while (Date.now() - t0 < timeout) {
      const n = gridRowCount();
      if (n !== null && n === last) {
        same++;
        if (same >= 3) return n;
      } else { same = 0; last = n; }
      await sleep(200);
    }
    return gridRowCount();
  }

  async function switchGroup(target) {
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

      /* 「买」是「买买」的前缀 → 必须严格等值匹配 */
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

  /* ---------------- 任务处理 ---------------- */
  async function alreadyHas(sym) {
    const a = api();
    if (!a || !a.collectWatchlist || !a.dataRowsTotal) return false;
    const rows = a.dataRowsTotal();
    if (rows === null || rows <= 0) return false;
    if (rows > 400) return false;            // 大分组不做全表去重（太慢），交给行数校验
    const buf = await a.collectWatchlist();
    const t = a.normKey(sym);
    return Object.keys(buf).some(k => a.normKey(k) === t);
  }

  async function handleTask(t) {
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
        if (r && r.status === 'added') {
          ok = true;
          msg = `${sym} 已加入「${grp || currentGroup()}」`;
        } else {
          ok = false;
          msg = `${sym} 添加失败：${(r && (r.error || r.status)) || '未知原因'}`;
        }
      }
    } catch (e) {
      ok = false;
      msg = String((e && e.message) || e);
    }

    /* 尽量把页面还原成用户离开时的样子 */
    try {
      if (restore && origin && norm(currentGroup()) !== norm(origin)) {
        await switchGroup(origin);
      }
    } catch (e) { log('切回原分组失败', e); }

    try { a.pressEscape(); a.cleanNavSearch(); } catch (e) { }

    const text = (ok ? '✅ ' : '❌ ') + msg;
    try { a.renderScan(text); } catch (e) { }
    toast(text);
    console.log(LOG, text);

    await bg({
      action: 'FT_WL_TASK_RESULT',
      payload: { id: t.id, ok: ok, message: msg, data: { symbol: sym, group: grp } }
    });
  }

  /* ---------------- 轮询 ---------------- */
  async function poll() {
    if (!ENABLED || busy || !isWatchlistPage()) return;
    const a = api();
    if (!a || !a.addOneSymbol) return;
    if (a.isBusy()) return;                      // 一键重建 / 行情抓取进行中 → 让路

    const r = await bg({ action: 'FT_WL_TASKS', max: 3 });
    if (!r.ok) return;                           // 桥接没开，静默
    const tasks = (r.data && r.data.tasks) || [];
    if (!tasks.length) return;

    busy = true;
    try { a.setExternalBusy(true); } catch (e) { }
    try {
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

  /* ---------------- 设置 ---------------- */
  function loadSettings() {
    chrome.storage.local.get(['ftWlAgent', 'ftWlRestoreGroup', 'ftDebug'], (res) => {
      ENABLED = res.ftWlAgent !== false;          // 默认开
      RESTORE = res.ftWlRestoreGroup !== false;   // 默认开
      DEBUG = !!res.ftDebug;
      log('设置: ENABLED =', ENABLED, 'RESTORE =', RESTORE);
    });
  }
  chrome.storage.onChanged.addListener((c, area) => {
    if (area !== 'local') return;
    if (c.ftWlAgent || c.ftWlRestoreGroup || c.ftDebug) loadSettings();
  });

  /* 供 popup 查询状态 */
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || msg.action !== 'FT_AGENT_STATUS') return;
    sendResponse({
      ok: true, page: isWatchlistPage(), enabled: ENABLED, restore: RESTORE,
      busy: busy, group: currentGroup(), apiReady: !!(api() && api().addOneSymbol)
    });
  });

  loadSettings();
  if (isWatchlistPage()) {
    setInterval(poll, POLL_MS);
    setTimeout(poll, 1500);
  }
  console.log(LOG, `wl_agent.js v1 就绪（isWatchlist=${isWatchlistPage()}）`);
})();