/* ============================================================================
 * Firstrade 桥接后台 v10.1
 *  ★ FT_RUN_ON_PAGE / FT_PEEK_PAGE / FT_COMBO（同 v10）
 *  ★ FT_POS_QUOTE：G 键取数 —— 读持仓页单行（隐藏标签页会短暂切过去再切回，不抢窗口焦点）
 *  ★ FT_WL_ENQUEUE：持仓页成交后「移出分组」排队给自选股页代理
 *  ★ 修复：migrateFlags 漏读 ftTradeMode → 每次启动都把下单模式重置为预演
 * ==========================================================================*/

const BRIDGE_BASE = 'http://127.0.0.1:18888';
const LOG = '[FT-BG]';
const FT_HOST = 'invest.firstrade.com';
const FT_ORIGIN = 'https://' + FT_HOST;

const PAGE_URL = {
  positions: FT_ORIGIN + '/app/positions',
  orders: FT_ORIGIN + '/app/order-status',
  watchlist: FT_ORIGIN + '/app/watchlist'
};
const PAGE_RE = {
  positions: /\/positions?(\/|$)/i,
  orders: /\/order-status/i,
  watchlist: /\/watchlist/i
};
const PAGE_LABEL = { positions: '持仓页', orders: '订单页', watchlist: '自选股页' };
const READY_TIMEOUT = 60000;
const WL_JOB_TIMEOUT = 90 * 60 * 1000;
const DEFAULT_GROUP = 'Earning';

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function jsonFetch(url, options) {
  const res = await fetch(url, options);
  const txt = await res.text();
  let data;
  try { data = JSON.parse(txt); } catch (e) { data = { raw: txt }; }
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${txt.slice(0, 200)}`);
  return data;
}
const postJson = (path, body) => jsonFetch(`${BRIDGE_BASE}${path}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {})
});

/* ==================== 页面识别 & 标签页工具 ==================== */
function pageOfUrl(url) {
  try {
    const u = new URL(url);
    if (u.hostname !== FT_HOST) return null;
    for (const k of Object.keys(PAGE_RE)) if (PAGE_RE[k].test(u.pathname)) return k;
    return 'other';
  } catch (e) { return null; }
}

function tabMsg(tabId, msg) {
  return new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, msg, (resp) => {
        if (chrome.runtime.lastError) {
          const m = chrome.runtime.lastError.message || '';
          resolve({ ok: false, error: m, noReceiver: /Receiving end|Could not establish/i.test(m) });
          return;
        }
        resolve(resp || { ok: false, error: '无响应' });
      });
    } catch (e) { resolve({ ok: false, error: String(e) }); }
  });
}

async function activeTab() {
  try {
    const [t] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    return t || null;
  } catch (e) { return null; }
}
async function ftTabs() {
  try { return await chrome.tabs.query({ url: FT_ORIGIN + '/*' }); } catch (e) { return []; }
}
const byRecent = (a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0);

async function findPageTab(page) {
  const cur = await activeTab();
  if (cur && pageOfUrl(cur.url) === page) return cur;
  const hits = (await ftTabs()).filter(t => pageOfUrl(t.url) === page).sort(byRecent);
  return hits[0] || null;
}

async function openPageTab(page, activate = true, focusWindow = true) {
  const cur = await activeTab();
  let tab = await findPageTab(page);
  let how = 'existing';
  if (!tab) {
    const pool = (await ftTabs())
      .filter(t => page === 'watchlist' || pageOfUrl(t.url) !== 'watchlist')
      .sort(byRecent);
    const nav = (cur && pool.find(t => t.id === cur.id)) || pool[0];
    if (nav) {
      tab = await chrome.tabs.update(nav.id, { url: PAGE_URL[page] });
      how = 'navigated';
    } else {
      tab = await chrome.tabs.create({ url: PAGE_URL[page], active: activate });
      how = 'created';
    }
  }
  if (activate) {
    try { await chrome.tabs.update(tab.id, { active: true }); } catch (e) { }
    if (focusWindow) { try { await chrome.windows.update(tab.windowId, { focused: true }); } catch (e) { } }
  }
  return { tab, how, originTabId: (cur && cur.id !== tab.id) ? cur.id : null };
}

