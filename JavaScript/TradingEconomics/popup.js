const logsDiv = document.getElementById('logs');

function appendLog(text, cls = 'info') {
    const d = document.createElement('div');
    d.textContent = text;
    d.className = cls;
    logsDiv.appendChild(d);
    logsDiv.scrollTop = logsDiv.scrollHeight;
}

// 一打开 Popup 就自动开始抓取
document.addEventListener('DOMContentLoaded', () => {
    // 先清空旧日志（如果有）
    logsDiv.innerHTML = '';
    // 立刻发起抓取流程
    chrome.runtime.sendMessage({ action: 'startAll' });
});

// 接收 background 发过来的日志
chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'log') {
        appendLog(msg.text, msg.status);
    }
});