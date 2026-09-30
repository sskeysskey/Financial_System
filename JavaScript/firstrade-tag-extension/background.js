/* ============================================================================
 * Firstrade 桥接后台 v9
 *  ★ FT_RUN_ON_PAGE：自动 定位已开页面 / 跳转其它 Firstrade 标签页 / 新开标签页
 *                     → 等待页面就绪（识别未登录/会话过期/脚本未注入）→ 执行 → 成功后切回原标签页
 *  ★ FT_PEEK_PAGE  ：不切换标签页，直接向对应页面查询状态
 *  ★ 结果写入 storage.ftLastOp（popup 因切标签被关闭也不丢结果）
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

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function jsonFetch(url, options) {
  const res = await fetch(url, options);
  const txt = await res.text();
  let data;
  try { data = JSON.parse(txt); } catch (e) { data = { raw: txt }; }
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${txt.slice(0, 200)}`);
  return data;
}

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

/* 定位 → 跳转 → 新开；不会把 watchlist 标签页（远程代理/同步任务所在）跳走去别的页面 */
async function openPageTab(page, activate = true) {
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
    try { await chrome.windows.update(tab.windowId, { focused: true }); } catch (e) { }
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
          if (!reloaded && Date.now() - noRecvSince > 3000) {      // 扩展更新后旧页面没有脚本 → 刷新一次
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

/* MV3 service worker 30s 空闲会被回收：长任务期间定时调用扩展 API 续命 */
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

async function runOnPage(opt) {
  const page = opt.page;
  const msg = opt.msg || {};
  const kind = opt.kind || msg.action || '';
  const label = opt.label || '';
  if (!PAGE_URL[page]) return { ok: false, error: '未知页面: ' + page };

  const stop = keepAlive();
  const id = Date.now() + '_' + Math.random().toString(36).slice(2, 6);
  await setLastOp({ id, kind, label, page, state: 'running', ts: Date.now() });

  let result, origin = null;
  try {
    const loc = await openPageTab(page, opt.activate !== false);
    origin = loc.originTabId;
    console.log(LOG, `[${kind}] ${PAGE_LABEL[page]} → ${loc.how} tab=${loc.tab.id}`);
    const rd = await waitPageReady(loc.tab.id, page, opt.readyTimeout || READY_TIMEOUT);
    if (!rd.ok) throw new Error(rd.error);
    await sleep(rd.waited > 1500 ? 900 : 250);           // 刚加载完的页面给 ag-Grid 一点渲染时间
    const resp = await tabMsg(loc.tab.id, msg);
    result = {
      ok: !!(resp && resp.ok), resp, how: loc.how, tabId: loc.tab.id,
      error: (resp && !resp.ok) ? (resp.error || resp.message || '执行失败') : ''
    };
  } catch (e) {
    result = { ok: false, error: String((e && e.message) || e) };
  } finally { stop(); }

  // 只有成功才切回原标签页；失败（如未登录）停在 Firstrade 页面便于处理
  if (result.ok && opt.restore && origin) {
    const cfg = await chrome.storage.local.get(['ftWlRestoreTab']);
    if (cfg.ftWlRestoreTab !== false) {
      try {
        const t = await chrome.tabs.get(origin);
        await chrome.tabs.update(origin, { active: true });
        await chrome.windows.update(t.windowId, { focused: true });
      } catch (e) { }
    }
  }
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

/* ==================== 桥接 API ==================== */
async function syncPositions(positions, overwrite = false) {
  if (!positions || (!Object.keys(positions).length && !overwrite)) return { status: 'skip', reason: 'empty' };
  return jsonFetch(`${BRIDGE_BASE}/sync_positions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ positions: positions || {}, overwrite: !!overwrite })
  });
}
async function syncOrders(orders, verbose = false) {
  if (!orders || !Object.keys(orders).length) return { status: 'skip', reason: 'empty' };
  return jsonFetch(`${BRIDGE_BASE}/sync_orders`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ orders, verbose: !!verbose })
  });
}
async function compactOrders(verbose = false) {
  return jsonFetch(`${BRIDGE_BASE}/compact_orders`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ verbose: !!verbose })
  });
}
async function syncWatchlist(quotes, overwrite = true) {
  if (!quotes || !Object.keys(quotes).length) return { status: 'skip', reason: 'empty' };
  return jsonFetch(`${BRIDGE_BASE}/sync_watchlist`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quotes, overwrite: !!overwrite })
  });
}
async function plotWithPositions(symbol, positions) {
  return jsonFetch(`${BRIDGE_BASE}/plot`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, positions: positions || {} })
  });
}
async function ping() { return jsonFetch(`${BRIDGE_BASE}/ping`, { method: 'GET' }); }
async function fetchServerPositions() { return jsonFetch(`${BRIDGE_BASE}/positions`, { method: 'GET' }); }
async function fetchServerOrders() { return jsonFetch(`${BRIDGE_BASE}/orders`, { method: 'GET' }); }
async function fetchServerWatchlist() { return jsonFetch(`${BRIDGE_BASE}/watchlist`, { method: 'GET' }); }
async function fetchSectors() { return jsonFetch(`${BRIDGE_BASE}/sectors_all`, { method: 'GET' }); }

async function fetchWlSource(src, back, ahead) {
  const q = new URLSearchParams();
  q.set('src', src || 'earnings');
  if (back !== undefined && back !== null && back !== '') q.set('back', String(back));
  if (ahead !== undefined && ahead !== null && ahead !== '') q.set('ahead', String(ahead));
  q.set('fallback', '0');                        // ★ 永不回退到最近财报日
  return jsonFetch(`${BRIDGE_BASE}/wl_source?${q.toString()}`, { method: 'GET' });
}
async function fetchWlTasks(max) { return jsonFetch(`${BRIDGE_BASE}/wl_tasks?max=${max || 3}`, { method: 'GET' }); }
async function postWlTaskResult(payload) {
  return jsonFetch(`${BRIDGE_BASE}/wl_task_result`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  });
}
async function fetchWlGroups() { return jsonFetch(`${BRIDGE_BASE}/wl_groups`, { method: 'GET' }); }
async function postMembership(payload) {
  return jsonFetch(`${BRIDGE_BASE}/wl_membership`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  });
}
async function postMembershipEvent(payload) {
  return jsonFetch(`${BRIDGE_BASE}/wl_membership_event`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  });
}
async function fetchMembership() { return jsonFetch(`${BRIDGE_BASE}/wl_membership`, { method: 'GET' }); }

/* ==================== 开关迁移与默认值 ==================== */
function migrateFlags() {
  chrome.storage.local.get(
    ['ftAutoScrape', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoWatchlist',
      'ftOrderVerbose', 'ftWlSource', 'ftWlBack', 'ftWlAhead',
      'ftWlAgent', 'ftWlRestoreGroup', 'ftWlRestoreTab',
      'ftWlTargetGroup', 'ftWlStrictSync', 'ftWlMemberPassive'],
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
      if (res.ftWlTargetGroup === undefined) patch.ftWlTargetGroup = 'ALL';
      if (res.ftWlStrictSync === undefined) patch.ftWlStrictSync = true;
      if (res.ftWlRestoreGroup === undefined) patch.ftWlRestoreGroup = true;
      if (res.ftWlRestoreTab === undefined) patch.ftWlRestoreTab = true;
      if (res.ftWlMemberPassive === undefined) patch.ftWlMemberPassive = true;
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
    case 'FT_SYNC_WATCHLIST': return done(syncWatchlist(msg.payload, msg.overwrite));
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

    /* ★ 全自动页面执行 / 免切换查询 */
    case 'FT_RUN_ON_PAGE': return direct(runOnPage(msg));
    case 'FT_PEEK_PAGE': return direct(peekPage(msg.page, msg.msg));
    case 'FT_ENSURE_WATCHLIST_TAB':
      return done(openPageTab('watchlist', true).then(r => ({ tabId: r.tab.id, status: r.how })));
    case 'FT_RESTORE_TAB':
      sendResponse({ ok: true });
      return;
    default: return;
  }
});

console.log(LOG, 'service worker 就绪 (v9：全功能自动定位/跳转/新开 Firstrade 页面)');