async function waitPageReady(tabId, page, timeout) {
  const t0 = Date.now();
  let reloaded = false, looksSince = 0, mismatchSince = 0, noRecvSince = 0;
  while (Date.now() - t0 < timeout) {
    let tab;
    try { tab = await chrome.tabs.get(tabId); } catch (e) { return { ok: false, error: '目标标签页已被关闭' }; }
    if (tab.status === 'complete') {
      const pg = pageOfUrl(tab.url || '');
      if (pg !== page) {
        mismatchSince = mismatchSince || Date.now();
        if (Date.now() - mismatchSince > 8000) {
          return { ok: false, error: `页面停在 ${tab.url}，不是${PAGE_LABEL[page]}：Firstrade 可能未登录或会话已过期，请先登录后重试` };
        }
      } else {
        mismatchSince = 0;
        const r = await tabMsg(tabId, { action: 'FT_PAGE_READY', page });
        if (r && r.ok) {
          noRecvSince = 0;
          if (r.loggedOut) return { ok: false, error: '检测到登录框：Firstrade 未登录，请先登录后重试' };
          if (r.ready) return { ok: true, waited: Date.now() - t0 };
          if (r.looks) {
            looksSince = looksSince || Date.now();
            if (Date.now() - looksSince > 6000) return { ok: true, waited: Date.now() - t0, weak: true };
          } else looksSince = 0;
        } else if (r && r.noReceiver) {
          noRecvSince = noRecvSince || Date.now();
          if (!reloaded && Date.now() - noRecvSince > 3000) {
            reloaded = true; noRecvSince = 0;
            console.log(LOG, '页面脚本未注入，刷新标签页', tabId);
            try { await chrome.tabs.reload(tabId); } catch (e) { }
            await sleep(1500);
            continue;
          }
        }
      }
    }
    await sleep(600);
  }
  return { ok: false, error: `等待${PAGE_LABEL[page]}加载超时（${Math.round(timeout / 1000)}s），请检查网络或是否已登录` };
}

function keepAlive() {
  const h = setInterval(() => { try { chrome.runtime.getPlatformInfo(() => { }); } catch (e) { } }, 20000);
  return () => clearInterval(h);
}

function slimResp(resp) {
  if (!resp || typeof resp !== 'object') return resp || null;
  try { if (JSON.stringify(resp).length <= 60000) return resp; } catch (e) { }
  const out = {};
  Object.keys(resp).forEach(k => { if (!['data', 'list', 'clearList'].includes(k)) out[k] = resp[k]; });
  out._truncated = true;
  return out;
}

const setLastOp = (op) => chrome.storage.local.set({ ftLastOp: op });

async function execOnPage(opt) {
  const page = opt.page;
  const msg = opt.msg || {};
  if (!PAGE_URL[page]) return { ok: false, error: '未知页面: ' + page };
  try {
    const loc = await openPageTab(page, opt.activate !== false, opt.focusWindow !== false);
    console.log(LOG, `[${opt.kind || msg.action}] ${PAGE_LABEL[page]} → ${loc.how} tab=${loc.tab.id}`);
    const rd = await waitPageReady(loc.tab.id, page, opt.readyTimeout || READY_TIMEOUT);
    if (!rd.ok) return { ok: false, error: rd.error, how: loc.how, tabId: loc.tab.id, originTabId: loc.originTabId };
    await sleep(rd.waited > 1500 ? 900 : 250);
    const resp = await tabMsg(loc.tab.id, msg);
    return {
      ok: !!(resp && resp.ok), resp, how: loc.how, tabId: loc.tab.id, originTabId: loc.originTabId,
      error: (resp && !resp.ok) ? (resp.error || resp.message || '执行失败') : ''
    };
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e) };
  }
}

async function restoreTab(origin) {
  if (!origin) return;
  const cfg = await chrome.storage.local.get(['ftWlRestoreTab']);
  if (cfg.ftWlRestoreTab === false) return;
  try {
    const t = await chrome.tabs.get(origin);
    await chrome.tabs.update(origin, { active: true });
    await chrome.windows.update(t.windowId, { focused: true });
  } catch (e) { }
}
/* 只切回标签，不抢 OS 窗口焦点（G 键取数用，避免 Chrome 盖住图表窗口） */
async function restoreTabQuiet(origin) {
  if (!origin) return;
  try { await chrome.tabs.update(origin, { active: true }); } catch (e) { }
}

