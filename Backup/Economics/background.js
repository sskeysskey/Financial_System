// Handle download events
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "downloadCSV") {
        chrome.downloads.download({
            url: message.dataUrl,
            filename: 'economic_data_' + new Date().toISOString().split('T')[0] + '.csv',
            saveAs: false
        });
    }
});