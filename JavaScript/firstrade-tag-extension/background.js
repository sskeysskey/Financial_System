/* Firstrade 桥接后台：所有与本机 Python 的 HTTP 通信都在这里做，
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

/* 只同步持仓数据 */
async function syncPositions(positions) {
  if (!positions || !Object.keys(positions).length) {
    return { status: 'skip', reason: 'empty' };
  }
  return jsonFetch(`${BRIDGE_BASE}/sync_positions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(positions)
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

async function ping() {
  return jsonFetch(`${BRIDGE_BASE}/ping`, { method: 'GET' });
}

async function fetchServerPositions() {
  return jsonFetch(`${BRIDGE_BASE}/positions`, { method: 'GET' });
}

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
    case 'FT_SYNC': return done(syncPositions(msg.payload));
    case 'FT_PLOT': return done(plotWithPositions(msg.symbol, msg.payload));
    case 'FT_PING': return done(ping());
    case 'FT_SERVER_POSITIONS': return done(fetchServerPositions());
    default: return;
  }
});

console.log(LOG, 'service worker 就绪');