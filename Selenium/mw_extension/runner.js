'use strict';
const PROTOCOL = 1;
const qs = new URLSearchParams(location.search);
const PORT = qs.get('port') || '8765';
const TOKEN = qs.get('token') || '';
const AUTO = qs.get('auto') === '1';
const BASE = `http://127.0.0.1:${PORT}`;
const VERSION = chrome.runtime.getManifest().version;
const $ = (id) => document.getElementById(id);

let session = null, cfg = null, stopping = false, running = false;
let workerWinId = null, workerTabId = null;
const view = { running: false, done: false, port: PORT, status: '', current: '', summary: null };

// ---------------- 计时（Worker，不受后台节流影响） ----------------
const timer = new Worker(chrome.runtime.getURL('timer_worker.js'));
let timerSeq = 0;
const timerWaiters = new Map();
timer.onmessage = (e) => { const f = timerWaiters.get(e.data); if (f) { timerWaiters.delete(e.data); f(); } };
function sleep(ms) {
  return new Promise((resolve) => { const id = ++timerSeq; timerWaiters.set(id, resolve); timer.postMessage({ id, ms: Math.max(0, ms | 0) }); });
}
async function sleepStoppable(ms, label) {
  const end = Date.now() + ms;
  while (!stopping) {
    const left = end - Date.now();
    if (left <= 0) return true;
    if (label) setStatus(`${label}（剩余 ${Math.ceil(left / 1000)} 秒）`);
    await sleep(Math.min(1000, left));
  }
  return false;
}

// ---------------- UI ----------------
function publish() { chrome.storage.session.set({ mwRun: { ...view, ts: Date.now() } }).catch(() => { }); }
function setStatus(s) { view.status = s; $('status').textContent = s; publish(); }
function log(msg, level = 'info') {
  const div = document.createElement('div');
  div.className = 'line ' + level;
  div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  const box = $('log');
  box.prepend(div);
  while (box.childElementCount > 800) box.lastElementChild.remove();
  (level === 'err' ? console.error : console.log)(msg);
}
function renderSummary(s) {
  if (!s) return;
  view.summary = s;
  $('s-progress').textContent = `进度 ${s.done}/${s.total}`;
  $('s-ok').textContent = `成功 ${s.success}`;
  $('s-fail').textContent = `失败 ${s.failed}`;
  $('s-nf').textContent = `未找到 ${s.not_found}`;
  $('s-skip').textContent = `跳过 ${s.skipped}`;
  $('s-block').textContent = `封禁 ${s.hard_blocks}`;
  document.title = `MW ${s.done}/${s.total}`;
  publish();
}

// ---------------- 桥接通信 ----------------
class BridgeDown extends Error { }
async function api(path, body = {}, { timeoutMs = 20000, retries = 4 } = {}) {
  let lastErr;
  for (let i = 0; i <= retries; i++) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const resp = await fetch(BASE + path, {
        method: 'POST', cache: 'no-store', signal: ctrl.signal,
        headers: { 'Content-Type': 'application/json', 'X-MW-Token': TOKEN },
        body: JSON.stringify({ session, ...body }),
      });
      clearTimeout(t);
      if (resp.status === 401 || resp.status === 403) throw new BridgeDown(`桥接拒绝访问（HTTP ${resp.status}），令牌不匹配，可能是旧的控制台页`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      clearTimeout(t);
      if (e instanceof BridgeDown) throw e;
      lastErr = e;
      if (i < retries) await sleep(1500 * (i + 1));
    }
  }
  throw new BridgeDown(`无法连接本地桥接程序 ${BASE}（MW_Bridge.py 已退出？）：${(lastErr && lastErr.message) || lastErr}`);
}

// ---------------- 抓取窗口 ----------------
async function ensureWorkerTab() {
  if (workerTabId != null) {
    try { await chrome.tabs.get(workerTabId); return workerTabId; } catch (e) { workerTabId = null; }
  }
  const w = (cfg && cfg.window) || {};
  const win = await chrome.windows.create({
    url: 'about:blank', focused: false, type: 'normal',
    left: w.left ?? 0, top: w.top ?? 25, width: w.width ?? 1366, height: w.height ?? 900,
  });
  workerWinId = win.id;
  workerTabId = win.tabs[0].id;
  chrome.tabs.update(workerTabId, { autoDiscardable: false }).catch(() => { });
  log('🪟 已创建抓取窗口');
  return workerTabId;
}
async function focusWorker() {
  try {
    await chrome.windows.update(workerWinId, { focused: true, state: 'normal' });
    await chrome.tabs.update(workerTabId, { active: true });
  } catch (e) { }
}
async function blank() {
  if (workerTabId == null) return;
  try {
    const t = await chrome.tabs.get(workerTabId);
    if (t.url && t.url !== 'about:blank') await chrome.tabs.update(workerTabId, { url: 'about:blank' });
  } catch (e) { }
}
async function closeWorker() {
  if (cfg && cfg.keep_window) return;
  if (workerWinId != null) { try { await chrome.windows.remove(workerWinId); } catch (e) { } }
  workerWinId = workerTabId = null;
}
chrome.windows.onRemoved.addListener((id) => { if (id === workerWinId) { workerWinId = workerTabId = null; } });

