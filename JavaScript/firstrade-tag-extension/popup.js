const $ = (id) => document.getElementById(id);
const statusEl = $('status');
const bridgeEl = $('bridgeStatus');
const pageEl = $('pageStatus');
const wlEl = $('wlStatus');
const wlMsgEl = $('wlMsg');

function mkSetter(el, okColor) {
  return (text, isError) => { el.style.color = isError ? '#b91c1c' : okColor; el.innerText = text; };
}
const setStatus = mkSetter(statusEl, '#059669');
const setBridge = mkSetter(bridgeEl, '#059669');
const setWl = mkSetter(wlMsgEl, '#065f46');
const setTop = mkSetter($('topMsg'), '#065f46');
const setTrade = mkSetter($('tradeMsg'), '#065f46');
function setWlStatus(text, isError) {
  wlEl.style.color = isError ? '#b91c1c' : '#334155';
  wlEl.innerText = text;
}
const AREA_SET = { wl: setWl, top: setTop, trade: setTrade, bridge: setBridge };

/* ---------- 通信 ---------- */
function sendToTab(msg) {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || !tabs[0] || !tabs[0].id) { resolve({ ok: false, error: '没有活动标签页' }); return; }
      chrome.tabs.sendMessage(tabs[0].id, msg, (resp) => {
        if (chrome.runtime.lastError) { resolve({ ok: false, error: chrome.runtime.lastError.message }); return; }
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
const runOn = (page, msg, extra) => sendToBg(Object.assign({ action: 'FT_RUN_ON_PAGE', page, msg }, extra || {}));
const peek = (page, msg) => sendToBg({ action: 'FT_PEEK_PAGE', page, msg });

const DEFAULT_GROUP = 'Earning';
const PAGE_NAME = { positions: '持仓页 ✅', orders: '订单页 ✅', watchlist: '自选股页 ✅', other: '其它页面（不会抓取）' };
const PAGE_LABEL = { positions: '持仓页', orders: '订单页', watchlist: '自选股页' };
const SRC_NAME = { earnings: '财报日历', sectors: 'Sectors_All', manual: '本地清单' };
const PHASE_NAME = { idle: '空闲', group: '🎯 切换分组', diff: '🧮 比对中', clear: '🗑 删除中', add: '➕ 添加中', verify: '🔍 复核中' };
const HOW_NAME = { existing: '已切到现有标签页', navigated: '已把 Firstrade 标签页跳转过去', created: '已新开标签页' };
const ST = { F: '已成交', C: '已取消', P: '待成交', X: '?' };

/* ==================== 结果格式化 ==================== */
function fmtPositions(r) {
  const srv = r.server && r.server.ok ? '已覆盖写入本机 JSON ✅' : ('写入本机失败：' + JSON.stringify(r.server || {}).slice(0, 200));
  return `✅ 共抓取 ${r.count} 只持仓\n${srv}`;
}
function fmtOrders(r) {
  const d = (r.server && r.server.data) || {};
  const srv = r.server && r.server.ok
    ? `已追加写入本机 ✅ 新增 ${d.added ?? '?'} / 更新 ${d.updated ?? '?'} / 累计 ${d.total ?? '?'}\n` +
    `顺手瘦身 ${d.shrunk ?? 0} 条，文件 ${((d.bytes || 0) / 1024).toFixed(1)}KB`
    : ('写入本机失败：' + JSON.stringify(r.server || {}).slice(0, 200));
  return `✅ 本页抓到 ${r.count} 笔订单\n${srv}`;
}
function fmtQuotes(r) {
  const d = (r.server && r.server.data) || {};
  return `✅ 分组「${r.group || '?'}」抓到 ${r.count} 只\n本机写入：${d.saved ?? '?'} 条（模式 ${d.mode || '?'}，文件累计 ${d.total ?? '?'}）`;
}
function fmtMember(r) {
  return '✅ ' + (r.message || '') + '\n' +
    (r.results || []).map(x => `${x.group}: ${x.ok ? x.count + ' 只' : '❌ ' + (x.error || '')}`).join('\n');
}
function fmtStart(r) {
  return `✅ 已启动：目标分组「${r.targetGroup}」（当前「${r.group}」）\n` +
    `阶段0 切分组 → 阶段1 比对 → 阶段2 删多余${r.strictSync ? '' : '(已关闭)'} → 阶段3 补缺失 → 阶段4 复核\n` +
    `进度看网页右下角面板；任务期间尽量让该标签页保持在前台。`;
}
function fmtClearOnly(r) { return `🧹 已启动只清空：目标分组「${r.targetGroup}」`; }
function fmtClearGroups(r) {
  if (!r.started) return 'ℹ️ ' + (r.message || '没有需要清空的分组');
  return `🧹 已启动：依次清空 ${r.groups.join(' / ')}\n保留：${r.keep.join(' / ')}\n` +
    `每组删前自动备份（「复制删除前备份」可取回）；进度看网页右下角面板，可随时停止。`;
}
function fmtDiff(r) {
  return `分组：${r.group}${r.onTarget ? ' ✅' : ` (目标「${r.targetGroup}」)`}\n` +
    `来源：${r.srcFrom}（${r.srcCount} 只）\n自选股已有：${r.haveCount} 只\n` +
    `★ 待添加：${r.missing} 只｜★ 多余(严格同步会删)：${r.extraCount} 只\n` +
    (r.srcCount === 0 ? '⚠ 数据源目标日期无数据（不回退）\n' : '') +
    (r.sample && r.sample.length ? `待加示例：${r.sample.join(', ')}\n` : '') +
    (r.extraSample && r.extraSample.length ? `多余示例：${r.extraSample.join(', ')}` : '');
}
function fmtGroups(r) {
  const sw = r.switched;
  return `页面可选分组：${(r.options || []).join(' / ') || '(未读到)'}\n` +
    `当前分组：${r.current}｜表内 ${r.dataRows} 只\n` +
    (sw ? (sw.ok ? '✅ 已切换/已在目标分组' : `❌ 切换失败：${sw.error}`) : '');
}
function fmtProbe(r) {
  return `添加按钮：${r.addBtn}\n可见弹层：${r.popover} 个\n` +
    `输入框：${r.input}\n联想项：${r.items} 个 ${r.exact ? '(含精确匹配✅)' : ''}\n` +
    `示例：${(r.itemSample || []).join(', ')}\n表内标的：${r.dataRows}｜分组：${r.group}\n` +
    `最顶可删行：${r.topRow}` + (r.error ? `\n错误：${r.error}` : '');
}
function fmtProbeDel(r) {
  return `目标行：${r.symbol}（rowId=${r.rowId}）\n弹出菜单：${r.menus} 个\n` +
    `菜单项：${(r.menuItems || []).join(' / ')}\n` +
    `找到「删除」：${r.removeFound ? '是 ✅ (' + r.removeId + ')' : '否 ❌'}`;
}
function fmtTradeProbe(r) {
  return `「交易」按钮：${r.tradeBtn ? '找到 ✅' : '未找到 ❌'}\n面板：${r.panel}\n` +
    `标签页：${(r.tabs || []).join(' / ') || '-'}\n代码输入框：${r.symbolInput ? '✅' : '❌'}\n` +
    `交易类型：${r.transaction || '-'}\n数量方式：${r.qtyMode || '-'}\n订单类型：${r.orderType || '-'}\n` +
    `下单按钮：${r.submit || '-'}\n底部按钮：${(r.footerButtons || []).join(' / ') || '-'}\n` +
    `通知区域：${r.notifications ? '✅' : '❌'}`;
}
const stepLines = (steps) => (steps || []).map(s => `${s.ok ? '✅' : '❌'} ${s.label}：${s.msg || ''}`).join('\n');

const OPS = {
  positions: { label: '抓取全部持仓', page: 'positions', area: 'bridge', fmt: fmtPositions },
  orders: { label: '抓取订单记录', page: 'orders', area: 'bridge', fmt: fmtOrders },
  wl_quotes: { label: '抓取 Earning 变更%', page: 'watchlist', area: 'bridge', fmt: fmtQuotes },
  wl_member: { label: '扫描全部分组归属', page: 'watchlist', area: 'wl', fmt: fmtMember },
  wl_start: { label: '一键同步', page: 'watchlist', area: 'wl', fmt: fmtStart },
  wl_clear_only: { label: '只清空目标分组', page: 'watchlist', area: 'wl', fmt: fmtClearOnly },
  wl_clear_groups: { label: '清空非保留分组', page: 'watchlist', area: 'wl', fmt: fmtClearGroups },
  wl_diff: { label: '比对差集', page: 'watchlist', area: 'wl', fmt: fmtDiff },
  wl_groups: { label: '检测/切换分组', page: 'watchlist', area: 'wl', fmt: fmtGroups },
  wl_probe: { label: '探测添加弹层', page: 'watchlist', area: 'wl', fmt: fmtProbe },
  wl_probe_del: { label: '探测删除菜单', page: 'watchlist', area: 'wl', fmt: fmtProbeDel },
  wl_test_add: { label: '试添加', page: 'watchlist', area: 'wl', fmt: r => '测试结果：' + JSON.stringify(r.result) },
  wl_test_del: { label: '试删除', page: 'watchlist', area: 'wl', fmt: r => '测试删除结果：' + JSON.stringify(r.result) },
  wl_hud: { label: '显示进度面板', page: 'watchlist', area: 'wl', fmt: () => '👁 已显示网页右下角进度面板' },
  trade_probe: { label: '探测交易面板', page: 'watchlist', area: 'trade', fmt: fmtTradeProbe },
  combo_collect: { label: '一键抓取（持仓 + 订单 + 分组归属）', area: 'top', combo: true },
  combo_sync: { label: '一键同步 Earning + 抓取变更%', area: 'top', combo: true }
};

function showOp(op) {
  const K = OPS[op && op.kind];
  if (!K) return;
  const set = AREA_SET[K.area] || setBridge;
  if (op.state === 'running') {
    if (K.combo) {
      const prev = stepLines(op.steps);
      set(`⏳ ${op.progress || K.label + ' 启动中…'}\n${prev ? prev + '\n' : ''}` +
        `（会自动切换/跳转标签页，本窗口关闭不影响执行；再次打开可看进度）`);
      return;
    }
    set(`⏳ ${K.label} 进行中…（自动定位${PAGE_LABEL[K.page]}；切换标签页时本窗口会自动关闭，` +
      `不影响执行，完成后网页右下角提示，再次打开本窗口可看结果）`);
    return;
  }
  if (K.combo) {
    set(`${op.ok ? '✅' : '⚠️'} ${K.label}${op.ok ? '：全部完成' : '：' + (op.error || '部分步骤失败')}\n` +
      stepLines(op.resp && op.resp.steps), !op.ok);
    return;
  }
  const how = op.how ? `〔${HOW_NAME[op.how] || op.how}〕\n` : '';
  if (!op.ok) {
    set(`${how}❌ ${K.label}失败：${op.error || (op.resp && (op.resp.error || op.resp.message)) || '未知错误'}`, true);
    return;
  }
  set(how + K.fmt(op.resp || {}), false);
}

async function runOp(kind, msg, extra) {
  const K = OPS[kind];
  showOp({ kind, state: 'running' });
  const r = await runOn(K.page, msg, Object.assign({ kind, label: K.label, restore: true }, extra || {}));
  const op = { kind, state: 'done', ok: !!(r && r.ok), error: r && r.error, resp: r && r.resp, how: r && r.how };
  showOp(op);
  setTimeout(() => { refreshPageStatus(); refreshWlStatus(); }, 500);
  return op;
}

async function runCombo(kind, opts) {
  showOp({ kind, state: 'running' });
  const r = await sendToBg({ action: 'FT_COMBO', combo: kind, opts: opts || {} });
  showOp({ kind, state: 'done', ok: !!(r && r.ok), error: r && r.error, resp: r && r.resp });
  setTimeout(() => { refreshPageStatus(); refreshWlStatus(); }, 500);
}

chrome.storage.onChanged.addListener((c, area) => {
  if (area === 'local' && c.ftLastOp && c.ftLastOp.newValue) showOp(c.ftLastOp.newValue);
});

/* ==================== 状态刷新 ==================== */
async function refreshPageStatus() {
  const r = await sendToTab({ action: 'FT_STATUS' });
  if (!r.ok) {
    pageEl.innerText = '当前标签页不是 Firstrade 页面（或脚本未注入）。\n' +
      '无需手动切换：点任一抓取/同步按钮会自动定位、跳转或新开对应页面。';
    return;
  }
  pageEl.innerText =
    `当前：${PAGE_NAME[r.page] || r.page}   ${r.path}\n` +
    `自动：持仓 ${r.autoPositions ? '开⚠️' : '关'} ｜ 订单 ${r.autoOrders ? '开⚠️' : '关'}\n` +
    `订单写入模式：${r.orderVerbose ? '完整字段 ⚠️体积大' : '精简 LEAN ✅'}\n` +
    `可抓持仓：${r.canPositions ? '是' : '否'} ｜ 可抓订单：${r.canOrders ? '是' : '否'}\n` +
    `本页缓存：持仓 ${r.positions} 条 / 订单 ${r.orders} 笔`;
}

async function refreshWlStatus() {
  const r = await peek('watchlist', { action: 'FT_WL_STATUS' });
  if (!r || !r.ok) {
    if (r && r.noTab) setWlStatus('尚未打开自选股页面（点任一自选股功能会自动打开并执行）');
    else setWlStatus('自选股页面脚本未响应（可能正在加载，必要时刷新该页）：' + ((r && r.error) || ''), true);
    return;
  }
  const rowsCount = (r.dataRows === null || r.dataRows === undefined) ? '0' : r.dataRows;
  let txt =
    `当前分组：${r.group || '(未识别)'} ${r.onTarget ? '✅在目标分组' : `→ 将自动切到「${r.targetGroup}」`}\n` +
    `表内标的：${rowsCount}｜严格同步：${r.strictSync ? '开（删多余）' : '关（只补齐）'}\n` +
    `数据源：${SRC_NAME[r.src] || r.src}（回溯 ${r.srcBack} 交易日 / 前瞻 ${r.srcAhead} 天，不回退）\n` +
    `自动抓取变更%：${r.auto ? '已开启 ⚠️' : '已关闭'}\n` +
    `任务：${r.running ? (r.paused ? '⏸ 已暂停' : '▶️ 运行中') : (r.finishing ? '收尾中' : '空闲')}｜阶段：${PHASE_NAME[r.phase] || r.phase || '空闲'}` +
    (r.multi && r.multi.length ? `\n清空分组：${r.multi.join(' / ')}` : '');
  if (r.running) {
    txt += `\n待删 ${r.toRemove}｜待加 ${r.toAdd}`;
    if (r.phase === 'clear') txt += `\n删除进度：${r.cleared}/${r.clearTotal}（失败 ${r.clearFailed}）`;
    if (r.phase === 'add') txt += `\n添加进度：第 ${r.pass} 趟 ${r.done}/${r.total}  成功 ${r.added} 失败 ${r.failed}`;
  }
  if (!r.running && (r.cleared || r.added)) {
    txt += `\n上次结果：删除 ${r.cleared}｜新增 ${r.added}｜失败 ${r.failed + r.clearFailed}`;
  }
  txt += `\n行情抓取：${r.scanning ? '进行中' : '空闲'}`;
  if (r.lastError) txt += `\n最后错误：${r.lastError}`;
  setWlStatus(txt);
}

async function refreshAgentStatus() {
  const r = await peek('watchlist', { action: 'FT_AGENT_STATUS' });
  const el = $('agentBox');
  if (!r || !r.ok) {
    el.textContent = r && r.noTab ? '🤖 远程代理：自选股页未打开（Python 端提交任务时会自动唤起）'
      : '🤖 远程代理：未注入（请刷新 /app/watchlist 页面）';
    return;
  }
  el.textContent = `🤖 远程代理：${r.enabled ? '已开启' : '已关闭'}` +
    `｜当前分组 ${r.group || '?'}｜${r.busy ? '正在执行任务…' : '待命'}` +
    `｜链路 ${r.apiReady ? 'OK' : '未就绪'}`;
}

/* ---------- 初始化 ---------- */
chrome.storage.local.get(
  ['stockData', 'maxTags', 'ftDebug', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoWatchlist',
    'ftAutoScrape', 'ftWlManualList', 'ftOrderVerbose', 'ftWlSource', 'ftWlBack', 'ftWlAhead',
    'ftWlClearFirst', 'ftWlAgent', 'ftWlRestoreGroup', 'ftWlTargetGroup', 'ftWlStrictSync',
    'ftWlMemberPassive', 'ftLastOp', 'ftWlKeepExtra', 'ftTradeMode',
    'ftTradeEnabled', 'ftTradeDryRun', 'ftTradeRemoveAfter', 'ftTradePresets'],
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
    $('wlStrict').checked = res.ftWlStrictSync !== false;
    let tg = (res.ftWlTargetGroup && String(res.ftWlTargetGroup).trim()) || DEFAULT_GROUP;
    if (tg.toUpperCase() === 'ALL') { tg = DEFAULT_GROUP; chrome.storage.local.set({ ftWlTargetGroup: tg }); }
    $('wlTarget').value = tg;
    $('wlSrc').value = res.ftWlSource || 'earnings';
    $('wlBack').value = (res.ftWlBack === undefined ? 1 : res.ftWlBack);
    $('wlAhead').value = (res.ftWlAhead === undefined ? 0 : res.ftWlAhead);
    $('wlClearFirst').checked = res.ftWlClearFirst === true;
    $('wlMemberPassive').checked = res.ftWlMemberPassive !== false;
    $('wlKeepExtra').value = res.ftWlKeepExtra || '';
    $('tradeEnabled').checked = res.ftTradeEnabled !== false;
    $('tradeMode').value = ['dry', 'confirm', 'live'].includes(res.ftTradeMode) ? res.ftTradeMode : 'dry';
    $('tradeRemove').checked = res.ftTradeRemoveAfter !== false;
    $('tradePresets').value = (Array.isArray(res.ftTradePresets) && res.ftTradePresets.length
      ? res.ftTradePresets : [1000, 2000, 3000]).join(',');
    if (Array.isArray(res.ftWlManualList)) $('wlManual').value = res.ftWlManualList.join(', ');
    if (res.stockData) {
      const keys = Object.keys(res.stockData);
      setStatus(`已缓存 ${keys.length} 个标的\n示例：${keys.slice(0, 8).join(', ')}`);
    } else {
      setStatus('尚未导入数据，请选择 description.json');
    }
    const op = res.ftLastOp;
    if (op && op.ts && Date.now() - op.ts < 30 * 60 * 1000) showOp(op);
    refreshPageStatus();
    refreshWlStatus();
    refreshAgentStatus();
  });

setInterval(refreshWlStatus, 2500);
setInterval(refreshAgentStatus, 3000);

/* ---------- ⚡ 一键组合 ---------- */
$('comboCollectBtn').addEventListener('click', () => runCombo('combo_collect'));
$('comboSyncBtn').addEventListener('click', () =>
  runCombo('combo_sync', { strictSync: $('wlStrict').checked, targetGroup: targetGroupVal() }));

/* ---------- JSON 处理 ---------- */
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

/* ---------- 开关绑定 ---------- */
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

/* ---------- 持仓 ---------- */
$('pingBtn').addEventListener('click', async () => {
  setBridge('正在连接 127.0.0.1:18888 …');
  const r = await sendToBg({ action: 'FT_PING' });
  if (r.ok) {
    const d = r.data || {};
    setBridge('✅ 桥接服务正常\n' +
      `订单文件 ${((d.orders_bytes || 0) / 1024).toFixed(1)}KB（默认 ${d.orders_schema_default || '?'}）\n` +
      `财报日历 ${d.earnings_release_exists ? '存在 ✅' : '缺失 ❌'}: ${d.earnings_release || '?'}\n` +
      `行情文件：${d.watchlist_file || '?'}\n` +
      `待执行远程任务：${d.wl_tasks_pending ?? 0}｜代理上次轮询：${d.agent_last_poll_ago ?? '—'}s 前`);
  } else setBridge('❌ 连不上桥接服务：' + r.error + '\n请在终端运行 bridge_server.py', true);
});

$('scanBtn').addEventListener('click', () => runOp('positions', { action: 'FT_SYNC_ALL' }));

$('dumpBtn').addEventListener('click', async () => {
  const r = await peek('positions', { action: 'FT_DUMP' });
  if (!r.ok) { setBridge('读取失败：' + r.error + '（本页缓存需先执行一次抓取）', true); return; }
  const keys = Object.keys(r.data || {});
  const sample = keys.slice(0, 3).map(k => {
    const p = r.data[k];
    return `${k}: 成本=${p.cost} 今日=${p.day_change} 盈亏=${p.gainloss}`;
  }).join('\n');
  setBridge(`持仓页已抓取 ${r.count} 只：\n${sample || '(空，请先点手动抓取)'}\n…${keys.slice(0, 20).join(',')}`);
});

$('serverBtn').addEventListener('click', async () => {
  const r = await sendToBg({ action: 'FT_SERVER_POSITIONS' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const d = r.data || {};
  const keys = Object.keys(d).filter(k => !k.startsWith('_'));
  setBridge(`本机 positions JSON 共 ${keys.length} 条\n${keys.slice(0, 25).join(', ')}`);
});

/* ---------- 订单 ---------- */
$('scanOrdersBtn').addEventListener('click', () => runOp('orders', { action: 'FT_SCAN_ORDERS' }));

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
  const r = await peek('orders', { action: 'FT_DUMP_ORDERS' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const keys = Object.keys(r.data || {});
  const sample = keys.slice(0, 5).map(k => {
    const o = r.data[k];
    return `${o.date} ${o.symbol} ${o.side === 'buy' ? '买' : '卖'} $${o.amount ?? '?'} ${ST[o.st] || ''}`;
  }).join('\n');
  setBridge(`订单页已抓取 ${r.count} 笔订单：\n${sample || '(空，请先点手动抓取)'}`);
});

$('serverOrdersBtn').addEventListener('click', async () => {
  const r = await sendToBg({ action: 'FT_SERVER_ORDERS' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const d = (r.data && r.data.orders) || {};
  const meta = (r.data && r.data._meta) || {};
  const keys = Object.keys(d);
  const sample = keys.slice(-6).map(k => {
    const o = d[k];
    return `${o.date} ${o.symbol} ${o.side === 'buy' ? '买' : '卖'} $${o.amount ?? '?'} ${ST[o.st] || o.status || ''}`;
  }).join('\n');
  setBridge(`本机 orders JSON 共 ${keys.length} 笔（schema=${meta.schema || '?'}）：\n${sample}`);
});

/* ---------- 自选股 ---------- */
function wlSrcCfg() {
  return {
    src: $('wlSrc').value,
    back: Math.max(0, parseInt($('wlBack').value, 10) || 0),
    ahead: Math.max(0, parseInt($('wlAhead').value, 10) || 0)
  };
}
function targetGroupVal() {
  let g = ($('wlTarget').value || DEFAULT_GROUP).trim() || DEFAULT_GROUP;
  if (g.toUpperCase() === 'ALL') g = DEFAULT_GROUP;
  return g;
}
function saveTargetCfg() {
  const g = targetGroupVal();
  $('wlTarget').value = g;
  chrome.storage.local.set({ ftWlTargetGroup: g }, () => {
    setWl(`目标分组已设为「${g}」：同步 / 行情抓取都会自动切过去，结束后按开关切回原分组`);
    setTimeout(refreshWlStatus, 500);
  });
}
$('wlTarget').addEventListener('change', saveTargetCfg);
$('wlTarget').addEventListener('blur', saveTargetCfg);

$('wlStrict').addEventListener('change', () => {
  const v = $('wlStrict').checked;
  chrome.storage.local.set({ ftWlStrictSync: v }, () => {
    disarm();
    setWl(v ? '✅ 严格同步已开：分组内「不在数据源里」的标的会被删除（删前自动备份）'
      : 'ℹ️ 严格同步已关：只补齐缺失，不删任何东西');
  });
});

$('wlGroupsBtn').addEventListener('click', () =>
  runOp('wl_groups', { action: 'FT_WL_GROUPS_PROBE', switchTo: targetGroupVal() }, { restore: false }));

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
    setWl(v ? '⚠️ 已勾选「全清重建」：目标分组会先全部删除，再按数据源重建。' : '✅ 已取消「全清重建」：只做差集对账');
  });
});

$('wlSrcPreviewBtn').addEventListener('click', async () => {
  const c = wlSrcCfg();
  const strict = $('wlStrict').checked;
  const tg = targetGroupVal();
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
  if (!d.count) {
    txt += `⚠ 目标日期（今天 ${d.today}，回溯 ${d.back} 交易日 / 前瞻 ${d.ahead} 天）没有财报数据，按「无数据」处理（不回退）。\n` +
      (strict ? `→ 一键同步会把目标分组「${tg}」里的标的全部删除（删前自动备份，网页有 5 秒倒计时可取消）`
        : '→ 严格同步已关：一键同步不会做任何改动');
  } else if (d.dates) {
    Object.keys(d.dates).forEach(k => { txt += `  ${k}: ${d.dates[k].join(', ')}\n`; });
  } else {
    txt += (d.symbols || []).slice(0, 30).join(', ');
  }
  setWl(txt, !d.count && strict);
});

/* ---- 危险操作二次确认 ---- */
let armedBtn = null, armedAt = 0, armedText = '', armTimer = null;
function disarm() {
  if (armedBtn) { armedBtn.textContent = armedText; armedBtn.classList.remove('armed'); }
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

/* ---- 一键同步 ---- */
$('wlRunBtn').addEventListener('click', async () => {
  const btn = $('wlRunBtn');
  const clearFirst = $('wlClearFirst').checked;
  const strictSync = $('wlStrict').checked;
  const targetGroup = targetGroupVal();
  if (clearFirst) {
    const st = await peek('watchlist', { action: 'FT_WL_STATUS' });
    const rows = (st && st.ok && st.dataRows) ? st.dataRows : 0;
    if (needConfirm(btn, `⚠️ 再点一次：确认全清「${targetGroup}」后重建`)) {
      setWl(`⚠️ 全清重建：会把目标分组「${targetGroup}」内全部标的删掉再按数据源重建` +
        (rows ? `（当前分组显示 ${rows} 只）` : '') + `\n8 秒内再点一次确认。`);
      return;
    }
  }
  disarm();
  await runOp('wl_start', { action: 'FT_WL_START', clearFirst, strictSync, targetGroup }, { restore: false });
});

$('wlPauseBtn').addEventListener('click', async () => {
  const r = await peek('watchlist', { action: 'FT_WL_PAUSE' });
  setWl(r && r.ok ? (r.paused ? '⏸ 已暂停' : '▶️ 已继续') : ('操作失败：' + ((r && r.error) || '')), !(r && r.ok));
  setTimeout(refreshWlStatus, 400);
});
$('wlStopBtn').addEventListener('click', async () => {
  disarm();
  const r = await peek('watchlist', { action: 'FT_WL_STOP' });
  setWl(r && r.ok ? '⏹ 已发送停止指令' : ('停止失败：' + ((r && r.error) || '')), !(r && r.ok));
  setTimeout(refreshWlStatus, 800);
});
$('wlHudBtn').addEventListener('click', () => runOp('wl_hud', { action: 'FT_WL_HUD' }, { restore: false }));
$('wlFailBtn').addEventListener('click', async () => {
  const r = await peek('watchlist', { action: 'FT_WL_FAILED' });
  if (!r || !r.ok) { setWl('读取失败清单失败：' + ((r && r.error) || ''), true); return; }
  const add = (r.list || []).map(x => `ADD\t${x.symbol}\t${x.error}`);
  const del = (r.clearList || []).map(x => `DEL\t${x.symbol}\t${x.error}`);
  const all = add.concat(del);
  try { await navigator.clipboard.writeText(all.join('\n') || '(无失败项)'); } catch (e) { }
  setWl(`添加失败 ${add.length} 只 / 删除失败 ${del.length} 只，已复制到剪贴板\n` + all.slice(0, 8).join('\n'));
});

/* ---- ★ 清空非保留分组 ---- */
const keepExtraList = () => ($('wlKeepExtra').value || '').split(/[,，;；\s]+/).map(s => s.trim()).filter(Boolean);
$('wlKeepExtra').addEventListener('change', () => {
  chrome.storage.local.set({ ftWlKeepExtra: $('wlKeepExtra').value.trim() }, () =>
    setWl(`额外保留分组：${keepExtraList().join(' / ') || '(无)'}`));
});
$('wlClearGroupsBtn').addEventListener('click', async () => {
  const btn = $('wlClearGroupsBtn');
  const keep = Array.from(new Set(['Earning', 'Wrong'].concat(keepExtraList())));
  if (needConfirm(btn, `⚠️ 再点一次：清空除 ${keep.join(' / ')} 外的全部分组`)) {
    setWl(`⚠️ 将依次切换到每个分组并删除其中所有标的（保留：${keep.join(' / ')}）。\n` +
      `每组删前自动备份；网页上有 5 秒倒计时可停止。8 秒内再点一次确认。`);
    return;
  }
  disarm();
  await runOp('wl_clear_groups', { action: 'FT_WL_CLEAR_GROUPS', keep }, { restore: false });
});

/* ---- 高级 / 排错 ---- */
$('wlDiffBtn').addEventListener('click', () => runOp('wl_diff', { action: 'FT_WL_DIFF' }));
$('wlClearOnlyBtn').addEventListener('click', async () => {
  const btn = $('wlClearOnlyBtn');
  const targetGroup = targetGroupVal();
  if (needConfirm(btn, `⚠️ 再点一次：清空分组「${targetGroup}」`)) {
    setWl(`⚠️ 只清空模式：会切到「${targetGroup}」并删除其中全部标的（不添加，删前自动备份）。\n8 秒内再点一次确认。`);
    return;
  }
  disarm();
  await runOp('wl_clear_only', { action: 'FT_WL_START', clearOnly: true, targetGroup }, { restore: false });
});
$('wlBackupBtn').addEventListener('click', async () => {
  chrome.storage.local.get(['ftWlClearBackup'], async (res) => {
    const b = res.ftWlClearBackup;
    if (!b || !Array.isArray(b.symbols) || !b.symbols.length) { setWl('还没有备份记录', true); return; }
    let txt = b.symbols.join(', ');
    if (b.groups && typeof b.groups === 'object') {
      txt = Object.keys(b.groups).map(g => `[${g}] ${(b.groups[g] || []).join(', ')}`).join('\n');
    }
    try { await navigator.clipboard.writeText(txt); } catch (e) { }
    setWl(`已复制备份清单：分组「${b.group}」共 ${b.count} 只\n` +
      `备份时间：${new Date(b.ts).toLocaleString()}\n${b.symbols.slice(0, 25).join(', ')} …`);
  });
});
$('wlProbeBtn').addEventListener('click', () => {
  const sym = ($('wlTestSym').value || 'LIN').trim().toUpperCase();
  runOp('wl_probe', { action: 'FT_WL_PROBE', symbol: sym });
});
$('wlProbeDelBtn').addEventListener('click', () => {
  const sym = ($('wlTestSym').value || '').trim().toUpperCase();
  runOp('wl_probe_del', { action: 'FT_WL_PROBE_DEL', symbol: sym });
});
$('wlTestBtn').addEventListener('click', () => {
  const sym = ($('wlTestSym').value || '').trim().toUpperCase();
  if (!sym) { setWl('请先在下面的输入框填一个 symbol', true); return; }
  runOp('wl_test_add', { action: 'FT_WL_TEST_ADD', symbol: sym });
});
$('wlTestDelBtn').addEventListener('click', () => {
  const btn = $('wlTestDelBtn');
  const sym = ($('wlTestSym').value || '').trim().toUpperCase();
  if (needConfirm(btn, sym ? `⚠️ 再点一次：真的删掉 ${sym}` : '⚠️ 再点一次：真的删掉最顶那一只')) {
    setWl('⚠️ 这会真实删除标的，用于验证删除链路。8 秒内再点一次确认。');
    return;
  }
  disarm();
  runOp('wl_test_del', { action: 'FT_WL_TEST_DEL', symbol: sym });
});
$('wlManualSave').addEventListener('click', () => {
  const arr = $('wlManual').value.split(/[\s,;]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
  chrome.storage.local.set({ ftWlManualList: arr }, () => setWl(`备用清单已保存 ${arr.length} 只`));
});

/* ---------- 行情抓取 ---------- */
$('wlQuoteBtn').addEventListener('click', () => runOp('wl_quotes', { action: 'FT_WL_SCAN_QUOTES' }));
$('serverWlBtn').addEventListener('click', async () => {
  const r = await sendToBg({ action: 'FT_SERVER_WATCHLIST' });
  if (!r.ok) { setBridge('读取失败：' + r.error, true); return; }
  const q = (r.data && r.data.quotes) || {};
  const meta = (r.data && r.data._meta) || {};
  const keys = Object.keys(q);
  const sample = keys.slice(0, 8).map(k => `${k} ${q[k].change_pct || ''} ${q[k].last || ''}`).join('\n');
  setBridge(`本机 watchlist_earning JSON 共 ${keys.length} 只（分组「${meta.group || '?'}」）\n` +
    `更新时间：${meta.updated_at_str || '?'}\n${sample}`);
});

/* ---------- 远程代理 ---------- */
$('wlAgent').addEventListener('change', () => {
  chrome.storage.local.set({ ftWlAgent: $('wlAgent').checked }, () => {
    setWl($('wlAgent').checked ? '✅ 已允许 Python 远程添加/删除/交易（自选股页每 2 秒领一次任务）'
      : '⛔ 已关闭远程任务，Python 端会等待超时');
    setTimeout(refreshAgentStatus, 300);
  });
});
$('wlRestore').addEventListener('change', () => {
  chrome.storage.local.set({ ftWlRestoreGroup: $('wlRestore').checked }, () => {
    setWl($('wlRestore').checked ? '任务完成后会自动切回原分组' : '任务完成后停留在目标分组');
  });
});

/* ---------- 分组归属 ---------- */
$('wlMemberPassive').addEventListener('change', () => {
  const v = $('wlMemberPassive').checked;
  chrome.storage.local.set({ ftWlMemberPassive: v }, () => {
    setWl(v ? '✅ 分组归属被动同步已开（小分组自动完整快照，大分组合并可见行）'
      : '⛔ 已关闭被动同步（仍会记录 F 键添加 / × 删除 / 批量任务 / 全量扫描）');
  });
});
$('wlMemberScanBtn').addEventListener('click', () => runOp('wl_member', { action: 'FT_MEMBER_SCAN' }));
$('wlMemberViewBtn').addEventListener('click', async () => {
  const r = await sendToBg({ action: 'FT_SERVER_MEMBERSHIP' });
  if (!r.ok) { setWl('读取失败：' + r.error, true); return; }
  const g = (r.data && r.data.groups) || {};
  const names = Object.keys(g);
  if (!names.length) { setWl('本机还没有分组归属数据：点「扫描全部分组归属」'); return; }
  const lines = names.map(n => {
    const x = g[n] || {};
    const t = x.updated_at ? new Date(x.updated_at * 1000).toLocaleString() : '?';
    return `${n}: ${x.count || 0} 只 ${x.complete ? '✅完整' : '⚠部分'}  ${t}`;
  });
  setWl(`本机分组归属（${names.length} 组）：\n` + lines.join('\n'));
});

/* ---------- ⑥ 快速交易 ---------- */
$('tradeEnabled').addEventListener('change', () => {
  const v = $('tradeEnabled').checked;
  chrome.storage.local.set({ ftTradeEnabled: v }, () =>
    setTrade(v ? '✅ 已启用：在自选股页 / 持仓页点击股票代码会弹出交易层（Alt+点击 = 原生行为）' : '⛔ 已关闭快速交易层'));
});
$('tradeMode').addEventListener('change', () => {
  const v = $('tradeMode').value;
  const txt = {
    dry: '🧪 预演：只自动填表，不点「下单」，也不会移出分组',
    confirm: '✋ 下单前暂停：表单填好后，交易层出现「确认下单」，点了才真正下单（120 秒不点自动取消）',
    live: '⚠️ 实盘：点金额档（按网页现价换算整数股）/ 一键全卖 会立即真实下单！'
  };
  chrome.storage.local.set({ ftTradeMode: v }, () => setTrade(txt[v], v === 'live'));
});
$('tradeRemove').addEventListener('change', () => {
  chrome.storage.local.set({ ftTradeRemoveAfter: $('tradeRemove').checked }, () =>
    setTrade($('tradeRemove').checked ? '成交后默认勾选「从所在分组移除」' : '成交后默认不移除（交易层里仍可手动勾选）'));
});
$('tradePresets').addEventListener('change', () => {
  const arr = $('tradePresets').value.split(/[,，\s]+/).map(s => parseFloat(s)).filter(n => Number.isFinite(n) && n > 0).slice(0, 6);
  const v = arr.length ? arr : [1000, 2000, 3000];
  $('tradePresets').value = v.join(',');
  chrome.storage.local.set({ ftTradePresets: v }, () => setTrade(`金额档已设为：${v.map(x => '$' + x).join(' / ')}`));
});
$('tradeProbeBtn').addEventListener('click', () => runOp('trade_probe', { action: 'FT_TRADE_PROBE' }, { restore: false }));