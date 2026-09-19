/* Firstrade 桥接后台 v8：支持 Tab 自动寻找、切换、唤醒与现场还原 */

const BRIDGE_BASE = 'http://127.0.0.1:18888';
const LOG = '[FT-BG]';
const WATCHLIST_URL = 'https://invest.firstrade.com/app/watchlist';

let previousTabId = null;

async function jsonFetch(url, options) {
  const res = await fetch(url, options);
  const txt = await res.text();
  let data;
  try { data = JSON.parse(txt); } catch (e) { data = { raw: txt }; }
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${txt.slice(0, 200)}`);
  return data;
}

/* ---------- 智能寻找并激活 /app/watchlist 标签页 ---------- */
async function ensureWatchlistActive(savePrevious = true) {
  return new Promise((resolve) => {
    chrome.tabs.query({}, async (tabs) => {
      // 1. 记录当前用户正在看的 Tab，以便后续切回
      if (savePrevious) {
        const currentActive = tabs.find(t => t.active && t.currentWindow);
        if (currentActive && !currentActive.url.includes('/app/watchlist')) {
          previousTabId = currentActive.id;
        }
      }

      // 2. 寻找是否有现成的 /app/watchlist
      let wlTab = tabs.find(t => t.url && t.url.includes('/app/watchlist'));

      if (wlTab) {
        // 激活已有 watchlist tab
        chrome.windows.update(wlTab.windowId, { focused: true });
        chrome.tabs.update(wlTab.id, { active: true }, (updated) => {
          resolve({ ok: true, tabId: updated.id, status: 'activated_existing' });
        });
        return;
      }

      // 3. 寻找是否有其他 Firstrade 页面（如 /app/positions, /app/order-status）
      let ftTab = tabs.find(t => t.url && t.url.includes('invest.firstrade.com'));
      if (ftTab) {
        chrome.windows.update(ftTab.windowId, { focused: true });
        chrome.tabs.update(ftTab.id, { url: WATCHLIST_URL, active: true }, (updated) => {
          // 等待加载完成
          const listener = (tid, info) => {
            if (tid === updated.id && info.status === 'complete') {
              chrome.tabs.onUpdated.removeListener(listener);
              resolve({ ok: true, tabId: updated.id, status: 'navigated_ft_tab' });
            }
          };
          chrome.tabs.onUpdated.addListener(listener);
        });
        return;
      }

      // 4. 完全没有打开过 Firstrade，新建一个 Tab
      chrome.tabs.create({ url: WATCHLIST_URL, active: true }, (newTab) => {
        const listener = (tid, info) => {
          if (tid === newTab.id && info.status === 'complete') {
            chrome.tabs.onUpdated.removeListener(listener);
            resolve({ ok: true, tabId: newTab.id, status: 'created_new_tab' });
          }
        };
        chrome.tabs.onUpdated.addListener(listener);
      });
    });
  });
}

/* ---------- 还原用户原先查看的 Tab ---------- */
function restorePreviousTab() {
  if (previousTabId !== null) {
    chrome.tabs.get(previousTabId, (tab) => {
      if (!chrome.runtime.lastError && tab) {
        chrome.tabs.update(previousTabId, { active: true });
      }
      previousTabId = null;
    });
  }
}

/* ---------- 持仓（覆盖式） ---------- */
async function syncPositions(positions, overwrite = false) {
  if (!positions || (!Object.keys(positions).length && !overwrite)) {
    return { status: 'skip', reason: 'empty' };
  }
  return jsonFetch(`${BRIDGE_BASE}/sync_positions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ positions: positions || {}, overwrite: !!overwrite })
  });
}

/* ---------- 订单痕迹（追加式） ---------- */
async function syncOrders(orders, verbose = false) {
  if (!orders || !Object.keys(orders).length) return { status: 'skip', reason: 'empty' };
  return jsonFetch(`${BRIDGE_BASE}/sync_orders`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ orders: orders, verbose: !!verbose })
  });
}

async function compactOrders(verbose = false) {
  return jsonFetch(`${BRIDGE_BASE}/compact_orders`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ verbose: !!verbose })
  });
}

/* ---------- 自选股「变更%」 ---------- */
async function syncWatchlist(quotes, overwrite = true) {
  if (!quotes || !Object.keys(quotes).length) return { status: 'skip', reason: 'empty' };
  return jsonFetch(`${BRIDGE_BASE}/sync_watchlist`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quotes: quotes, overwrite: !!overwrite })
  });
}

async function plotWithPositions(symbol, positions) {
  return jsonFetch(`${BRIDGE_BASE}/plot`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: symbol, positions: positions || {} })
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
  return jsonFetch(`${BRIDGE_BASE}/wl_source?${q.toString()}`, { method: 'GET' });
}

/* ---------- 远程添加任务队列 ---------- */
async function fetchWlTasks(max) {
  return jsonFetch(`${BRIDGE_BASE}/wl_tasks?max=${max || 3}`, { method: 'GET' });
}

async function postWlTaskResult(payload) {
  const res = await jsonFetch(`${BRIDGE_BASE}/wl_task_result`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  });
  // 检查是否设置了还原 Tab 并且所有任务处理完成
  chrome.storage.local.get(['ftWlRestoreTab'], (cfg) => {
    if (cfg.ftWlRestoreTab !== false) {
      setTimeout(restorePreviousTab, 600);
    }
  });
  return res;
}

async function fetchWlGroups() { return jsonFetch(`${BRIDGE_BASE}/wl_groups`, { method: 'GET' }); }

/* ---------- 开关迁移与默认值 ---------- */
function migrateFlags() {
  chrome.storage.local.get(
    ['ftAutoScrape', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoWatchlist',
      'ftOrderVerbose', 'ftWlSource', 'ftWlBack', 'ftWlAhead',
      'ftWlAgent', 'ftWlRestoreGroup', 'ftWlRestoreTab'],
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
      if (res.ftWlTargetGroup === undefined) patch.ftWlTargetGroup = 'ALL';   // ★ 默认目标分组
      if (res.ftWlStrictSync === undefined) patch.ftWlStrictSync = true;      // ★ 默认严格同步
      if (res.ftWlRestoreGroup === undefined) patch.ftWlRestoreGroup = true;
      if (res.ftWlRestoreTab === undefined) patch.ftWlRestoreTab = true; // ★ 默认开启完成切回原 Tab
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

// 后台定时保活与即时唤醒通道
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.action) return;

  const done = (p) => {
    p.then((data) => sendResponse({ ok: true, data }))
      .catch((err) => {
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
    case 'FT_WL_TASKS': return done(fetchWlTasks(msg.max));
    case 'FT_WL_TASK_RESULT': return done(postWlTaskResult(msg.payload));
    case 'FT_WL_GROUPS': return done(fetchWlGroups());
    /* ★ 唤醒与定位 Tab */
    case 'FT_ENSURE_WATCHLIST_TAB':
      return done(ensureWatchlistActive(true));
    case 'FT_RESTORE_TAB':
      restorePreviousTab();
      sendResponse({ ok: true });
      return true;
    default: return;
  }
});

console.log(LOG, 'service worker 就绪 (v8 支持智能 Tab 切换)');