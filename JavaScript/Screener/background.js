chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === "downloadData") {
        try {
            const data = request.data;
            if (!data || data.length === 0) {
                sendResponse({ success: false, error: "No data to download" });
                return true;
            }

            // Generate text content
            let textContent = "";
            data.forEach(item => {
                textContent += `${item.symbol}: ${item.marketCap}, ${item.name}, ${item.category}\n`;
            });

            // Generate filename
            const now = new Date();
            const timestamp = now.toISOString().replace(/[:.]/g, '-').replace('T', '_').substring(0, 19);
            const filename = `screener_${timestamp}.txt`;

            // Convert the text to a blob using Blob API
            const blob = new Blob([textContent], { type: 'text/plain' });

            // Use chrome.downloads.download with data URL instead of createObjectURL
            // Create a data URL from the text content directly
            const reader = new FileReader();
            reader.onload = function () {
                const dataUrl = reader.result;
                chrome.downloads.download({
                    url: dataUrl,
                    filename: filename,
                    saveAs: false,
                    conflictAction: 'uniquify'
                }, function (downloadId) {
                    if (chrome.runtime.lastError) {
                        sendResponse({
                            success: false,
                            error: chrome.runtime.lastError.message
                        });
                    } else {
                        sendResponse({
                            success: true,
                            filename: filename
                        });
                    }
                });
            };

            reader.onerror = function () {
                sendResponse({
                    success: false,
                    error: "Failed to create data URL"
                });
            };

            // Start reading the blob as a data URL
            reader.readAsDataURL(blob);

            return true; // Indicates async response
        } catch (err) {
            console.error("Error downloading data:", err);
            sendResponse({ success: false, error: err.message });
            return true;
        }
    }
});