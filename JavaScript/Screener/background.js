// background.js
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === "downloadData") {
        const data = request.data || [];
        if (!data.length) {
            sendResponse({ success: false, error: "No data to download" });
            return true;
        }

        // 构造文本
        let text = "";
        data.forEach(item => {
            text += `${item.symbol}: ${item.marketCap}, ${item.category}, ${item.price}, ${item.volume}\n`;
        });

        // 生成文件名
        const ts = new Date().toISOString().replace(/[:.]/g, "-").replace("T", "_").slice(0, 19);
        const filename = `screener_${ts}.txt`;

        const blob = new Blob([text], { type: 'text/plain' });
        const reader = new FileReader();
        reader.onload = function () {
            chrome.downloads.download({
                url: reader.result,
                filename,
                conflictAction: 'uniquify',
                saveAs: false
            }, id => {
                if (chrome.runtime.lastError)
                    sendResponse({ success: false, error: chrome.runtime.lastError.message });
                else
                    sendResponse({ success: true, filename });
            });
        };
        reader.onerror = () => sendResponse({ success: false, error: "FileReader error" });
        reader.readAsDataURL(blob);

        return true; // async
    }
});