// background.js
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === "downloadData") {
        const data = request.data || [];
        if (!data.length) {
            sendResponse({ success: false, error: "No data to download" });
            return true;
        }

        // 构造文本内容
        let text = "";
        data.forEach(item => {
            text += `${item.symbol}: ${item.marketCap}, ${item.category}, ${item.price}, ${item.volume}\n`;
        });

        // 如果 caller 提供了 filename，就用它；否则生成默认 screener_YYMMDD.txt
        let filename = request.filename;
        if (!filename) {
            const now = new Date();
            const yy = String(now.getFullYear() % 100).padStart(2, "0");
            const mm = String(now.getMonth() + 1).padStart(2, "0");
            const dd = String(now.getDate()).padStart(2, "0");
            filename = `screener_${yy}${mm}${dd}.txt`;
        }

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

        return true; // async
    }
});