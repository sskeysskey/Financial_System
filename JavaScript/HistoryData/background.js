// background.js

// 1) 监听来自 popup.js 的 "startScraping" 消息，注入 content.js
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "startScraping") {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs[0] && tabs[0].id) {
                chrome.scripting.executeScript({
                    target: { tabId: tabs[0].id },
                    files: ["content.js"]
                }, () => {
                    if (chrome.runtime.lastError) {
                        // 如果注入失败，也通知 popup
                        chrome.runtime.sendMessage({
                            action: "updateStatus",
                            data: { message: `注入脚本失败: ${chrome.runtime.lastError.message}`, type: 'error' }
                        });
                    }
                });
            }
        });
    }

    // 2) 监听来自 content.js 的下载请求，调用 downloads API
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
                // 下载失败，通知 popup
                chrome.runtime.sendMessage({
                    action: "updateStatus",
                    data: { message: `下载失败: ${chrome.runtime.lastError.message}`, type: 'error' }
                });
            } else {
                // 下载成功，也通知 popup
                chrome.runtime.sendMessage({
                    action: "updateStatus",
                    data: { message: `任务完成，已开始下载 ${filename}`, type: 'success' }
                });
            }
        });
    }

    // 3) 监听来自 content.js 的状态更新，并将其转发给 popup.js
    if (request.action === "updateStatus") {
        chrome.runtime.sendMessage({
            action: "updateStatus",
            data: request.data
        });
    }
});