async function runOnPage(opt) {
  const page = opt.page;
  const msg = opt.msg || {};
  const kind = opt.kind || msg.action || '';
  const label = opt.label || '';
  const stop = keepAlive();
  const id = Date.now() + '_' + Math.random().toString(36).slice(2, 6);
  await setLastOp({ id, kind, label, page, state: 'running', ts: Date.now() });
  let result;
  try { result = await execOnPage(Object.assign({}, opt, { kind })); }
  finally { stop(); }
  if (result.ok && opt.restore && result.originTabId) await restoreTab(result.originTabId);
  await setLastOp({
    id, kind, label, page, state: 'done', ts: Date.now(),
    ok: result.ok, error: result.error, how: result.how, resp: slimResp(result.resp)
  });
  return result;
}

async function peekPage(page, msg) {
  const tab = await findPageTab(page);
  if (!tab) return { ok: false, noTab: true, error: `尚未打开${PAGE_LABEL[page] || page}` };
  const r = await tabMsg(tab.id, msg || {});
  if (r && typeof r === 'object') r.tabId = tab.id;
  return r;
}

/* ==================== ★ G 键：读持仓页单行 ==================== */
async function posQuote(symbol) {
  const sym = String(symbol || '').trim().toUpperCase();
  if (!sym) return { ok: false, error: 'symbol 为空' };
  const stop = keepAlive();
  try {
    const tab = await findPageTab('positions');
    if (tab) {
      const r = await tabMsg(tab.id, { action: 'FT_POS_ROW', symbol: sym, scroll: false });
      // 只有页面处于可见状态时，表格数据才保证是最新的
      if (r && r.ok && r.found && !r.hidden) return Object.assign({ how: 'visible' }, r);
    }
    const ex = await execOnPage({
      page: 'positions', kind: 'pos_quote', activate: true, focusWindow: false, readyTimeout: 30000,
      msg: { action: 'FT_POS_ROW', symbol: sym, scroll: true, settle: true }
    });
    if (ex.originTabId) await restoreTabQuiet(ex.originTabId);
    if (!ex.resp || !ex.resp.ok) return { ok: false, error: ex.error || '持仓页读取失败' };
    return Object.assign({ how: ex.how }, ex.resp);
  } finally { stop(); }
}

/* ==================== ★ 排队远程增删（不激活/不跳转任何标签页） ==================== */
async function enqueueSymbolTask(task, symbol, group) {
  const path = task === 'add' ? '/wl_add' : '/wl_remove';
  const r = await postJson(path, { symbol, group, wait: 0, restore: true, activate: false });
  const tab = await findPageTab('watchlist');
  if (tab) tabMsg(tab.id, { action: 'FT_WAKE_UP' });
  return Object.assign({}, r, { watchlistTab: !!tab });
}

/* ==================== 组合任务 ==================== */
const fmtPos = (r) => `${r.count ?? '?'} 只` + (r.server && r.server.ok ? '，已覆盖写入本机' : '，写入本机失败');
const fmtOrd = (r) => {
  const d = (r.server && r.server.data) || {};
  return `${r.count ?? '?'} 笔` + (r.server && r.server.ok ? `，新增 ${d.added ?? '?'} / 累计 ${d.total ?? '?'}` : '，写入本机失败');
};
const PHASE_TXT = { idle: '收尾', group: '切换分组', diff: '比对差集', clear: '删除中', add: '添加中', verify: '复核中' };

const fmtQuotes = (r) => r.empty
  ? (r.message || `分组「${r.group || '?'}」为空，已清空本机 JSON`)
  : `${r.count ?? '?'} 只（分组「${r.group || '?'}」）` + (r.server && r.server.ok ? '，已覆盖写入' : '，写入失败');

