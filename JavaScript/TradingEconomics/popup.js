document.addEventListener('DOMContentLoaded', function () {
    const scrapeButton = document.getElementById('scrapeButton');
    const statusDiv = document.getElementById('status');
    const progressBar = document.getElementById('progressBar');

    // Check if today is Sunday or Monday
    function checkDay() {
        const day = new Date().getDay();
        return day === 0 || day === 1; // 0 is Sunday, 1 is Monday
    }

    scrapeButton.addEventListener('click', async () => {
        if (checkDay()) {
            statusDiv.textContent = "Today is Sunday or Monday. Not executing update operation.";
            return;
        }

        scrapeButton.disabled = true;
        statusDiv.textContent = "Starting data scraping...";
        progressBar.style.width = "10%";

        try {
            // Create a new tab in the background
            const tab = await chrome.tabs.create({
                url: 'https://tradingeconomics.com/united-states/indicators',
                active: false  // This keeps the tab in the background
            });

            // Wait for page to load and then start scraping
            statusDiv.textContent = "Page loaded. Starting data collection...";
            progressBar.style.width = "20%";

            // Message to the content script to start scraping
            chrome.tabs.onUpdated.addListener(function listener(tabId, changeInfo, tab) {
                if (tabId === tab.id && changeInfo.status === 'complete' &&
                    tab.url.includes('tradingeconomics.com/united-states/indicators')) {
                    chrome.tabs.onUpdated.removeListener(listener);

                    // Start scraping
                    chrome.tabs.sendMessage(tab.id, { action: "startScraping" });
                }
            });

            // Listen for progress updates from the content script
            chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
                if (message.action === "updateProgress") {
                    statusDiv.textContent = message.status;
                    progressBar.style.width = message.progress + "%";
                } else if (message.action === "scrapingComplete") {
                    statusDiv.textContent = "Scraping complete! Downloading data...";
                    progressBar.style.width = "100%";

                    // Download the CSV file
                    chrome.downloads.download({
                        url: message.dataUrl,
                        filename: 'economic_data_' + new Date().toISOString().split('T')[0] + '.csv',
                        saveAs: false
                    }, () => {
                        statusDiv.textContent = "Data downloaded to /Users/yanzhang/Downloads";
                        scrapeButton.disabled = false;
                    });
                } else if (message.action === "scrapingError") {
                    statusDiv.textContent = "Error: " + message.error;
                    progressBar.style.width = "0%";
                    scrapeButton.disabled = false;
                }
            });

        } catch (error) {
            statusDiv.textContent = "Error: " + error.message;
            progressBar.style.width = "0%";
            scrapeButton.disabled = false;
        }
    });
});