const $ = (id) => document.getElementById(id);
const fileInput = $('fileInput');
const pasteArea = $('pasteArea');
const pasteBtn = $('pasteBtn');
const clearBtn = $('clearBtn');
const maxTagsInput = $('maxTags');
const statusEl = $('status');
const bridgeEl = $('bridgeStatus');
const pageEl = $('pageStatus');
const dbgChk = $('dbgChk');
const autoChk = $('autoChk');

function setStatus(text, isError) {
  statusEl.style.color = isError ? '#b91c1c' : '#059669';
  statusEl.innerText = text;
}
function setBridge(text, isError) {
  bridgeEl.style.color = isError ? '#b91c1c' : '#059669';
  bridgeEl.innerText = text;
}

/* ---------- 通信 ---------- */
function sendToTab(msg) {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || !tabs[0] || !tabs[0].id) { resolve({ ok: false, error: '没有活动标签页' }); return; }
      chrome.tabs.sendMessage(tabs[0].id, msg, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message + '（请在 Firstrade 页面打开本插件，必要时刷新页面）' });
          return;
        }
        resolve(resp || { ok: false, error: '无响应' });
      });
    });
  });
}

function sendToBg(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (resp) => {
      if (chrome.runtime.lastError) { resolve({ ok: false, error: chrome.runtime.lastError.message }); return; }
      resolve(resp || { ok: false, error: '无响应' });
    });
  });
}

const PAGE_NAME = { positions: '持仓页 ✅', orders: '订单页 ✅', other: '其它页面（不会抓取）' };

async function refreshPageStatus() {
  const r = await sendToTab({ action: 'FT_STATUS' });
  if (!r.ok) { pageEl.innerText = '未检测到页面脚本：' + r.error; return; }
  pageEl.innerText =
    `当前：${PAGE_NAME[r.page] || r.page}   ${r.path}\n` +
    `自动抓取：${r.auto ? '已开启 ⚠️' : '已关闭（推荐）'}\n` +
    `可抓持仓：${r.canPositions ? '是' : '否'} ｜ 可抓订单：${r.canOrders ? '是' : '否'}\n` +
    `本页缓存：持仓 ${r.positions} 条 / 订单 ${r.orders} 笔`;
}

/* ---------- 初始化 ---------- */
chrome.storage.local.get(['stockData', 'maxTags', 'ftDebug', 'ftAutoScrape'], (res) => {
  if (res.maxTags) maxTagsInput.value = res.maxTags;
  dbgChk.checked = !!res.ftDebug;
  autoChk.checked = res.ftAutoScrape === true;
  if (res.stockData) {
    const keys = Object.keys(res.stockData);
    setStatus(`已缓存 ${keys.length} 个标的\n示例：${keys.slice(0, 8).join(', ')}`);
  } else {
    setStatus('尚未导入数据，请选择 description.json');
  }
  refreshPageStatus();
});

/* ---------- description.json -> {SYMBOL:[tag]} ---------- */
function buildMap(json) {
  const map = {};
  Object.keys(json).forEach((key) => {
    const arr = json[key];
    if (!Array.isArray(arr)) return;
    arr.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const sym = (item.symbol || '').toString().trim().toUpperCase();
      if (!sym) return;
      let tags = item.tag;
      if (typeof tags === 'string') tags = [tags];
      if (!Array.isArray(tags)) return;
      tags = tags.map(t => String(t).trim()).filter(Boolean);
      if (tags.length) {
        map[sym] = tags;
        if (sym.includes('-')) map[sym.replace(/-/g, '.')] = tags;
        else if (sym.includes('.')) map[sym.replace(/\./g, '-')] = tags;
      }
    });
  });
  return map;
}

function save(map) {
  const count = Object.keys(map).length;
  if (!count) { setStatus('解析成功，但没找到任何含 tag 的 symbol', true); return; }
  const maxTags = Math.max(1, Math.min(20, parseInt(maxTagsInput.value, 10) || 2));
  chrome.storage.local.set({ stockData: map, maxTags }, () => {
    if (chrome.runtime.lastError) { setStatus('写入失败：' + chrome.runtime.lastError.message, true); return; }
    setStatus(`导入成功！共 ${count} 个标的\n示例：${Object.keys(map).slice(0, 8).join(', ')}`);
    sendToTab({ action: 'refreshTags' });
  });
}

function handleText(text) {
  try { save(buildMap(JSON.parse(text))); }
  catch (err) { setStatus('解析 JSON 失败：' + err.message, true); }
}

/* ---------- 事件 ---------- */
fileInput.addEventListener('change', (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  setStatus('读取中…');
  const reader = new FileReader();
  reader.onerror = () => setStatus('文件读取失败，请改用粘贴方式', true);
  reader.onload = (ev) => handleText(ev.target.result);
  reader.readAsText(file, 'utf-8');
});

pasteBtn.addEventListener('click', () => {
  const text = pasteArea.value.trim();
  if (!text) { setStatus('粘贴框是空的', true); return; }
  handleText(text);
});