const COMBOS = {
  combo_all: {
    label: '一键全流程（持仓 → 订单 → 同步 Earning → 变更% → 分组归属）',
    steps: (o) => {
      const tg = o.targetGroup || DEFAULT_GROUP;
      return [
        { page: 'positions', label: '① 抓取全部持仓', msg: { action: 'FT_SYNC_ALL' }, fmt: fmtPos },
        { page: 'orders', label: '② 抓取订单记录', msg: { action: 'FT_SCAN_ORDERS' }, fmt: fmtOrd },
        {
          page: 'watchlist', label: `③ 一键同步「${tg}」`, waitJob: true,
          msg: { action: 'FT_WL_START', clearFirst: false, strictSync: o.strictSync !== false, targetGroup: tg, skipQuotes: true }
        },
        { page: 'watchlist', label: '④ 抓取全部变更%', msg: { action: 'FT_WL_SCAN_QUOTES' }, fmt: fmtQuotes },
        { page: 'watchlist', label: '⑤ 扫描全部分组归属', msg: { action: 'FT_MEMBER_SCAN' }, fmt: r => r.message || 'OK' }
      ];
    }
  }
};

async function waitWlJob(tabId, onTick) {
  const t0 = Date.now();
  let idle = 0, last = null;
  await sleep(1200);
  while (Date.now() - t0 < WL_JOB_TIMEOUT) {
    const st = await tabMsg(tabId, { action: 'FT_WL_STATUS' });
    if (st && st.ok) {
      last = st;
      if (st.running || st.finishing) {
        idle = 0;
        if (onTick) { try { await onTick(st); } catch (e) { } }
      } else {
        const saved = ((await chrome.storage.local.get(['ftWlJob'])).ftWlJob) || {};
        if (saved.autoResume === true) idle = 0;
        else if (++idle >= 2) break;
      }
    }
    await sleep(1500);
  }
  if (!last) return { ok: false, msg: '无法读取自选股任务状态' };
  if (last.running || last.finishing) return { ok: false, msg: '等待任务结束超时' };
  const fails = (last.failed || 0) + (last.clearFailed || 0);
  const did = (last.cleared || 0) + (last.added || 0);
  const ok = fails === 0 && !(last.lastError && did === 0 && last.lastError.indexOf('一致') < 0);
  let msg = `删除 ${last.cleared || 0}（失败 ${last.clearFailed || 0}）｜新增 ${last.added || 0}（失败 ${last.failed || 0}）`;
  if (did === 0 && fails === 0 && !last.lastError) msg = '分组已与数据源一致，无需改动';
  if (last.lastError) msg += `｜最后错误：${last.lastError}`;
  return { ok, msg };
}

async function runCombo(msg) {
  const kind = msg.combo;
  const C = COMBOS[kind];
  if (!C) return { ok: false, error: '未知组合任务：' + kind };
  const steps = C.steps(msg.opts || {});
  const id = Date.now() + '_' + Math.random().toString(36).slice(2, 6);
  const out = [];
  let origin = null;
  const stop = keepAlive();
  const progress = (i, extra) => setLastOp({
    id, kind, label: C.label, state: 'running', ts: Date.now(), steps: out.slice(),
    progress: `步骤 ${i + 1}/${steps.length}：${steps[i].label}${extra ? '｜' + extra : ''}`
  });
  try {
    for (let i = 0; i < steps.length; i++) {
      const s = steps[i];
      await progress(i);
      const r = await execOnPage({ page: s.page, msg: s.msg, kind, readyTimeout: READY_TIMEOUT });
      if (i === 0) origin = r.originTabId || null;
      let ok = !!r.ok;
      if (ok && r.resp && r.resp.server && r.resp.server.ok === false) ok = false;
      let text = r.ok ? (s.fmt ? s.fmt(r.resp || {}) : 'OK') : (r.error || '失败');
      if (r.ok && s.waitJob) {
        const w = await waitWlJob(r.tabId, (st) => progress(i,
          `${PHASE_TXT[st.phase] || st.phase}｜待删 ${st.toRemove}｜待加 ${st.toAdd}｜已删 ${st.cleared}｜已加 ${st.added}`));
        ok = w.ok; text = w.msg;
      }
      out.push({ label: s.label, ok, msg: text });
    }
  } finally { stop(); }
  const allOk = out.length === steps.length && out.every(x => x.ok);
  if (allOk && origin) await restoreTab(origin);
  const result = { ok: allOk, error: allOk ? '' : '部分步骤失败（见下方明细）', resp: { steps: out } };
  await setLastOp({ id, kind, label: C.label, state: 'done', ts: Date.now(), ok: allOk, error: result.error, resp: result.resp });
  return result;
}

