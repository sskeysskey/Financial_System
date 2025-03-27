document.addEventListener('DOMContentLoaded', function () {
    const statusElement = document.getElementById('status');

    // 获取当前日期
    const now = new Date();
    const today = now.toISOString().split('T')[0];

    // 检查是否是周日(0)或周一(1)
    const dayOfWeek = now.getDay();
    if (dayOfWeek === 0 || dayOfWeek === 1) {
        statusElement.innerHTML = "Today is either Sunday or Monday. The script will not run.";
        statusElement.classList.add('error');
        return;
    }

    // 开始爬取数据
    statusElement.innerHTML = "Starting the scraping process...<span class='loading'></span>";

    // 发送消息给background script开始爬取数据
    chrome.runtime.sendMessage({ action: "startScraping" });

    // 监听消息更新状态
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        console.log("Received message:", message);

        if (message.action === "updateStatus") {
            // 保留之前的状态并添加新状态
            const newStatus = statusElement.innerHTML + "\n" + message.status;
            statusElement.innerHTML = newStatus;

            // 如果有错误，添加错误样式
            if (message.isError) {
                statusElement.classList.add('error');
            }

            // 自动滚动到底部
            statusElement.scrollTop = statusElement.scrollHeight;
        } else if (message.action === "downloadStatus") {
            if (message.success) {
                statusElement.innerHTML += "\nFile downloaded successfully!";
                statusElement.classList.add('success');
            } else {
                statusElement.innerHTML += "\nError downloading file: " + message.error;
                statusElement.classList.add('error');
            }

            // 自动滚动到底部
            statusElement.scrollTop = statusElement.scrollHeight;
        }

        return true; // 表示将异步发送响应
    });
});