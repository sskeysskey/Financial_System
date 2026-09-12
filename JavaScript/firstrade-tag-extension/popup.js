const $ = (id) => document.getElementById(id);
const statusEl = $('status');
const bridgeEl = $('bridgeStatus');
const pageEl = $('pageStatus');
const wlEl = $('wlStatus');

function setStatus(text, isError) {
  statusEl.style.color = isError ? '#b91c1c' : '#059669';
  statusEl.innerText = text;
}
function setBridge(text, isError) {
  bridgeEl.style.color = isError ? '#b91c1c' : '#059669';
  bridgeEl.innerText = text;
}
function setWl(text, isError) {
  wlEl.style.color = isError ? '#b91c1c' : '#334155';
  wlEl.innerText = text;
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

const PAGE_NAME = {
  positions: '持仓页 ✅', orders: '订单页 ✅',
  watchlist: '自选股页 ✅', other: '其它页面（不会抓取）'
};

async function refreshPageStatus() {
  const r = await sendToTab({ action: 'FT_STATUS' });
  if (!r.ok) { pageEl.innerText = '未检测到页面脚本：' + r.error; return; }
  pageEl.innerText =
    `当前：${PAGE_NAME[r.page] || r.page}   ${r.path}\n` +
    `自动：持仓 ${r.autoPositions ? '开⚠️' : '关'} ｜ 订单 ${r.autoOrders ? '开⚠️' : '关'}\n` +
    `可抓持仓：${r.canPositions ? '是' : '否'} ｜ 可抓订单：${r.canOrders ? '是' : '否'}\n` +
    `本页缓存：持仓 ${r.positions} 条 / 订单 ${r.orders} 笔`;
}

async function refreshWlStatus() {
  const r = await sendToTab({ action: 'FT_WL_STATUS' });
  if (!r || !r.ok) { setWl('未检测到自选股脚本（请在 /app/watchlist 页面刷新一次）', true); return; }
  if (!r.page) { setWl(`当前不在自选股页面（${r.path}）\n请先打开 https://invest.firstrade.com/app/watchlist`); return; }
  setWl(
    `分组：${r.group || '(未识别)'}｜表内行数：${r.gridRows === null ? '?' : (r.gridRows - 1)}\n` +
    `自动抓取变更%：${r.auto ? '已开启 ⚠️' : '已关闭'}\n` +
    `任务：${r.running ? (r.paused ? '⏸已暂停' : '▶️运行中') : '空闲'}` +
    (r.total ? `  第${r.pass}趟 ${r.done}/${r.total}  成功${r.added} 失败${r.failed}` : '') +
    (r.lastError ? `\n最后错误：${r.lastError}` : '')
  );
}

/* ---------- 初始化 ---------- */
chrome.storage.local.get(
  ['stockData', 'maxTags', 'ftDebug', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoWatchlist', 'ftAutoScrape', 'ftWlManualList'],
  (res) => {
    if (res.maxTags) $('maxTags').value = res.maxTags;
    $('dbgChk').checked = !!res.ftDebug;
    const legacy = res.ftAutoScrape === true;
    $('autoPos').checked = res.ftAutoPositions === undefined ? legacy : res.ftAutoPositions === true;
    $('autoOrd').checked = res.ftAutoOrders === undefined ? legacy : res.ftAutoOrders === true;
    $('autoWl').checked = res.ftAutoWatchlist === true;
    if (Array.isArray(res.ftWlManualList)) $('wlManual').value = res.ftWlManualList.join(', ');

    if (res.stockData) {
      const keys = Object.keys(res.stockData);
      setStatus(`已缓存 ${keys.length} 个标的\n示例：${keys.slice(0, 8).join(', ')}`);
    } else {
      setStatus('尚未导入数据，请选择 description.json');
    }
    refreshPageStatus();
    refreshWlStatus();
  });

setInterval(refreshWlStatus, 2500);

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
  const maxTags = Math.max(1, Math.min(20, parseInt($('maxTags').value, 10) || 2));
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

/* ---------- ① 标签 ---------- */
$('fileInput').addEventListener('change', (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  setStatus('读取中…');
  const reader = new FileReader();
  reader.onerror = () => setStatus('文件读取失败，请改用粘贴方式', true);
  reader.onload = (ev) => handleText(ev.target.result);
  reader.readAsText(file, 'utf-8');
});

$('pasteBtn').addEventListener('click', () => {
  const text = $('pasteArea').value.trim();
  if (!text) { setStatus('粘贴框是空的', true); return; }
  handleText(text);
});

$('maxTags').addEventListener('change', () => {
  const maxTags = Math.max(1, Math.min(20, parseInt($('maxTags').value, 10) || 2));
  chrome.storage.local.set({ maxTags }, () => {
    setStatus(`已设置为每行最多显示 ${maxTags} 个标签`);
    sendToTab({ action: 'refreshTags' });
  });
});

$('clearBtn').addEventListener('click', () => {
  chrome.storage.local.remove('stockData', () => {
    setStatus('已清空标签缓存');
    sendToTab({ action: 'refreshTags' });
  });
});

/* ---------- 开关 ---------- */
$('dbgChk').addEventListener('change', () => {
  chrome.storage.local.set({ ftDebug: $('dbgChk').checked }, () => {
    setBridge($('dbgChk').checked ? '调试日志已开启（看页面 Console）' : '调试日志已关闭');
  });
});

function bindAuto(id, key, label) {
  $(id).addEventListener('change', () => {
    const v = $(id).checked;
    chrome.storage.local.set({ [key]: v }, () => {
      setBridge(v ? `⚠️ ${label} 自动抓取已开启` : `✅ ${label} 自动抓取已关闭`);
      setTimeout(() => { refreshPageStatus(); refreshWlStatus(); }, 300);
    });
  });
}
bindAuto('autoPos', 'ftAutoPositions', '持仓');
bindAuto('autoOrd', 'ftAutoOrders', '订单');
bindAuto('autoWl', 'ftAutoWatchlist', '自选股');

/* ---------- ② 持仓 ---------- */
$('pingBtn').addEventListener('click', async () => {
  setBridge('正在连接 127.0.0.1:18888 …');
  const r = await sendToBg({ action: 'FT_PING' });
  if (r.ok) setBridge('✅ 桥接服务正常\n' + JSON.stringify(r.data, null, 1));
  else setBridge('❌ 连不上桥接服务：' + r.error + '\n请在终端运行 bridge_server.py', true);
});

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

/* ---------- ③ 订单 ---------- */
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

/* ---------- ④ 自选股批量补齐 ---------- */
$('wlDiffBtn').addEventListener('click', async () => {
  setWl('正在读取 Sectors_All + 抓取自选股全表（1800 行需 1~3 分钟）…');
  const r = await sendToTab({ action: 'FT_WL_DIFF' });
  if (!r || !r.ok) { setWl('比对失败：' + (r && r.error), true); return; }
  setWl(
    `分组：${r.group}\n来源：${r.srcFrom}（${r.srcCount} 只）\n` +
    `自选股已有：${r.haveCount} 只\n★ 待添加：${r.missing} 只\n` +
    (r.sample.length ? `示例：${r.sample.join(', ')}` : '')
  );
});

$('wlStartBtn').addEventListener('click', async () => {
  setWl('正在启动批量添加…（进度看网页右下角面板，可以关掉本窗口）');
  const r = await sendToTab({ action: 'FT_WL_START' });
  if (!r || !r.ok) { setWl('启动失败：' + (r && r.error), true); return; }
  setWl(`✅ 已启动：分组「${r.group || ''}」，待添加 ${r.total} 只\n来源：${r.srcFrom || ''}\n` +
    `请勿操作该标签页；可切到别的标签页。`);
});

$('wlPauseBtn').addEventListener('click', async () => {
  const r = await sendToTab({ action: 'FT_WL_PAUSE' });
  setWl(r && r.ok ? (r.paused ? '⏸ 已暂停' : '▶️ 已继续') : '操作失败');
  setTimeout(refreshWlStatus, 400);
});

$('wlStopBtn').addEventListener('click', async () => {
  await sendToTab({ action: 'FT_WL_STOP' });
  setWl('⏹ 已发送停止指令');
  setTimeout(refreshWlStatus, 800);
});

$('wlHudBtn').addEventListener('click', () => sendToTab({ action: 'FT_WL_HUD' }));

$('wlFailBtn').addEventListener('click', async () => {
  const r = await sendToTab({ action: 'FT_WL_FAILED' });
  if (!r || !r.ok) { setWl('读取失败清单失败', true); return; }
  const txt = (r.list || []).map(x => `${x.symbol}\t${x.error}`).join('\n');
  console.log('[FT-POPUP] 失败清单\n' + txt);
  try { await navigator.clipboard.writeText(txt || '(无失败项)'); } catch (e) { }
  setWl(`失败 ${r.list.length} 只，已复制到剪贴板（也可在 Console 查看）\n` +
    (r.list.slice(0, 8).map(x => `${x.symbol} - ${x.error}`).join('\n')));
});

$('wlManualSave').addEventListener('click', () => {
  const arr = $('wlManual').value.split(/[\s,;]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
  chrome.storage.local.set({ ftWlManualList: arr }, () => setWl(`备用清单已保存 ${arr.length} 只`));
});

/* ---------- ④-自检 ---------- */
$('wlProbeBtn').addEventListener('click', async () => {
  const sym = ($('wlTestSym').value || 'LIN').trim().toUpperCase();
  setWl('正在探测（会打开弹层并输入 ' + sym + '，不会真的添加）…');
  const r = await sendToTab({ action: 'FT_WL_PROBE', symbol: sym });
  if (!r || !r.ok) { setWl('探测失败：' + (r && r.error), true); return; }
  setWl(
    `添加按钮：${r.addBtn}\n可见弹层：${r.popover} 个\n` +
    `输入框：${r.input}\n联想项：${r.items} 个 ${r.exact ? '(含精确匹配✅)' : ''}\n` +
    `示例：${(r.itemSample || []).join(', ')}\n表行数：${r.rows}｜分组：${r.group}` +
    (r.error ? `\n错误：${r.error}` : ''), !!r.error);
  console.log('[FT-POPUP] probe', r);
});

$('wlTestBtn').addEventListener('click', async () => {
  const sym = ($('wlTestSym').value || '').trim().toUpperCase();
  if (!sym) { setWl('请先在下面的输入框填一个 symbol', true); return; }
  setWl('正在测试添加 ' + sym + ' …');
  const r = await sendToTab({ action: 'FT_WL_TEST_ADD', symbol: sym });
  if (!r || !r.ok) { setWl('测试失败：' + (r && r.error), true); return; }
  setWl('测试结果：' + JSON.stringify(r.result));
});

/* ---------- ⑤ 自选股行情 ---------- */
$('wlQuoteBtn').addEventListener('click', async () => {
  setBridge('正在全量抓取自选股「变更%」，1800 行需 1~3 分钟，请勿操作页面…');
  const r = await sendToTab({ action: 'FT_WL_SCAN_QUOTES' });
  if (!r || !r.ok) { setBridge('抓取失败：' + (r && r.error), true); return; }
  const d = (r.server && r.server.data) || {};
  setBridge(`✅ 抓到 ${r.count} 只\n本机写入：${d.saved ?? '?'} 条（模式 ${d.mode || '?'}，文件累计 ${d.total ?? '?'}）`);
  refreshWlStatus();
});

$('serverWlBtn').addEventListener('click', async () => {
  const r = await sendToBg({ action: 'FT_SERVER_WATCHLIST' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const q = (r.data && r.data.quotes) || {};
  const keys = Object.keys(q);
  const sample = keys.slice(0, 8).map(k => `${k} ${q[k].change_pct || ''} ${q[k].last || ''}`).join('\n');
  setBridge(`本机 watchlist JSON 共 ${keys.length} 只\n更新时间：${(r.data._meta || {}).updated_at_str || '?'}\n${sample}`);
  console.log('[FT-POPUP] 本机 watchlist', r.data);
});