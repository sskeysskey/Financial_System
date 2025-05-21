// Handle download events
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "downloadCSV") {
        chrome.downloads.download({
            url: message.dataUrl,
            filename: 'Commodities_' + new Date().toISOString().split('T')[0] + '.csv',
            saveAs: false
        }, (downloadId) => {
            if (chrome.runtime.lastError) {
                chrome.runtime.sendMessage({
                    action: "downloadStatus",
                    success: false,
                    error: chrome.runtime.lastError.message
                });
            } else {
                chrome.runtime.sendMessage({
                    action: "downloadStatus",
                    success: true,
                    downloadId: downloadId
                });
            }
        });
        return true; // 表示将异步发送响应
    }
});