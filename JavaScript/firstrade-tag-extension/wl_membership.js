/* ============================================================================
 * Firstrade 自选股「分组归属」同步  wl_membership.js  v1   仅在 /app/watchlist 生效
 *
 *  目标：让本机知道「每个分组里有哪些 symbol」→ bridge_server.py 落盘到
 *        Modules/firstrade_wl_membership.json → Chart_input(_single) 显示「自选 [买] [Watch]」
 *
 *  更新来源（从便宜到贵）：
 *    ① 被动快照：分组表格稳定 3 秒后，DOM 行数 == 表格总行数 → 完整快照；否则只合并可见行
 *    ② 手动增删捕获：网页上「三点菜单 → 删除」/「添加自选股」弹层选中 → 精确回传事件
 *    ③ watchlist.js 每次完整滚动读取（比对/复核/行情抓取）→ 完整快照（挂钩在 watchlist.js）
 *    ④ Python F 键添加成功 → bridge 服务端直接记账（不依赖本脚本）
 *    ⑤ 全量扫描：popup 按钮 / 图表 M 键 → 逐组切换 + 滚动读取 → 完整快照 → 切回原分组
 * ==========================================================================*/
(() => {
  if (window.__FT_WL_MEMBER_V1__) return;
  window.__FT_WL_MEMBER_V1__ = true;

  const LOG = '[FT-MEMBER]';
  const TICK_MS = 1000;
  const STABLE_TICKS = 3;
  const ROW_EXCLUDE = '.ag-floating-top, .ag-floating-bottom, #app-quote-bar, header, #app-header';
  const FORBIDDEN = 'header, #app-header, nav, #app-quote-bar';
  const NOT_A_GROUP = /新建|创建|管理|编辑|重命名|删除|new|create|manage|edit|rename|delete/i;
  const REMOVE_TXT = /^(删除|移除|移出|删除自选|移除自选|Remove|Remove from watchlist|Delete)$/i;

  let DEBUG = false;
  let PASSIVE = true;
  let knownGroups = [];
  let scanning = false;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const log = (...a) => { if (DEBUG) console.log(LOG, ...a); };
  const isWatchlistPage = () => /\/watchlist/i.test(location.pathname || '');
  const api = () => window.__FT_WL_API__ || null;
  const busy = () => window.__FT_AUTOMATION__ === true || scanning;
  const toast = (t) => { try { (window.__FT_TOAST__ || console.log)(t); } catch (e) { } };
  const normKey = (s) => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const cleanGroup = (s) => String(s || '')
    .replace(/\u00a0/g, ' ')
    .replace(/[（(]\s*\d+\s*[）)]\s*$/, '')
    .replace(/\s+/g, ' ')
    .trim();

  function cleanText(el) {
    const t = (el && (el.innerText || el.textContent)) || '';
    return t.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
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

  function symbolFromRowId(rowId) {
    if (!rowId) return '';
    const raw = String(rowId).split('|')[0].trim().toUpperCase();
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(raw)) return '';
    return raw;
  }

  function visibleSymbols() {
    const set = new Set();
    document.querySelectorAll('[row-id]').forEach(r => {
      if (r.closest(ROW_EXCLUDE)) return;
      const s = symbolFromRowId(r.getAttribute('row-id'));
      if (s) set.add(s);
    });
    return set;
  }

  function currentGroup() { const a = api(); return a ? cleanGroup(a.groupName()) : ''; }
  function totalRows() { const a = api(); return a ? a.dataRowsTotal() : 0; }
  function hasSym(sym) {
    const k = normKey(sym);
    for (const s of visibleSymbols()) if (normKey(s) === k) return true;
    return false;
  }

  /* ---------------- 上报（带去重） ---------------- */
  const lastSent = Object.create(null);

  function sendSnapshot(group, symbols, complete, source, force) {
    const g = cleanGroup(group);
    if (!g) return Promise.resolve({ ok: false, error: 'no group' });
    const arr = Array.from(new Set((symbols || [])
      .map(s => String(s).trim().toUpperCase()).filter(Boolean))).sort();
    const key = g + (complete ? '#C' : '#P');
    const sig = arr.join(',');
    if (!force && lastSent[key] === sig) return Promise.resolve({ ok: true, skipped: true });
    lastSent[key] = sig;
    log('snapshot', g, complete ? '完整' : '部分', arr.length, source);
    return bg({
      action: 'FT_WL_MEMBERSHIP',
      payload: {
        group: g, symbols: arr, complete: !!complete, source: source || '',
        page_groups: knownGroups.length ? knownGroups : null
      }
    }).then(r => { if (!r || !r.ok) delete lastSent[key]; return r; });
  }

  function sendEvent(group, symbol, op, source) {
    const g = cleanGroup(group);
    const sym = String(symbol || '').trim().toUpperCase();
    if (!g || !sym) return Promise.resolve({ ok: false });
    delete lastSent[g + '#C'];
    delete lastSent[g + '#P'];
    log('event', op, sym, g, source);
    return bg({ action: 'FT_WL_MEMBERSHIP_EVENT', payload: { group: g, symbol: sym, op, source } });
  }

  /* ---------------- ① 被动快照 ---------------- */
  let prev = { sig: '', stable: 0 };

  function passiveTick() {
    if (!PASSIVE || !isWatchlistPage() || busy()) { prev.stable = 0; prev.sig = ''; return; }
    const a = api();
    if (!a) return;
    const group = currentGroup();
    if (!group) { prev.stable = 0; return; }
    const syms = visibleSymbols();
    const total = a.dataRowsTotal();
    const sig = group + '|' + total + '|' + Array.from(syms).sort().join(',');
    if (sig !== prev.sig) { prev = { sig, stable: 0 }; return; }
    prev.stable++;
    if (prev.stable < STABLE_TICKS) return;

    if (syms.size === 0) {
      if (total === 0 && typeof a.gridSaysEmpty === 'function' && a.gridSaysEmpty()) {
        sendSnapshot(group, [], true, 'passive_empty');
      }
      return;
    }
    if (total > 0 && syms.size === total) sendSnapshot(group, Array.from(syms), true, 'passive');
    else sendSnapshot(group, Array.from(syms), false, 'passive_visible');
  }

  /* ---------------- ② 手动增删捕获 ---------------- */
  let menuCtx = null;
  const pendingAdds = new Set();

  function recordMenuCtx(target) {
    if (!target || !target.closest) return;
    const btn = target.closest('button[aria-haspopup="menu"]');
    if (!btn) return;
    const row = btn.closest('[row-id]');
    if (!row || row.closest(ROW_EXCLUDE)) return;
    const sym = symbolFromRowId(row.getAttribute('row-id'));
    if (!sym) return;
    menuCtx = { symbol: sym, group: currentGroup(), total: totalRows(), ts: Date.now() };
  }

  function isRemoveItem(el) {
    if (!el) return false;
    if (/watchlist-(remove|delete)/i.test(el.id || '')) return true;
    return REMOVE_TXT.test(cleanText(el));
  }

  function cmdValue(el) {
    if (!el) return '';
    const w = el.closest('[data-value]') || el;
    let v = w.getAttribute('data-value') || el.getAttribute('data-value') || '';
    if (!v) { const sp = el.querySelector('span span, span'); v = sp ? cleanText(sp) : cleanText(el); }
    v = String(v).trim().split(/\s+/)[0].toUpperCase();
    return /^[A-Z][A-Z0-9.\-]{0,9}$/.test(v) ? v : '';
  }

  async function onRemoveChosen() {
    const ctx = menuCtx; menuCtx = null;
    if (!ctx || !ctx.symbol || !ctx.group || Date.now() - ctx.ts > 60000) return;
    const t0 = Date.now();
    while (Date.now() - t0 < 15000) {       // 留时间给可能出现的二次确认对话框
      await sleep(300);
      if (currentGroup() !== ctx.group) return;
      const gone = !hasSym(ctx.symbol);
      const after = totalRows();
      if (gone && after < ctx.total) {
        await sendEvent(ctx.group, ctx.symbol, 'remove', 'manual_remove');
        toast(`🗂 已记录：${ctx.symbol} 移出「${ctx.group}」`);
        return;
      }
    }
  }

  async function onAddChosen(sym) {
    if (!sym) return;
    const group = currentGroup();
    if (!group) return;
    const key = group + '|' + normKey(sym);
    if (pendingAdds.has(key)) return;
    pendingAdds.add(key);
    const before = totalRows();
    const t0 = Date.now();
    try {
      while (Date.now() - t0 < 8000) {
        await sleep(300);
        if (currentGroup() !== group) return;
        if (hasSym(sym) || totalRows() > before) {
          await sendEvent(group, sym, 'add', 'manual_add');
          return;
        }
      }
    } finally { pendingAdds.delete(key); }
  }

  document.addEventListener('pointerdown', (e) => { if (isWatchlistPage()) recordMenuCtx(e.target); }, true);

  document.addEventListener('click', (e) => {
    if (!isWatchlistPage() || busy()) return;
    const t = e.target;
    if (!t || !t.closest) return;
    const item = t.closest('[role="menuitem"], [data-dropdown-menu-item]');
    if (item) { if (isRemoveItem(item)) onRemoveChosen(); return; }
    const cmd = t.closest('[data-command-root] [data-command-item], [data-command-root] [role="option"]');
    if (cmd && !cmd.closest(FORBIDDEN)) onAddChosen(cmdValue(cmd));
  }, true);

  document.addEventListener('keydown', (e) => {
    if (!isWatchlistPage()) return;
    const t = e.target;
    if (!t || !t.closest) return;
    if (e.key === 'Enter' || e.key === ' ') recordMenuCtx(t);
    if (e.key !== 'Enter' || busy()) return;
    const menu = t.closest('[role="menu"], [data-dropdown-menu-content]');
    if (menu) {
      const hl = menu.querySelector('[data-highlighted]') || (t.matches && t.matches('[role="menuitem"]') ? t : null);
      if (isRemoveItem(hl)) onRemoveChosen();
      return;
    }
    const cr = t.closest('[data-command-root]');
    if (cr && !cr.closest(FORBIDDEN)) {
      const sel = cr.querySelector('[data-command-item][aria-selected="true"], [data-command-item][data-selected="true"], [role="option"][aria-selected="true"]');
      if (sel) onAddChosen(cmdValue(sel));
    }
  }, true);

  /* ---------------- ⑤ 全量扫描 ---------------- */
  async function scanAllGroups(want) {
    const a = api();
    if (!isWatchlistPage()) return { ok: false, error: '当前不在 /app/watchlist 页面' };
    if (!a || !a.collectWatchlist) return { ok: false, error: 'watchlist.js 未就绪（请刷新页面）' };
    if (scanning) return { ok: false, error: '分组归属扫描已在进行中' };
    if (a.isBusy()) return { ok: false, error: '自选股同步/行情抓取进行中，请稍后' };

    scanning = true;
    const ownBusy = !window.__FT_AGENT_BUSY__;
    if (ownBusy) { try { a.setExternalBusy(true); } catch (e) { } }
    const origin = a.groupName();
    const results = [];
    let targets = [];
    try {
      a.clearStopFlags();
      a.cleanNavSearch();
      a.ensureHud('task');
      a.renderScan('🗂 正在读取分组列表…', 'task');

      const lr = await a.listGroupOptions();
      await sleep(300);
      let names = Array.from(new Set((lr.options || []).map(cleanGroup).filter(Boolean)))
        .filter(n => !NOT_A_GROUP.test(n));
      if (names.length) knownGroups = names;

      targets = names;
      if (Array.isArray(want) && want.length) {
        const w = new Set(want.map(x => a.normGroup(x)));
        targets = names.filter(n => w.has(a.normGroup(n)));
        if (!targets.length && !names.length) targets = want.map(cleanGroup).filter(Boolean);
      }
      if (!targets.length) targets = [cleanGroup(origin)].filter(Boolean);

      for (let i = 0; i < targets.length; i++) {
        const g = targets[i];
        const tag = `(${i + 1}/${targets.length})`;
        a.renderScan(`🗂 ${tag} 切到「${g}」…`, 'task');
        const sr = await a.switchGroup(g);
        if (!sr.ok) { results.push({ group: g, ok: false, error: sr.error || '切换失败' }); continue; }
        await a.waitGridSettled();
        await sleep(400);
        a.clearStopFlags();
        const buf = await a.collectWatchlist(n => a.renderScan(`🗂 ${tag}「${g}」已读 ${n} 只…`, 'task'));
        const syms = Object.keys(buf);
        const r = await sendSnapshot(currentGroup() || g, syms, true, 'scan_all', true);
        results.push({ group: g, ok: !!(r && r.ok), count: syms.length, error: r && !r.ok ? r.error : '' });
      }
    } catch (e) {
      results.push({ group: '?', ok: false, error: String((e && e.message) || e) });
    } finally {
      try {
        if (origin && a.normGroup(a.groupName()) !== a.normGroup(origin)) {
          a.renderScan(`🗂 正在切回原分组「${origin}」…`, 'task');
          await a.switchGroup(origin);
        }
      } catch (e) { }
      scanning = false;
      if (ownBusy) { try { a.setExternalBusy(false); } catch (e) { } }
    }

    const okN = results.filter(r => r.ok).length;
    const message = `分组归属扫描完成：${okN}/${targets.length} 组成功` +
      (results.length ? '（' + results.map(r => r.ok ? `${r.group}:${r.count}` : `${r.group}:失败`).join('，') + '）' : '');
    try { a.renderScan((okN ? '✅ ' : '❌ ') + message, 'task'); } catch (e) { }
    toast((okN ? '✅ ' : '❌ ') + message);
    return { ok: okN > 0, message, results, groups: targets };
  }

  /* ---------------- 设置 & 通信 ---------------- */
  function loadSettings() {
    chrome.storage.local.get(['ftDebug', 'ftWlMemberPassive'], (res) => {
      DEBUG = !!res.ftDebug;
      PASSIVE = res.ftWlMemberPassive !== false;
    });
  }
  chrome.storage.onChanged.addListener((c, area) => {
    if (area === 'local' && (c.ftDebug || c.ftWlMemberPassive)) loadSettings();
  });

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || !msg.action) return;
    if (msg.action === 'FT_MEMBER_SCAN') {
      scanAllGroups(Array.isArray(msg.groups) ? msg.groups : null)
        .then(r => sendResponse(r))
        .catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }
  });

  window.__FT_WL_MEMBER__ = {
    version: 1,
    snapshot: sendSnapshot,
    event: sendEvent,
    scanAllGroups,
    cleanGroup,
    isScanning: () => scanning
  };

  loadSettings();
  setInterval(passiveTick, TICK_MS);
  console.log(LOG, `wl_membership.js v1 就绪（isWatchlist=${isWatchlistPage()}）`);
})();