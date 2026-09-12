/* Firstrade 桥接后台 v5：所有与本机 Python 的 HTTP 通信都在这里做。
   扩展上下文拥有 host_permissions 特权，不受页面 CORS / Private Network Access 限制。 */

const BRIDGE_BASE = 'http://127.0.0.1:18888';
const LOG = '[FT-BG]';

async function jsonFetch(url, options) {
  const res = await fetch(url, options);
  const txt = await res.text();
  let data;
  try { data = JSON.parse(txt); } catch (e) { data = { raw: txt }; }
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${txt.slice(0, 200)}`);
  return data;
}

/* ---------- 持仓（覆盖式，只保留最新快照） ---------- */
async function syncPositions(positions, overwrite = false) {
  if (!positions || (!Object.keys(positions).length && !overwrite)) {
    return { status: 'skip', reason: 'empty' };
  }
  return jsonFetch(`${BRIDGE_BASE}/sync_positions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ positions: positions || {}, overwrite: !!overwrite })
  });
}

/* ---------- 订单痕迹（追加式，永不覆盖） ---------- */
async function syncOrders(orders) {
  if (!orders || !Object.keys(orders).length) {
    return { status: 'skip', reason: 'empty' };
  }
  return jsonFetch(`${BRIDGE_BASE}/sync_orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ orders: orders })
  });
}

/* ---------- 自选股「变更%」（overwrite=true 全量覆盖 / false 增量合并） ---------- */
async function syncWatchlist(quotes, overwrite = true) {
  if (!quotes || !Object.keys(quotes).length) {
    return { status: 'skip', reason: 'empty' };
  }
  return jsonFetch(`${BRIDGE_BASE}/sync_watchlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quotes: quotes, overwrite: !!overwrite })
  });
}

/* 一次请求同时落盘 + 拉起图表，服务端保证「先写文件再启动 Python」 */
async function plotWithPositions(symbol, positions) {
  return jsonFetch(`${BRIDGE_BASE}/plot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: symbol, positions: positions || {} })
  });
}

async function ping() { return jsonFetch(`${BRIDGE_BASE}/ping`, { method: 'GET' }); }
async function fetchServerPositions() { return jsonFetch(`${BRIDGE_BASE}/positions`, { method: 'GET' }); }
async function fetchServerOrders() { return jsonFetch(`${BRIDGE_BASE}/orders`, { method: 'GET' }); }
async function fetchServerWatchlist() { return jsonFetch(`${BRIDGE_BASE}/watchlist`, { method: 'GET' }); }
async function fetchSectors() { return jsonFetch(`${BRIDGE_BASE}/sectors_all`, { method: 'GET' }); }

/* ---------- 旧开关迁移：ftAutoScrape -> ftAutoPositions / ftAutoOrders ---------- */
function migrateFlags() {
  chrome.storage.local.get(['ftAutoScrape', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoWatchlist'], (res) => {
    const patch = {};
    if (res.ftAutoPositions === undefined) patch.ftAutoPositions = res.ftAutoScrape === true;
    if (res.ftAutoOrders === undefined) patch.ftAutoOrders = res.ftAutoScrape === true;
    if (res.ftAutoWatchlist === undefined) patch.ftAutoWatchlist = false;
    if (Object.keys(patch).length) {
      chrome.storage.local.set(patch, () => {
        chrome.storage.local.remove('ftAutoScrape');
        console.log(LOG, '开关已迁移为独立三开关:', patch);
      });
    }
  });
}
chrome.runtime.onInstalled.addListener(migrateFlags);
chrome.runtime.onStartup.addListener(migrateFlags);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.action) return;

  const done = (p) => {
    p.then((data) => sendResponse({ ok: true, data }))
      .catch((err) => {
        console.warn(LOG, msg.action, '失败:', err);
        sendResponse({ ok: false, error: String(err && err.message ? err.message : err) });
      });
    return true;
  };

  switch (msg.action) {
    case 'FT_SYNC': return done(syncPositions(msg.payload, msg.overwrite));
    case 'FT_SYNC_ORDERS': return done(syncOrders(msg.payload));
    case 'FT_SYNC_WATCHLIST': return done(syncWatchlist(msg.payload, msg.overwrite));
    case 'FT_PLOT': return done(plotWithPositions(msg.symbol, msg.payload));
    case 'FT_PING': return done(ping());
    case 'FT_SERVER_POSITIONS': return done(fetchServerPositions());
    case 'FT_SERVER_ORDERS': return done(fetchServerOrders());
    case 'FT_SERVER_WATCHLIST': return done(fetchServerWatchlist());
    case 'FT_SECTORS': return done(fetchSectors());
    default: return;
  }
});

console.log(LOG, 'service worker 就绪 (v5)');