async function markStale(tabId) {
  try { await chrome.scripting.executeScript({ target: { tabId }, func: () => { window.__mwStalePage = true; } }); } catch (e) { }
}
async function probe(tabId, args) {
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ['mw_parse.js'] });
    const res = await chrome.scripting.executeScript({
      target: { tabId }, args: [args],
      func: (a) => (self.__mwProbe ? self.__mwProbe(a) : { state: 'transient' }),
    });
    return (res && res[0] && res[0].result) || { state: 'transient' };
  } catch (e) {
    const m = String((e && e.message) || e);
    if (/No tab with id|tab was closed/i.test(m)) return { state: 'tab_closed' };
    return { state: 'transient', error: m };
  }
}

// ---------------- 单个任务：导航 + 等待 + 验证码处理 ----------------
async function runTask(task) {
  let tabId = await ensureWorkerTab();
  await markStale(tabId);
  try { await chrome.tabs.update(tabId, { url: task.url }); }
  catch (e) { workerTabId = null; tabId = await ensureWorkerTab(); await chrome.tabs.update(tabId, { url: task.url }); }

  const args = { mode: task.mode, expectSeg: task.expect_seg, expectType: task.expect_type, maxRows: task.max_rows };
  const t0 = Date.now();
  let deadline = t0 + task.wait_ms, lastPing = Date.now();
  let seenCaptcha = false, reported = false, manual = false, rounds = 0, solvedAt = null, refreshed = false;

  while (true) {
    if (stopping) return { state: 'stopped' };
    if (Date.now() - lastPing > 30000) {
      lastPing = Date.now();
      api('/api/ping', {}, { retries: 0, timeoutMs: 5000 }).catch(() => { });
    }
    const r = await probe(tabId, args);
    const st = r.state;

    if (st === 'tab_closed') { workerTabId = null; return { state: 'stale', error: '抓取窗口被关闭' }; }
    if (st === 'blocked') { await blank(); return { state: 'blocked', final_url: r.url }; }

    if (seenCaptcha && st !== 'captcha' && st !== 'transient' && st !== 'stale') {
      seenCaptcha = false;
      log('✅ 验证已通过，继续');
      api('/api/captcha', { phase: 'resolved' }, { retries: 0 }).catch(() => { });
      deadline = Math.max(deadline, Date.now() + task.wait_ms);
    }
    if (st === 'ready') return { state: 'ready', payload: r.payload, final_url: r.url, elapsed_ms: Date.now() - t0 };
    if (st === 'notfound' || st === 'mismatch' || st === 'wrong_symbol') {
      return { state: st, final_url: r.url, body_class: r.body_class };
    }

    if (st === 'captcha') {
      seenCaptcha = true;
      if (!reported) {
        reported = true;
        log(`🧩 [${task.symbol}] 出现滑块验证`, 'warn');
        await api('/api/captcha', { phase: 'detected' }, { retries: 1 }).catch(() => { });
      }
      if (solvedAt !== null) {
        const el = Date.now() - solvedAt;
        if (el >= 8000 && !refreshed) {
          refreshed = true;
          log('🔄 滑块已通过但页面未跳转，刷新一次');
          try { await chrome.tabs.reload(tabId); } catch (e) { }
        } else if (el >= 15000) {
          log('⚠️ 刷新后仍为验证页，可能出现了新一轮验证', 'warn');
          solvedAt = null;
        }
      } else if (cfg.slider && !manual && rounds < cfg.slider_rounds) {
        rounds++;
        log(`🧩 自动拖拽滑块（第 ${rounds}/${cfg.slider_rounds} 轮）...`);
        await focusWorker();
        let res = 'failed';
        try { res = (await api('/api/captcha', { phase: 'solve' }, { timeoutMs: 120000, retries: 0 })).result || 'failed'; }
        catch (e) { res = 'failed'; }
        log(`   滑块结果: ${res}`);
        deadline = Date.now() + 20000;
        if (res === 'solved' || res === 'passed') { solvedAt = Date.now(); refreshed = false; }
        else if (['aborted', 'blocked', 'unavailable'].includes(res)) rounds = cfg.slider_rounds;
        else await sleep(1500);
        continue;
      } else if (!manual) {
        if (cfg.unattended) return { state: 'captcha_failed', final_url: r.url };
        manual = true;
        await focusWorker();
        log(`🙋 请在抓取窗口中手动完成验证（最多 ${Math.round(task.manual_wait_ms / 1000)} 秒）`, 'warn');
        api('/api/captcha', { phase: 'manual' }, { retries: 0 }).catch(() => { });
        deadline = Date.now() + task.manual_wait_ms;
      }
    }

    if (Date.now() > deadline) {
      if (st === 'captcha') return { state: 'captcha_timeout', final_url: r.url };
      if (st === 'stale' || st === 'transient') return { state: 'stale', final_url: r.url, error: '页面未完成跳转（超时）' };
      return { state: 'timeout', final_url: r.url, error: '等待数据超时' };
    }
    await sleep(st === 'captcha' ? 500 : 250);
  }
}