/* ==================== 桥接 API ==================== */
async function syncPositions(positions, overwrite = false) {
  if (!positions || (!Object.keys(positions).length && !overwrite)) return { status: 'skip', reason: 'empty' };
  return postJson('/sync_positions', { positions: positions || {}, overwrite: !!overwrite });
}
async function syncOrders(orders, verbose = false) {
  if (!orders || !Object.keys(orders).length) return { status: 'skip', reason: 'empty' };
  return postJson('/sync_orders', { orders, verbose: !!verbose });
}
const compactOrders = (verbose = false) => postJson('/compact_orders', { verbose: !!verbose });
async function syncWatchlist(quotes, overwrite = true, group = '') {
  if (!quotes || (!Object.keys(quotes).length && !overwrite)) return { status: 'skip', reason: 'empty' };
  return postJson('/sync_watchlist', { quotes: quotes || {}, overwrite: !!overwrite, group: group || '' });
}
const plotWithPositions = (symbol, positions) => postJson('/plot', { symbol, positions: positions || {} });
const ping = () => jsonFetch(`${BRIDGE_BASE}/ping`, { method: 'GET' });
const fetchServerPositions = () => jsonFetch(`${BRIDGE_BASE}/positions`, { method: 'GET' });
const fetchServerOrders = () => jsonFetch(`${BRIDGE_BASE}/orders`, { method: 'GET' });
const fetchServerWatchlist = () => jsonFetch(`${BRIDGE_BASE}/watchlist`, { method: 'GET' });
const fetchSectors = () => jsonFetch(`${BRIDGE_BASE}/sectors_all`, { method: 'GET' });

async function fetchWlSource(src, back, ahead) {
  const q = new URLSearchParams();
  q.set('src', src || 'earnings');
  if (back !== undefined && back !== null && back !== '') q.set('back', String(back));
  if (ahead !== undefined && ahead !== null && ahead !== '') q.set('ahead', String(ahead));
  q.set('fallback', '0');
  return jsonFetch(`${BRIDGE_BASE}/wl_source?${q.toString()}`, { method: 'GET' });
}
const fetchWlTasks = (max) => jsonFetch(`${BRIDGE_BASE}/wl_tasks?max=${max || 3}`, { method: 'GET' });
const postWlTaskResult = (p) => postJson('/wl_task_result', p);
const fetchWlGroups = () => jsonFetch(`${BRIDGE_BASE}/wl_groups`, { method: 'GET' });
const postMembership = (p) => postJson('/wl_membership', p);
const postMembershipEvent = (p) => postJson('/wl_membership_event', p);
const fetchMembership = () => jsonFetch(`${BRIDGE_BASE}/wl_membership`, { method: 'GET' });
const postTradeLog = (p) => postJson('/trade_log', p);

/* ==================== 开关迁移与默认值 ==================== */
function migrateFlags() {
  chrome.storage.local.get(
    ['ftAutoScrape', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoWatchlist',
      'ftOrderVerbose', 'ftWlSource', 'ftWlBack', 'ftWlAhead',
      'ftWlAgent', 'ftWlRestoreGroup', 'ftWlRestoreTab', 'ftSymColor',
      'ftWlTargetGroup', 'ftWlStrictSync', 'ftWlMemberPassive',
      'ftTradeEnabled', 'ftTradeMode', 'ftTradeRemoveAfter', 'ftTradePresets'],     // ★ 补上 ftTradeMode
    (res) => {
      const patch = {};
      if (res.ftAutoPositions === undefined) patch.ftAutoPositions = res.ftAutoScrape === true;
      if (res.ftAutoOrders === undefined) patch.ftAutoOrders = res.ftAutoScrape === true;
      if (res.ftAutoWatchlist === undefined) patch.ftAutoWatchlist = false;
      if (res.ftOrderVerbose === undefined) patch.ftOrderVerbose = false;
      if (res.ftWlSource === undefined) patch.ftWlSource = 'earnings';
      if (res.ftWlBack === undefined) patch.ftWlBack = 1;
      if (res.ftWlAhead === undefined) patch.ftWlAhead = 0;
      if (res.ftWlAgent === undefined) patch.ftWlAgent = true;
      const tg = String(res.ftWlTargetGroup || '').trim();
      if (!tg || tg.toUpperCase() === 'ALL') patch.ftWlTargetGroup = DEFAULT_GROUP;
      if (res.ftWlStrictSync === undefined) patch.ftWlStrictSync = true;
      if (res.ftWlRestoreGroup === undefined) patch.ftWlRestoreGroup = true;
      if (res.ftWlRestoreTab === undefined) patch.ftWlRestoreTab = true;
      if (res.ftWlMemberPassive === undefined) patch.ftWlMemberPassive = true;
      if (res.ftTradeEnabled === undefined) patch.ftTradeEnabled = true;
      if (!['dry', 'confirm', 'live'].includes(res.ftTradeMode)) patch.ftTradeMode = 'dry';
      if (res.ftTradeRemoveAfter === undefined) patch.ftTradeRemoveAfter = true;
      if (!Array.isArray(res.ftTradePresets) || !res.ftTradePresets.length) patch.ftTradePresets = [1000, 2000, 3000];
      if (res.ftSymColor === undefined) patch.ftSymColor = true;
      if (Object.keys(patch).length) {
        chrome.storage.local.set(patch, () => {
          chrome.storage.local.remove('ftAutoScrape');
          console.log(LOG, '默认值/开关已初始化:', patch);
        });
      }
    });
}
chrome.runtime.onInstalled.addListener(migrateFlags);
chrome.runtime.onStartup.addListener(migrateFlags);

