// popup.js

document.addEventListener('DOMContentLoaded', () => {
    const statusList = document.getElementById('statusList');

    // 1. 清空上次可能存在的状态
    statusList.innerHTML = '';

    // 2. 立即发送消息给 background.js，让它开始抓取任务
    chrome.runtime.sendMessage({ action: "startScraping" });

    // 3. 监听来自 background.js 的状态更新消息 (这部分逻辑保持不变)
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "updateStatus") {
            const { message, type } = request.data; // type: 'success', 'error', 'info'

            const li = document.createElement('li');
            li.textContent = message;
            li.className = `status-${type}`; // 添加 CSS class
            statusList.appendChild(li);
        }
    });
});