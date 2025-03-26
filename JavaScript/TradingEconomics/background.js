// Handle icon click event
chrome.action.onClicked.addListener((tab) => {
    // We'll still use the popup, but we need to trigger the scraping automatically
    // Handled in popup.js now through auto-trigger
});

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

// Check if today is Sunday or Monday
function checkDay() {
    const day = new Date().getDay();
    return day === 0 || day === 1; // 0 is Sunday, 1 is Monday
}

// Optional: You can add install/update handlers here
chrome.runtime.onInstalled.addListener(() => {
    console.log('Economics Data Scraper extension installed');
});