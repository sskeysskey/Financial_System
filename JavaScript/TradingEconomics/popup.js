const logsDiv = document.getElementById('logs');
document.getElementById('startBtn').addEventListener('click', () => {
    logsDiv.innerHTML = '';
    chrome.runtime.sendMessage({ action: 'startAll' });
});

function appendLog(text, cls = 'info') {
    const d = document.createElement('div');
    d.textContent = text;
    d.className = cls;
    logsDiv.appendChild(d);
    logsDiv.scrollTop = logsDiv.scrollHeight;
}

// 接收 background 的日志更新
chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'log') {
        appendLog(msg.text, msg.status);
    }
});