/* ==================== 消息分发 ==================== */
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.action) return;
  const done = (p) => {
    p.then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: String(err && err.message ? err.message : err) }));
    return true;
  };
  const direct = (p) => {
    p.then((r) => sendResponse(r))
      .catch((err) => sendResponse({ ok: false, error: String(err && err.message ? err.message : err) }));
    return true;
  };

  switch (msg.action) {
    case 'FT_SYNC': return done(syncPositions(msg.payload, msg.overwrite));
    case 'FT_SYNC_ORDERS': return done(syncOrders(msg.payload, msg.verbose));
    case 'FT_COMPACT_ORDERS': return done(compactOrders(msg.verbose));
    case 'FT_SYNC_WATCHLIST': return done(syncWatchlist(msg.payload, msg.overwrite, msg.group));
    case 'FT_PLOT': return done(plotWithPositions(msg.symbol, msg.payload));
    case 'FT_PING': return done(ping());
    case 'FT_SERVER_POSITIONS': return done(fetchServerPositions());
    case 'FT_SERVER_ORDERS': return done(fetchServerOrders());
    case 'FT_SERVER_WATCHLIST': return done(fetchServerWatchlist());
    case 'FT_SECTORS': return done(fetchSectors());
    case 'FT_WL_SOURCE': return done(fetchWlSource(msg.src, msg.back, msg.ahead));
    case 'FT_WL_TASKS': return done(fetchWlTasks(msg.max));
    case 'FT_WL_TASK_RESULT': return done(postWlTaskResult(msg.payload));
    case 'FT_WL_GROUPS': return done(fetchWlGroups());
    case 'FT_WL_MEMBERSHIP': return done(postMembership(msg.payload));
    case 'FT_WL_MEMBERSHIP_EVENT': return done(postMembershipEvent(msg.payload));
    case 'FT_SERVER_MEMBERSHIP': return done(fetchMembership());
    case 'FT_TRADE_LOG': return done(postTradeLog(msg.payload));
    case 'FT_WL_ENQUEUE': return done(enqueueSymbolTask(msg.task, msg.symbol, msg.group));

    case 'FT_POS_QUOTE': return direct(posQuote(msg.symbol));
    case 'FT_RUN_ON_PAGE': return direct(runOnPage(msg));
    case 'FT_PEEK_PAGE': return direct(peekPage(msg.page, msg.msg));
    case 'FT_COMBO': return direct(runCombo(msg));
    case 'FT_ENSURE_WATCHLIST_TAB':
      return done(openPageTab('watchlist', true).then(r => ({ tabId: r.tab.id, status: r.how })));
    case 'FT_RESTORE_TAB':
      sendResponse({ ok: true });
      return;
    default: return;
  }
});

console.log(LOG, 'service worker 就绪 (v10.1：持仓页交易 / 按股数下单 / G 键取变更%)');