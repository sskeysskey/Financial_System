// popup.js

document.addEventListener('DOMContentLoaded', () => {
    const statusList = document.getElementById('statusList');

    // 1. 清空上次可能存在的状态
    statusList.innerHTML = '';

    // 2. 立即发送消息给 background.js，让它开始抓取任务
    chrome.runtime.sendMessage({ action: "startScraping" });

    // 3. 监听来自 background.js 的状态更新消息
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "updateStatus") {
            const { message, type } = request.data; // type: 'success', 'error', 'info'

            const li = document.createElement('li');
            li.textContent = message;
            li.className = `status-${type}`; // 添加 CSS class
            statusList.appendChild(li);

            // --- 新增代码：将列表滚动到底部 ---
            // statusList.scrollHeight 是整个列表内容的总高度
            // 将 scrollTop 设置为这个值，就能让可见区域滚动到最下方
            statusList.scrollTop = statusList.scrollHeight;
        }
    });
});