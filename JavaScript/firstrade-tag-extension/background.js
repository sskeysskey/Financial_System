/* Firstrade 桥接后台 v6：所有与本机 Python 的 HTTP 通信都在这里做。
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

/* ---------- 订单痕迹（追加式，永不覆盖；默认 LEAN 精简字段） ---------- */
async function syncOrders(orders, verbose = false) {
  if (!orders || !Object.keys(orders).length) {
    return { status: 'skip', reason: 'empty' };
  }
  return jsonFetch(`${BRIDGE_BASE}/sync_orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ orders: orders, verbose: !!verbose })
  });
}

/* ---------- 一次性压缩历史订单 JSON ---------- */
async function compactOrders(verbose = false) {
  return jsonFetch(`${BRIDGE_BASE}/compact_orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ verbose: !!verbose })
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

/* 一次请求同时落盘 + 拉起图表 */
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

/* ---------- ★ 自选股补齐的数据源统一入口 ---------- */
async function fetchWlSource(src, back, ahead) {
  const q = new URLSearchParams();
  q.set('src', src || 'earnings');
  if (back !== undefined && back !== null && back !== '') q.set('back', String(back));
  if (ahead !== undefined && ahead !== null && ahead !== '') q.set('ahead', String(ahead));
  return jsonFetch(`${BRIDGE_BASE}/wl_source?${q.toString()}`, { method: 'GET' });
}

/* ---------- 开关迁移与默认值 ---------- */
function migrateFlags() {
  chrome.storage.local.get(
    ['ftAutoScrape', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoWatchlist',
      'ftOrderVerbose', 'ftWlSource', 'ftWlBack', 'ftWlAhead'],
    (res) => {
      const patch = {};
      if (res.ftAutoPositions === undefined) patch.ftAutoPositions = res.ftAutoScrape === true;
      if (res.ftAutoOrders === undefined) patch.ftAutoOrders = res.ftAutoScrape === true;
      if (res.ftAutoWatchlist === undefined) patch.ftAutoWatchlist = false;
      if (res.ftOrderVerbose === undefined) patch.ftOrderVerbose = false;   // 默认精简
      if (res.ftWlSource === undefined) patch.ftWlSource = 'earnings';      // 默认财报日历
      if (res.ftWlBack === undefined) patch.ftWlBack = 1;
      if (res.ftWlAhead === undefined) patch.ftWlAhead = 0;
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
    default: return;
  }
});

console.log(LOG, 'service worker 就绪 (v6)');