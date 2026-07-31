document.addEventListener('DOMContentLoaded', function () {
  const statusDiv = document.getElementById('status');
  const progressBar = document.getElementById('progressBar');
  const logContainer = document.getElementById('logContainer');
  const btnRestart = document.getElementById('btnRestart');
  const btnStop = document.getElementById('btnStop');

  let lastSeq = 0;

  // 与 background 建立长连接：既能触发续跑，也帮 Service Worker 保活
  let port = null;
  try {
    port = chrome.runtime.connect({ name: 'popup' });
    setInterval(() => { try { port.postMessage({ type: 'ping' }); } catch (e) { } }, 5000);
  } catch (e) { }

  // 打开 popup 即尝试启动（若已在跑或刚跑完，则只显示进度）
  chrome.runtime.sendMessage({ action: 'start' }, () => void chrome.runtime.lastError);

  btnRestart.addEventListener('click', () => {
    if (!confirm('确定要放弃当前进度，重新开始抓取吗？')) return;
    lastSeq = 0;
    logContainer.innerHTML = '';
    chrome.runtime.sendMessage({ action: 'start', force: true }, () => void chrome.runtime.lastError);
  });

  btnStop.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'stop' }, () => void chrome.runtime.lastError);
  });

  function appendLogs(logs) {
    for (const l of logs) {
      if (l.seq <= lastSeq) continue;
      lastSeq = l.seq;
      const p = document.createElement('p');
      p.className = `log-message log-${l.type}`;
      p.textContent = `[${new Date(l.t).toLocaleTimeString()}] ${l.text}`;
      logContainer.appendChild(p);
    }
    logContainer.scrollTop = logContainer.scrollHeight;
  }

  function render(s) {
    if (!s) { statusDiv.textContent = '尚未开始'; return; }
    const total = s.tasks.length;
    const done = s.tasks.filter(t => t.status === 'done').length;
    const running = s.tasks.filter(t => t.status === 'running').length;
    progressBar.style.width = `${(done / total * 100).toFixed(1)}%`;

    if (s.running) {
      statusDiv.textContent = `进行中  ${done}/${total}  (第 ${s.round} 轮, 正在抓 ${running} 页)`;
    } else if (s.finished) {
      statusDiv.textContent = `已完成  ${done}/${total}`;
    } else {
      statusDiv.textContent = `已停止  ${done}/${total}`;
    }
    appendLogs(s.logs || []);
  }

  function refresh() {
    chrome.storage.local.get('scraperState', o => {
      if (chrome.runtime.lastError) return;
      render(o.scraperState);
    });
  }

  refresh();
  setInterval(refresh, 800);
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.scraperState) render(changes.scraperState.newValue);
  });
});