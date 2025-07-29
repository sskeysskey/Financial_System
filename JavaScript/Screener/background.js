// background.js
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === "downloadData") {
        const data = request.data || [];
        if (!data.length) {
            sendResponse({ success: false, error: "No data to download" });
            return true;
        }

        // 构造Python脚本期望的文本内容
        // 格式: SYMBOL: MARKETCAP, CATEGORY, PRICE, VOLUME
        let text = "";
        data.forEach(item => {
            // 注意这里的字段顺序和格式
            text += `${item.symbol}: ${item.marketCap}, ${item.category}, ${item.price}, ${item.volume}\n`;
        });

        // 获取文件名 (逻辑保持不变)
        let filename = request.filename;
        if (!filename) {
            const now = new Date();
            const yy = String(now.getFullYear() % 100).padStart(2, "0");
            const mm = String(now.getMonth() + 1).padStart(2, "0");
            const dd = String(now.getDate()).padStart(2, "0");
            filename = `screener_${yy}${mm}${dd}.txt`;
        }

        // 将文件名后缀从 .csv 改回 .txt (如果之前改过的话)
        if (filename.endsWith('.csv')) {
            filename = filename.replace('.csv', '.txt');
        }

        // 创建并下载文件 (逻辑保持不变)
        const blob = new Blob([text], { type: 'text/plain' });
        const reader = new FileReader();
        reader.onload = function () {
            chrome.downloads.download({
                url: reader.result,
                filename,
                conflictAction: 'uniquify',
                saveAs: false
            }, id => {
                if (chrome.runtime.lastError) {
                    sendResponse({ success: false, error: chrome.runtime.lastError.message });
                } else {
                    sendResponse({ success: true, filename });
                }
            });
        };
        reader.onerror = () => sendResponse({ success: false, error: "FileReader error" });
        reader.readAsDataURL(blob);

        return true; // 异步操作
    }
});