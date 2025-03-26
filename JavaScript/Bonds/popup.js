document.addEventListener('DOMContentLoaded', function () {
    const statusDiv = document.getElementById('status');

    function addLogMessage(message, type = 'info') {
        const logItem = document.createElement('div');
        logItem.className = `log-item ${type}`;
        logItem.textContent = message;
        statusDiv.appendChild(logItem);
        statusDiv.scrollTop = statusDiv.scrollHeight;
    }

    // 自动开始抓取过程，无需用户点击按钮
    chrome.runtime.sendMessage({ action: 'startScraping' }, function (response) {
        if (response && response.status === 'started') {
            addLogMessage('Background process initiated.', 'info');
        }
    });

    // 监听状态更新
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.type === 'status') {
            addLogMessage(message.text, message.status);
        }
        else if (message.type === 'csvData') {
            // 处理CSV数据下载
            const blob = new Blob([message.data], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = message.filename;
            document.body.appendChild(a);
            a.click();

            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 100);

            addLogMessage(`CSV file "${message.filename}" is being downloaded`, 'success');
        }

        sendResponse({ received: true });
        return true;
    });
});