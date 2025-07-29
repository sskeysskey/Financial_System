// background.js

// 1) 点击图标时，向当前页注入 content.js
chrome.action.onClicked.addListener((tab) => {
    if (!tab.id) return;
    chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"]
    }, () => {
        if (chrome.runtime.lastError) {
            console.error("注入 content.js 失败:", chrome.runtime.lastError);
        }
    });
});

// 2) 接收来自 content.js 的下载请求，调用 downloads API
chrome.runtime.onMessage.addListener((request, sender) => {
    if (request.action === "downloadCSV") {
        const csv = request.csv || "";
        const filename = request.filename || "data.csv";
        const url = "data:text/csv;charset=utf-8," + encodeURIComponent(csv);
        chrome.downloads.download({
            url,
            filename,
            saveAs: false
        }, (downloadId) => {
            if (chrome.runtime.lastError) {
                console.error("下载失败:", chrome.runtime.lastError);
            } else {
                console.log("下载已开始，ID:", downloadId);
            }
        });
    }
});