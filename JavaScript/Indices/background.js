// Listen for messages from popup
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action === "startScraping") {
        startScraping();
    }
});

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action === "dataScraped") {
        processScrapedData(message.data);
    }
});

async function startScraping() {
    updateStatus("init", "success", "Initialization complete");
    updateStatus("openingTab", "in-progress", "Opening new tab...");

    try {
        // Check if today is Sunday or Monday
        const now = new Date();
        const dayOfWeek = now.getDay(); // 0 is Sunday, 1 is Monday

        if (dayOfWeek === 0 || dayOfWeek === 1) {
            updateStatus("dayCheck", "error", "Today is either Sunday or Monday. The script will not run.");
            return;
        }

        // Create a new tab but don't activate it
        const tab = await chrome.tabs.create({
            url: "https://tradingeconomics.com/stocks",
            active: false
        });

        updateStatus("openingTab", "success", "New tab opened");
        updateStatus("scraping", "in-progress", "Scraping data...");

        // Wait for the content script to send back data
        // This will be handled by the message listener for "dataScraped"
    } catch (error) {
        updateStatus("openingTab", "error", `Error opening tab: ${error.message}`);
    }
}

function processScrapedData(data) {
    if (!data || data.length === 0) {
        updateStatus("scraping", "error", "No data scraped");
        return;
    }

    updateStatus("scraping", "success", `Successfully scraped ${data.length} items`);
    updateStatus("downloading", "in-progress", "Preparing CSV file for download...");

    try {
        // Format data as CSV
        const headers = "date\tname\tprice\tcategory\n";
        const rows = data.map(item =>
            `${item.date}\t${item.name}\t${item.price}\t${item.category}`
        ).join("\n");
        const csvContent = headers + rows;

        // Create blob and download
        const blob = new Blob([csvContent], { type: 'text/csv' });

        // Get today's date for the filename
        const today = new Date();
        const dateStr = today.toISOString().split('T')[0];
        const filename = `Indices_${dateStr}.csv`;

        // Use the download API to download the file directly
        // Create a temporary data URL without using URL.createObjectURL
        const dataStr = "data:text/csv;charset=utf-8," + encodeURIComponent(csvContent);

        chrome.downloads.download({
            url: dataStr,
            filename: filename,
            saveAs: false,
            conflictAction: 'uniquify'
        }, function (downloadId) {
            if (chrome.runtime.lastError) {
                updateStatus("downloading", "error", `Download error: ${chrome.runtime.lastError.message}`);
            } else {
                updateStatus("downloading", "success", `File downloaded as ${filename}`);

                // Close the tab after download is complete
                chrome.tabs.query({ url: "https://tradingeconomics.com/stocks" }, function (tabs) {
                    if (tabs && tabs.length > 0) {
                        chrome.tabs.remove(tabs[0].id, function () {
                            updateStatus("closingTab", "success", "Tab closed");
                            updateStatus("complete", "success", "All operations completed successfully");
                        });
                    }
                });
            }
        });
    } catch (error) {
        updateStatus("downloading", "error", `Error creating CSV: ${error.message}`);
    }
}

function updateStatus(step, status, message) {
    chrome.runtime.sendMessage({
        type: "status",
        step: step,
        status: status,
        message: message
    });
}