maxTagsInput.addEventListener('change', () => {
  const maxTags = Math.max(1, Math.min(20, parseInt(maxTagsInput.value, 10) || 2));
  chrome.storage.local.set({ maxTags }, () => {
    setStatus(`已设置为每行最多显示 ${maxTags} 个标签`);
    sendToTab({ action: 'refreshTags' });
  });
});

clearBtn.addEventListener('click', () => {
  chrome.storage.local.remove('stockData', () => {
    setStatus('已清空标签缓存');
    sendToTab({ action: 'refreshTags' });
  });
});

dbgChk.addEventListener('change', () => {
  chrome.storage.local.set({ ftDebug: dbgChk.checked }, () => {
    setBridge(dbgChk.checked ? '调试日志已开启（看页面 Console）' : '调试日志已关闭');
  });
});

autoChk.addEventListener('change', () => {
  chrome.storage.local.set({ ftAutoScrape: autoChk.checked }, () => {
    setBridge(autoChk.checked
      ? '⚠️ 自动抓取已开启：滚动/定时都会抓取并写入本机 JSON'
      : '✅ 自动抓取已关闭：只有手动按钮会写文件');
    setTimeout(refreshPageStatus, 300);
  });
});

$('pingBtn').addEventListener('click', async () => {
  setBridge('正在连接 127.0.0.1:18888 …');
  const r = await sendToBg({ action: 'FT_PING' });
  if (r.ok) setBridge('✅ 桥接服务正常\n' + JSON.stringify(r.data, null, 1));
  else setBridge('❌ 连不上桥接服务：' + r.error + '\n请在终端运行 bridge_server.py', true);
});

/* ② 持仓 */
$('scanBtn').addEventListener('click', async () => {
  setBridge('正在自动滚动抓取持仓全表，请勿操作页面…');
  const r = await sendToTab({ action: 'FT_SYNC_ALL' });
  if (r.ok) {
    const srv = r.server && r.server.ok ? '已覆盖写入本机 JSON ✅' : ('写入本机失败：' + JSON.stringify(r.server));
    setBridge(`共抓取 ${r.count} 只标的\n${srv}`);
  } else setBridge('抓取失败：' + r.error, true);
  refreshPageStatus();
});

$('dumpBtn').addEventListener('click', async () => {
  const r = await sendToTab({ action: 'FT_DUMP' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const keys = Object.keys(r.data || {});
  const sample = keys.slice(0, 3).map(k => {
    const p = r.data[k];
    return `${k}: 成本=${p.cost} 今日=${p.day_change} 盈亏=${p.gainloss}`;
  }).join('\n');
  setBridge(`本页已抓取 ${r.count} 只：\n${sample || '(空，请先点手动抓取)'}\n…${keys.slice(0, 20).join(',')}`);
  console.log('[FT-POPUP] 持仓', r.data);
});

$('serverBtn').addEventListener('click', async () => {
  const r = await sendToBg({ action: 'FT_SERVER_POSITIONS' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const d = r.data || {};
  const keys = Object.keys(d).filter(k => !k.startsWith('_'));
  setBridge(`本机 positions JSON 共 ${keys.length} 条\n${keys.slice(0, 25).join(', ')}`);
  console.log('[FT-POPUP] 本机 positions', d);
});

/* ③ 订单 */
$('scanOrdersBtn').addEventListener('click', async () => {
  setBridge('正在自动滚动抓取订单记录，请勿操作页面…');
  const r = await sendToTab({ action: 'FT_SCAN_ORDERS' });
  if (r.ok) {
    const d = (r.server && r.server.data) || {};
    const srv = r.server && r.server.ok
      ? `已追加写入本机 ✅ 新增 ${d.added ?? '?'} / 更新 ${d.updated ?? '?'} / 累计 ${d.total ?? '?'}`
      : ('写入本机失败：' + JSON.stringify(r.server));
    setBridge(`本页抓到 ${r.count} 笔订单\n${srv}`);
  } else setBridge('抓取失败：' + r.error, true);
  refreshPageStatus();
});

$('dumpOrdersBtn').addEventListener('click', async () => {
  const r = await sendToTab({ action: 'FT_DUMP_ORDERS' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const keys = Object.keys(r.data || {});
  const sample = keys.slice(0, 5).map(k => {
    const o = r.data[k];
    return `${o.date} ${o.symbol} ${o.side === 'buy' ? '买' : '卖'} $${o.amount ?? '?'} ${o.status || ''}`;
  }).join('\n');
  setBridge(`本页已抓取 ${r.count} 笔订单：\n${sample || '(空，请确认在 order-status 页面)'}`);
  console.log('[FT-POPUP] 订单', r.data);
});

$('serverOrdersBtn').addEventListener('click', async () => {
  const r = await sendToBg({ action: 'FT_SERVER_ORDERS' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const d = (r.data && r.data.orders) || {};
  const keys = Object.keys(d);
  const sample = keys.slice(-6).map(k => {
    const o = d[k];
    return `${o.date} ${o.symbol} ${o.side === 'buy' ? '买' : '卖'} $${o.amount ?? '?'}`;
  }).join('\n');
  setBridge(`本机 orders JSON 共 ${keys.length} 笔（最近几笔）：\n${sample}`);
  console.log('[FT-POPUP] 本机 orders', r.data);
});