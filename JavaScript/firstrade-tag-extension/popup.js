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
const SRC_NAME = { earnings: '财报日历', sectors: 'Sectors_All', manual: '本地清单' };
const PHASE_NAME = { idle: '空闲', clear: '🧹 清空中', diff: '🧮 比对中', add: '➕ 添加中' };

async function refreshPageStatus() {
  const r = await sendToTab({ action: 'FT_STATUS' });
  if (!r.ok) { pageEl.innerText = '未检测到页面脚本：' + r.error; return; }
  pageEl.innerText =
    `当前：${PAGE_NAME[r.page] || r.page}   ${r.path}\n` +
    `自动：持仓 ${r.autoPositions ? '开⚠️' : '关'} ｜ 订单 ${r.autoOrders ? '开⚠️' : '关'}\n` +
    `订单写入模式：${r.orderVerbose ? '完整字段 ⚠️体积大' : '精简 LEAN ✅'}\n` +
    `可抓持仓：${r.canPositions ? '是' : '否'} ｜ 可抓订单：${r.canOrders ? '是' : '否'}\n` +
    `本页缓存：持仓 ${r.positions} 条 / 订单 ${r.orders} 笔`;
}

async function refreshWlStatus() {
  const r = await sendToTab({ action: 'FT_WL_STATUS' });
  if (!r || !r.ok) { setWl('未检测到自选股脚本（请在 /app/watchlist 页面刷新一次）', true); return; }
  if (!r.page) { setWl(`当前不在自选股页面（${r.path}）\n请先打开 https://invest.firstrade.com/app/watchlist`); return; }

  let txt =
    `分组：${r.group || '(未识别)'}｜表内标的：${(r.dataRows === null || r.dataRows === undefined) ? '?' : r.dataRows}\n` +
    `数据源：${SRC_NAME[r.src] || r.src}（回溯 ${r.srcBack} 交易日 / 前瞻 ${r.srcAhead} 天）\n` +
    `自动抓取变更%：${r.auto ? '已开启 ⚠️' : '已关闭'}\n` +
    `任务：${r.running ? (r.paused ? '⏸ 已暂停' : '▶️ 运行中') : '空闲'}｜阶段：${PHASE_NAME[r.phase] || r.phase}`;

  if (r.running && r.phase === 'clear') {
    txt += `\n清空进度：${r.cleared}/${r.clearTotal}（失败 ${r.clearFailed}）`;
  }
  if (r.running && r.phase === 'add') {
    txt += `\n添加进度：第 ${r.pass} 趟 ${r.done}/${r.total}  成功 ${r.added} 失败 ${r.failed}`;
  }
  if (!r.running && (r.cleared || r.added)) {
    txt += `\n上次结果：删除 ${r.cleared}｜新增 ${r.added}｜失败 ${r.failed + r.clearFailed}`;
  }
  txt += `\n行情抓取：${r.scanning ? '进行中' : '空闲'}`;
  if (r.lastError) txt += `\n最后错误：${r.lastError}`;
  setWl(txt);
}

