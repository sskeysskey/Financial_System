document.addEventListener('DOMContentLoaded', function () {
    const statusDiv = document.getElementById('status');
    const progressBar = document.getElementById('progressBar');
    const errorMessage = document.getElementById('errorMessage');
    const autoStartFlag = document.getElementById('autoStartFlag');

    // Variable to store the tab ID for later closing
    let scrapingTabId = null;

    // Check if today is Sunday or Monday
    function checkDay() {
        const day = new Date().getDay();
        return day === 0 || day === 1; // 0 is Sunday, 1 is Monday
    }

    // Start scraping automatically if the flag is set
    if (autoStartFlag.value === "true") {
        startScraping();
    }

    // Main scraping function
    async function startScraping() {
        if (checkDay()) {
            statusDiv.textContent = "Today is Sunday or Monday. Not executing update operation.";
            errorMessage.textContent = "Scraping is not performed on Sundays or Mondays.";
            errorMessage.style.display = "block";
            progressBar.style.width = "0%";
            return;
        }

        statusDiv.textContent = "Starting data scraping...";
        progressBar.style.width = "10%";

        try {
            // Create a new tab in the background
            const tab = await chrome.tabs.create({
                url: 'https://tradingeconomics.com/united-states/indicators',
                active: false  // This keeps the tab in the background
            });

            // Store the tab ID for later use
            scrapingTabId = tab.id;

            // Wait for page to load and then start scraping
            statusDiv.textContent = "Page loaded. Starting data collection...";
            progressBar.style.width = "20%";

            // Message to the content script to start scraping
            chrome.tabs.onUpdated.addListener(function listener(tabId, changeInfo, updatedTab) {
                if (tabId === tab.id && changeInfo.status === 'complete' &&
                    updatedTab.url.includes('tradingeconomics.com/united-states/indicators')) {
                    chrome.tabs.onUpdated.removeListener(listener);

                    // Start scraping
                    chrome.tabs.sendMessage(tab.id, { action: "startScraping" });
                }
            });
        } catch (error) {
            statusDiv.textContent = "Error initializing scraper";
            errorMessage.textContent = error.message;
            errorMessage.style.display = "block";
            progressBar.style.width = "0%";
        }
    }

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

                // Close the scraping tab if it exists
                if (scrapingTabId) {
                    chrome.tabs.remove(scrapingTabId, () => {
                        // Handle any error with the tab closing
                        if (chrome.runtime.lastError) {
                            console.error("Error closing tab:", chrome.runtime.lastError);
                        } else {
                            console.log("Scraping tab closed successfully");
                        }
                    });
                }
            });
        } else if (message.action === "scrapingError") {
            statusDiv.textContent = "Error occurred during scraping";
            errorMessage.textContent = message.error;
            errorMessage.style.display = "block";
            progressBar.style.width = "0%";

            // Also close the tab if there's an error
            if (scrapingTabId) {
                chrome.tabs.remove(scrapingTabId, () => {
                    if (chrome.runtime.lastError) {
                        console.error("Error closing tab after error:", chrome.runtime.lastError);
                    }
                });
            }
        }
    });
});