// ---------------- 主循环 ----------------
function finish(n) {
  view.done = true;
  if (n.aborted) { setStatus(`🛑 已终止：${n.reason || ''}`); log(`🛑 本轮终止：${n.reason || ''}`, 'warn'); }
  else { setStatus('🎉 全部完成'); log('🎉 全部完成'); }
  if (AUTO) {
    log('本页将在 15 秒后自动关闭');
    sleep(15000).then(async () => {
      const me = await chrome.tabs.getCurrent().catch(() => null);
      if (me) chrome.tabs.remove(me.id).catch(() => { });
    });
  }
}

async function main() {
  $('ver').textContent = `v${VERSION} · 端口 ${PORT}`;
  chrome.tabs.getCurrent().then((me) => { if (me) chrome.tabs.update(me.id, { autoDiscardable: false }).catch(() => { }); }).catch(() => { });
  if (!TOKEN) { setStatus('缺少令牌：请运行 MW_Bridge.py，或在扩展弹窗中点击「开始」'); return; }

  running = view.running = true;
  try {
    const h = await api('/api/hello', { protocol: PROTOCOL, version: VERSION, ua: navigator.userAgent });
    if (!h.ok) throw new Error(h.error || 'hello 失败');
    session = h.session;
    cfg = h;
    log(`🔌 已连接桥接程序：待抓取 ${h.total} 个 | 目标交易日 ${h.last_valid_date || '-'} | `
      + `${h.unattended ? '无人值守' : '有人值守'} | 滑块自动${h.slider ? '开' : '关'}${h.dry_run ? ' | DRY-RUN' : ''}`);

    while (true) {
      if (stopping) await api('/api/stop', {}).catch(() => { });
      const n = await api('/api/next', {});
      if (n.summary) renderSummary(n.summary);
      if (n.action === 'done') { finish(n); break; }
      if (n.action === 'superseded') { log('ℹ️ 已有新的控制台会话接管，本页停止', 'warn'); break; }
      if (n.action === 'wait') { await blank(); await sleepStoppable(n.ms, `🧊 ${n.reason}`); continue; }
      if (n.action !== 'task') { log(`未知指令：${JSON.stringify(n)}`, 'err'); await sleep(3000); continue; }

      view.current = `${n.symbol} [${n.group}]`;
      $('current').textContent = `[${n.index}/${n.total}] ${n.symbol} → ${n.label} [${n.group}]${n.reissued ? '（重新下发）' : ''}`;
      if (n.delay_ms > 0 && !(await sleepStoppable(n.delay_ms, '⏱️ 拟人间隔等待'))) continue;

      setStatus(`🌐 打开 ${n.url}`);
      const res = await runTask(n);
      res.task_id = n.task_id;
      if (res.state !== 'ready') log(`[${n.symbol}] ${res.state}${res.error ? '：' + res.error : ''}`, res.state === 'blocked' ? 'err' : 'warn');
      else log(`[${n.symbol}] 已取得数据（${res.elapsed_ms} ms）`);
      const ack = await api('/api/result', res);
      if (ack.summary) renderSummary(ack.summary);
      if (ack.action === 'superseded') break;
    }
  } catch (e) {
    log(`❌ ${e.message || e}`, 'err');
    setStatus(`已中断：${e.message || e}`);
  } finally {
    running = view.running = false;
    view.done = true;
    publish();
    await closeWorker();
  }
}

$('stop').addEventListener('click', () => { stopping = true; setStatus('正在停止…'); log('⛔ 用户点击停止', 'warn'); });
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === 'mw_stop' && running) { stopping = true; setStatus('正在停止…'); log('⛔ 收到停止指令（弹窗）', 'warn'); }
});
window.addEventListener('beforeunload', (e) => { if (running) { e.preventDefault(); e.returnValue = ''; } });

main();