'use strict';
const RUNNER = chrome.runtime.getURL('runner.html');
const $ = (id) => document.getElementById(id);

async function getPort() { const { mwPort } = await chrome.storage.local.get('mwPort'); return mwPort || 8765; }
async function health(port) {
  try {
    const ctrl = new AbortController();
    setTimeout(() => ctrl.abort(), 1500);
    const r = await fetch(`http://127.0.0.1:${port}/health`, { signal: ctrl.signal, cache: 'no-store' });
    return r.ok ? await r.json() : null;
  } catch (e) { return null; }
}
async function findRunner() { return (await chrome.tabs.query({})).find((t) => t.url && t.url.startsWith(RUNNER)); }

async function refresh() {
  const port = await getPort();
  $('port').value = port;
  const h = await health(port);
  const b = $('bridge');
  if (h && h.app === 'mw_bridge') {
    b.textContent = h.finished ? '● 已结束' : (h.connected ? '● 运行中' : '● 等待开始');
    b.className = 'ok';
  } else { b.textContent = '● 未运行'; b.className = 'bad'; }
  const { mwRun } = await chrome.storage.session.get('mwRun');
  if (mwRun && mwRun.summary) {
    const s = mwRun.summary;
    $('run').textContent = `${mwRun.running ? '运行中' : '已停止'}：${s.done}/${s.total}，成功 ${s.success}，失败 ${s.failed}`
      + (mwRun.status ? ` ｜ ${mwRun.status}` : '');
  }
}

$('port').addEventListener('change', async () => { await chrome.storage.local.set({ mwPort: Number($('port').value) || 8765 }); refresh(); });
$('start').addEventListener('click', async () => {
  const port = await getPort();
  const h = await health(port);
  if (!h || h.app !== 'mw_bridge') { $('run').textContent = '桥接程序未运行：请先在终端执行 MW_Bridge.py（见下方命令）'; return; }
  await chrome.tabs.create({ url: `http://127.0.0.1:${port}/start`, active: false });
  window.close();
});
$('console').addEventListener('click', async () => {
  const t = await findRunner();
  if (t) { await chrome.windows.update(t.windowId, { focused: true }); await chrome.tabs.update(t.id, { active: true }); }
  else $('run').textContent = '控制台未打开';
});
$('stop').addEventListener('click', () => { chrome.runtime.sendMessage({ type: 'mw_stop' }).catch(() => { }); $('run').textContent = '已发送停止指令'; });

refresh();
setInterval(refresh, 2000);