/* ---------- 初始化 ---------- */
chrome.storage.local.get(
  ['stockData', 'maxTags', 'ftDebug', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoWatchlist',
    'ftAutoScrape', 'ftWlManualList', 'ftOrderVerbose', 'ftWlSource', 'ftWlBack', 'ftWlAhead',
    'ftWlClearFirst', 'ftWlAgent', 'ftWlRestoreGroup'],
  (res) => {
    if (res.maxTags) $('maxTags').value = res.maxTags;
    $('dbgChk').checked = !!res.ftDebug;
    const legacy = res.ftAutoScrape === true;
    $('autoPos').checked = res.ftAutoPositions === undefined ? legacy : res.ftAutoPositions === true;
    $('autoOrd').checked = res.ftAutoOrders === undefined ? legacy : res.ftAutoOrders === true;
    $('autoWl').checked = res.ftAutoWatchlist === true;
    $('ordVerbose').checked = res.ftOrderVerbose === true;
    $('wlAgent').checked = res.ftWlAgent !== false;
    $('wlRestore').checked = res.ftWlRestoreGroup !== false;
    $('wlSrc').value = res.ftWlSource || 'earnings';
    $('wlBack').value = (res.ftWlBack === undefined ? 1 : res.ftWlBack);
    $('wlAhead').value = (res.ftWlAhead === undefined ? 0 : res.ftWlAhead);
    $('wlClearFirst').checked = res.ftWlClearFirst === true;
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

$('ordVerbose').addEventListener('change', () => {
  const v = $('ordVerbose').checked;
  chrome.storage.local.set({ ftOrderVerbose: v }, () => {
    setBridge(v ? '⚠️ 订单将保存完整字段（体积大 ~10 倍）' : '✅ 订单已切回精简写入(LEAN)');
    setTimeout(refreshPageStatus, 300);
  });
});

/* ---------- ② 持仓 ---------- */
$('pingBtn').addEventListener('click', async () => {
  setBridge('正在连接 127.0.0.1:18888 …');
  const r = await sendToBg({ action: 'FT_PING' });
  if (r.ok) {
    const d = r.data || {};
    setBridge('✅ 桥接服务正常\n' +
      `订单文件 ${(d.orders_bytes / 1024 || 0).toFixed(1)}KB（默认 ${d.orders_schema_default}）\n` +
      `财报日历 ${d.earnings_release_exists ? '存在 ✅' : '缺失 ❌'}: ${d.earnings_release}\n` +
      `Sectors 源启用：${d.sectors_source_enabled ? '是' : '否（已屏蔽）'}`);
  }
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
      ? `已追加写入本机 ✅ 新增 ${d.added ?? '?'} / 更新 ${d.updated ?? '?'} / 累计 ${d.total ?? '?'}\n` +
      `顺手瘦身 ${d.shrunk ?? 0} 条，文件 ${((d.bytes || 0) / 1024).toFixed(1)}KB`
      : ('写入本机失败：' + JSON.stringify(r.server));
    setBridge(`本页抓到 ${r.count} 笔订单\n${srv}`);
  } else setBridge('抓取失败：' + r.error, true);
  refreshPageStatus();
});

$('compactOrdersBtn').addEventListener('click', async () => {
  setBridge('正在压缩本机订单 JSON（首次会自动备份 .fat.bak）…');
  const r = await sendToBg({ action: 'FT_COMPACT_ORDERS', verbose: false });
  if (!r.ok) { setBridge('压缩失败：' + r.error, true); return; }
  const d = r.data || {};
  if (d.status === 'skip') { setBridge('订单文件为空，无需压缩'); return; }
  setBridge(`🗜 压缩完成：${(d.before / 1024).toFixed(1)}KB → ${(d.after / 1024).toFixed(1)}KB` +
    `（省 ${d.saved_pct}%）\n共 ${d.count} 笔，瘦身 ${d.shrunk} 笔，schema=${d.schema}`);
});

$('dumpOrdersBtn').addEventListener('click', async () => {
  const r = await sendToTab({ action: 'FT_DUMP_ORDERS' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const keys = Object.keys(r.data || {});
  const ST = { F: '已成交', C: '已取消', P: '待成交', X: '?' };
  const sample = keys.slice(0, 5).map(k => {
    const o = r.data[k];
    return `${o.date} ${o.symbol} ${o.side === 'buy' ? '买' : '卖'} $${o.amount ?? '?'} ${ST[o.st] || ''}`;
  }).join('\n');
  setBridge(`本页已抓取 ${r.count} 笔订单：\n${sample || '(空，请确认在 order-status 页面)'}`);
  console.log('[FT-POPUP] 订单', r.data);
});

$('serverOrdersBtn').addEventListener('click', async () => {
  const r = await sendToBg({ action: 'FT_SERVER_ORDERS' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const d = (r.data && r.data.orders) || {};
  const meta = (r.data && r.data._meta) || {};
  const keys = Object.keys(d);
  const ST = { F: '已成交', C: '已取消', P: '待成交', X: '?' };
  const sample = keys.slice(-6).map(k => {
    const o = d[k];
    return `${o.date} ${o.symbol} ${o.side === 'buy' ? '买' : '卖'} $${o.amount ?? '?'} ${ST[o.st] || o.status || ''}`;
  }).join('\n');
  setBridge(`本机 orders JSON 共 ${keys.length} 笔（schema=${meta.schema || '?'}）：\n${sample}`);
  console.log('[FT-POPUP] 本机 orders', r.data);
});

/* ---------- ④ 自选股一键重建 ---------- */
function wlSrcCfg() {
  return {
    src: $('wlSrc').value,
    back: Math.max(0, parseInt($('wlBack').value, 10) || 0),
    ahead: Math.max(0, parseInt($('wlAhead').value, 10) || 0)
  };
}

function saveWlSrcCfg() {
  const c = wlSrcCfg();
  chrome.storage.local.set({ ftWlSource: c.src, ftWlBack: c.back, ftWlAhead: c.ahead }, () => {
    setWl(`数据源已切换为「${SRC_NAME[c.src] || c.src}」（回溯 ${c.back} 交易日 / 前瞻 ${c.ahead} 天）`);
    setTimeout(refreshWlStatus, 600);
  });
}
$('wlSrc').addEventListener('change', saveWlSrcCfg);
$('wlBack').addEventListener('change', saveWlSrcCfg);
$('wlAhead').addEventListener('change', saveWlSrcCfg);

$('wlClearFirst').addEventListener('change', () => {
  const v = $('wlClearFirst').checked;
  chrome.storage.local.set({ ftWlClearFirst: v }, () => {
    disarm();
    setWl(v ? '⚠️ 已勾选「先清空当前分组」：执行时会先逐行删除现有全部标的（会先自动备份）'
      : '✅ 已取消「先清空」：只做差集补齐，不删任何东西');
  });
});

$('wlSrcPreviewBtn').addEventListener('click', async () => {
  const c = wlSrcCfg();
  if (c.src === 'manual') {
    chrome.storage.local.get(['ftWlManualList'], (res) => {
      const arr = res.ftWlManualList || [];
      setWl(`本地备用清单共 ${arr.length} 只\n${arr.slice(0, 30).join(', ')}`);
    });
    return;
  }
  setWl('正在读取数据源…');
  const r = await sendToBg({ action: 'FT_WL_SOURCE', src: c.src, back: c.back, ahead: c.ahead });
  if (!r.ok) { setWl('读取失败（bridge_server.py 是否运行？）：' + r.error, true); return; }
  const d = r.data || {};
  if (d.status === 'disabled') { setWl('⛔ ' + (d.message || '该数据源已停用'), true); return; }
  if (d.status === 'error') { setWl('❌ ' + (d.message || '数据源错误'), true); return; }
  let txt = `来源：${d.from || d.source}\n共 ${d.count} 只\n`;
  if (d.dates) {
    Object.keys(d.dates).forEach(k => { txt += `  ${k}: ${d.dates[k].join(', ')}\n`; });
  } else {
    txt += (d.symbols || []).slice(0, 30).join(', ');
  }
  if (d.fallback) txt += '\n⚠ 目标日期无数据，已回退到最近的财报日';
  if (d.file_exists === false) txt += `\n❌ 文件不存在：${d.file}`;
  setWl(txt);
  console.log('[FT-POPUP] wl_source', d);
});

/* ---- 危险操作二次确认（8 秒内再点一次） ---- */
let armedBtn = null, armedAt = 0, armedText = '', armTimer = null;

function disarm() {
  if (armedBtn) {
    armedBtn.textContent = armedText;
    armedBtn.classList.remove('armed');
  }
  armedBtn = null; armedAt = 0; armedText = '';
  clearTimeout(armTimer);
}

function armOnce(btn, label) {
  disarm();
  armedBtn = btn; armedAt = Date.now(); armedText = btn.textContent;
  btn.textContent = label;
  btn.classList.add('armed');
  armTimer = setTimeout(disarm, 8000);
}

function needConfirm(btn, label) {
  if (armedBtn === btn && Date.now() - armedAt < 8000) { disarm(); return false; }
  armOnce(btn, label);
  return true;
}

/* ---- ★ 一键执行 ---- */
$('wlRunBtn').addEventListener('click', async () => {
  const btn = $('wlRunBtn');
  const clearFirst = $('wlClearFirst').checked;

  if (clearFirst) {
    const st = await sendToTab({ action: 'FT_WL_STATUS' });
    const rows = (st && st.ok && st.dataRows !== null && st.dataRows !== undefined) ? st.dataRows : '?';
    if (needConfirm(btn, `⚠️ 再点一次：确认删掉 ${rows} 只后重建`)) {
      setWl(`⚠️ 即将清空分组「${(st && st.group) || '?'}」内 ${rows} 只标的，然后按数据源重新添加。\n` +
        `8 秒内再点一次按钮确认；点别处或等待即取消。`);
      return;
    }
  }
  disarm();

  setWl('正在启动…（进度看网页右下角面板，可以关掉本窗口）');
  const r = await sendToTab({ action: 'FT_WL_START', clearFirst });
  if (!r || !r.ok) { setWl('启动失败：' + (r && r.error), true); return; }
  setWl(`✅ 已启动：分组「${r.group || ''}」\n` +
    (r.clearFirst ? `阶段1 清空（表内约 ${r.rows} 只，已自动备份）→ ` : '') +
    `阶段2 比对差集 → 阶段3 批量添加\n请勿操作该标签页；可切到别的标签页。`);
  setTimeout(refreshWlStatus, 800);
});

$('wlPauseBtn').addEventListener('click', async () => {
  const r = await sendToTab({ action: 'FT_WL_PAUSE' });
  setWl(r && r.ok ? (r.paused ? '⏸ 已暂停' : '▶️ 已继续') : '操作失败');
  setTimeout(refreshWlStatus, 400);
});

$('wlStopBtn').addEventListener('click', async () => {
  disarm();
  await sendToTab({ action: 'FT_WL_STOP' });
  setWl('⏹ 已发送停止指令');
  setTimeout(refreshWlStatus, 800);
});

$('wlHudBtn').addEventListener('click', () => sendToTab({ action: 'FT_WL_HUD' }));

$('wlFailBtn').addEventListener('click', async () => {
  const r = await sendToTab({ action: 'FT_WL_FAILED' });
  if (!r || !r.ok) { setWl('读取失败清单失败', true); return; }
  const add = (r.list || []).map(x => `ADD\t${x.symbol}\t${x.error}`);
  const del = (r.clearList || []).map(x => `DEL\t${x.symbol}\t${x.error}`);
  const all = add.concat(del);
  const txt = all.join('\n');
  console.log('[FT-POPUP] 失败清单\n' + txt);
  try { await navigator.clipboard.writeText(txt || '(无失败项)'); } catch (e) { }
  setWl(`添加失败 ${add.length} 只 / 删除失败 ${del.length} 只，已复制到剪贴板\n` +
    all.slice(0, 8).join('\n'));
});

/* ---- 高级 / 排错 ---- */
$('wlDiffBtn').addEventListener('click', async () => {
  setWl('正在读取数据源 + 抓取自选股全表（1800 行需 1~3 分钟）…');
  const r = await sendToTab({ action: 'FT_WL_DIFF' });
  if (!r || !r.ok) { setWl('比对失败：' + (r && r.error), true); return; }
  setWl(
    `分组：${r.group}\n来源：${r.srcFrom}（${r.srcCount} 只）\n` +
    `自选股已有：${r.haveCount} 只\n★ 待添加：${r.missing} 只\n` +
    (r.sample && r.sample.length ? `示例：${r.sample.join(', ')}` : '（无需添加 ✅）')
  );
});

$('wlClearOnlyBtn').addEventListener('click', async () => {
  const btn = $('wlClearOnlyBtn');
  const st = await sendToTab({ action: 'FT_WL_STATUS' });
  const rows = (st && st.ok && st.dataRows !== null && st.dataRows !== undefined) ? st.dataRows : '?';
  if (needConfirm(btn, `⚠️ 再点一次：确认删除全部 ${rows} 只`)) {
    setWl(`⚠️ 只清空模式：将删除分组「${(st && st.group) || '?'}」内 ${rows} 只标的，不会自动添加。\n8 秒内再点一次确认。`);
    return;
  }
  disarm();
  const r = await sendToTab({ action: 'FT_WL_START', clearOnly: true });
  if (!r || !r.ok) { setWl('启动失败：' + (r && r.error), true); return; }
  setWl(`🧹 已启动只清空：分组「${r.group || ''}」，表内约 ${r.rows} 只（已自动备份）`);
});

$('wlBackupBtn').addEventListener('click', async () => {
  chrome.storage.local.get(['ftWlClearBackup'], async (res) => {
    const b = res.ftWlClearBackup;
    if (!b || !Array.isArray(b.symbols) || !b.symbols.length) { setWl('还没有备份记录', true); return; }
    const txt = b.symbols.join(', ');
    try { await navigator.clipboard.writeText(txt); } catch (e) { }
    setWl(`已复制备份清单：分组「${b.group}」共 ${b.count} 只\n` +
      `备份时间：${new Date(b.ts).toLocaleString()}\n${b.symbols.slice(0, 25).join(', ')} …`);
    console.log('[FT-POPUP] 清空前备份', b);
  });
});

$('wlProbeBtn').addEventListener('click', async () => {
  const sym = ($('wlTestSym').value || 'LIN').trim().toUpperCase();
  setWl('正在探测添加弹层（会输入 ' + sym + '，不会真的添加）…');
  const r = await sendToTab({ action: 'FT_WL_PROBE', symbol: sym });
  if (!r || !r.ok) { setWl('探测失败：' + (r && r.error), true); return; }
  setWl(
    `添加按钮：${r.addBtn}\n可见弹层：${r.popover} 个\n` +
    `输入框：${r.input}\n联想项：${r.items} 个 ${r.exact ? '(含精确匹配✅)' : ''}\n` +
    `示例：${(r.itemSample || []).join(', ')}\n表内标的：${r.dataRows}｜分组：${r.group}\n` +
    `最顶可删行：${r.topRow}` + (r.error ? `\n错误：${r.error}` : ''), !!r.error);
  console.log('[FT-POPUP] probe', r);
});

$('wlProbeDelBtn').addEventListener('click', async () => {
  setWl('正在探测删除菜单（只打开菜单，不会删除）…');
  const r = await sendToTab({ action: 'FT_WL_PROBE_DEL' });
  if (!r || !r.ok) { setWl('探测失败：' + (r && r.error), true); return; }
  setWl(`目标行：${r.symbol}（rowId=${r.rowId}）\n弹出菜单：${r.menus} 个\n` +
    `菜单项：${(r.menuItems || []).join(' / ')}\n` +
    `找到「删除」：${r.removeFound ? '是 ✅ (' + r.removeId + ')' : '否 ❌'}`, !r.removeFound);
  console.log('[FT-POPUP] probeDel', r);
});

$('wlTestBtn').addEventListener('click', async () => {
  const sym = ($('wlTestSym').value || '').trim().toUpperCase();
  if (!sym) { setWl('请先在下面的输入框填一个 symbol', true); return; }
  setWl('正在测试添加 ' + sym + ' …');
  const r = await sendToTab({ action: 'FT_WL_TEST_ADD', symbol: sym });
  if (!r || !r.ok) { setWl('测试失败：' + (r && r.error), true); return; }
  setWl('测试结果：' + JSON.stringify(r.result));
});

$('wlTestDelBtn').addEventListener('click', async () => {
  const btn = $('wlTestDelBtn');
  if (needConfirm(btn, '⚠️ 再点一次：真的删掉最顶那一只')) {
    setWl('⚠️ 这会真实删除表格最顶部的那一只标的，用于验证删除链路。8 秒内再点一次确认。');
    return;
  }
  disarm();
  setWl('正在测试删除最顶行…');
  const r = await sendToTab({ action: 'FT_WL_TEST_DEL' });
  if (!r || !r.ok) { setWl('测试失败：' + (r && r.error), true); return; }
  setWl('测试删除结果：' + JSON.stringify(r.result));
});

$('wlManualSave').addEventListener('click', () => {
  const arr = $('wlManual').value.split(/[\s,;]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
  chrome.storage.local.set({ ftWlManualList: arr }, () => setWl(`备用清单已保存 ${arr.length} 只`));
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

/* ---------- 🤖 远程添加代理 ---------- */
$('wlAgent').addEventListener('change', () => {
  chrome.storage.local.set({ ftWlAgent: $('wlAgent').checked }, () => {
    setWl($('wlAgent').checked
      ? '✅ 已允许 Python 远程添加（本页面每 2 秒领一次任务）'
      : '⛔ 已关闭远程添加，Python 端会等待超时');
    setTimeout(refreshAgentStatus, 300);
  });
});

$('wlRestore').addEventListener('change', () => {
  chrome.storage.local.set({ ftWlRestoreGroup: $('wlRestore').checked }, () => {
    setWl($('wlRestore').checked ? '添加完成后会自动切回原分组' : '添加完成后停留在目标分组');
  });
});

async function refreshAgentStatus() {
  const r = await sendToTab({ action: 'FT_AGENT_STATUS' });
  const el = $('agentBox');
  if (!r || !r.ok) { el.textContent = '🤖 远程添加代理：未注入（请在 /app/watchlist 刷新一次页面）'; return; }
  el.textContent = `🤖 远程添加代理：${r.enabled ? '已开启' : '已关闭'}` +
    `｜当前分组 ${r.group || '?'}｜${r.busy ? '正在执行任务…' : '待命'}` +
    `｜链路 ${r.apiReady ? 'OK' : '未就绪'}`;
}
setInterval(refreshAgentStatus, 3000);
refreshAgentStatus();