// Array to store scraped data
let allYahooETFData = [];

// Function to update status in popup
function updatePopupStatus(text, logType = 'info', completed = false) {
    chrome.runtime.sendMessage({
        type: 'statusUpdate', // Changed from 'status'
        text: text,
        logType: logType, // Changed from 'status'
        completed: completed
    }).catch(error => console.log("Error sending status to popup:", error)); // Catch if popup is not open
}

// Function to scrape data from a tab for Yahoo Finance
async function scrapeYahooETFFromTab(tabId, url) {
    try {
        updatePopupStatus(`Navigating to ${url}`, 'info');
        // Navigate to the URL
        await chrome.tabs.update(tabId, { url: url });

        // Wait for the page to load - Yahoo can be slow and dynamic
        // Consider a more robust wait if needed (e.g., waiting for a specific element)
        await new Promise(resolve => {
            const listener = (tabIdUpdated, changeInfo) => {
                if (tabIdUpdated === tabId && changeInfo.status === 'complete') {
                    chrome.tabs.onUpdated.removeListener(listener);
                    // Additional delay for dynamic content loading
                    setTimeout(resolve, 5000); // Increased delay for Yahoo
                }
            };
            chrome.tabs.onUpdated.addListener(listener);
        });

        updatePopupStatus(`Page loaded: ${url}. Attempting to scrape...`, 'info');
        // Execute content script to scrape data
        const results = await chrome.tabs.sendMessage(tabId, { action: 'scrapeYahooETFs' });

        if (results && results.success) {
            updatePopupStatus(`Successfully scraped ${results.data.length} ETFs from ${url}`, 'success');
            allYahooETFData = [...allYahooETFData, ...results.data];
            return true;
        } else {
            const errorMsg = results ? results.error : "No response from content script.";
            updatePopupStatus(`Failed to scrape data from ${url}: ${errorMsg}`, 'error');
            return false;
        }
    } catch (error) {
        updatePopupStatus(`Error scraping from ${url}: ${error.message}`, 'error');
        console.error(`Error in scrapeYahooETFFromTab for ${url}:`, error);
        return false;
    }
}

// Function to generate CSV from data
function generateETFCSV(data) {
    // CSV header
    let csv = 'Symbol,Name,Price,Volume\n';

    // Add each row
    data.forEach(item => {
        const symbol = item.symbol ? `"${item.symbol.replace(/"/g, '""')}"` : '';
        const name = item.name ? `"${item.name.replace(/"/g, '""')}"` : '';
        const price = item.price ? `"${item.price.replace(/"/g, '""')}"` : '';
        const volume = item.volume ? `"${item.volume.replace(/"/g, '""')}"` : '';
        csv += `${symbol},${name},${price},${volume}\n`;
    });
    return csv;
}

// Function to send CSV data to popup for download
function downloadCSVViaPopup(csvData, filename) {
    chrome.runtime.sendMessage({
        type: 'csvData',
        data: csvData,
        filename: filename
    }).catch(error => {
        updatePopupStatus(`Error sending CSV to popup for download: ${error.message}. You might need to open the popup.`, 'error');
        // Fallback or alternative download method could be implemented here if needed
        // For now, we'll just log it.
        console.error("Error sending CSV to popup:", error);
    });
}


// Main function to coordinate the Yahoo ETF scraping process
async function startYahooScrapingProcess() {
    updatePopupStatus('Starting Yahoo ETF scraping process...', 'info');
    allYahooETFData = []; // Reset data for a new scrape

    let tab;
    try {
        // Create a new tab for scraping. It's better to keep it active for debugging.
        // For production, you might set active: false, but ensure content scripts still work.
        tab = await chrome.tabs.create({ active: false, url: 'about:blank' });

        const urls = [
            "https://finance.yahoo.com/markets/etfs/top/?start=0&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=100&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=200&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=300&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=400&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=500&count=100"
        ];

        for (const url of urls) {
            const success = await scrapeYahooETFFromTab(tab.id, url);
            if (!success) {
                updatePopupStatus(`Skipping remaining URLs due to error on ${url}.`, 'error');
                break; // Optional: stop if one page fails
            }
            // Optional: add a small delay between page loads if needed
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        if (allYahooETFData.length > 0) {
            updatePopupStatus(`Generating CSV with ${allYahooETFData.length} ETF records...`, 'info');
            const csv = generateETFCSV(allYahooETFData);
            const timestamp = new Date().toISOString().replace(/[:.-]/g, '').slice(0, -4); // YYYYMMDDTHHMMSS
            const filename = `topetf_${timestamp}.csv`;

            // Instead of chrome.downloads.download, send to popup.js
            downloadCSVViaPopup(csv, filename);
            // updatePopupStatus(`CSV file "${filename}" download initiated via popup.`, 'success', true); // This message is now in popup.js
        } else {
            updatePopupStatus('No ETF data was scraped. Cannot generate CSV.', 'error', true);
        }

    } catch (error) {
        updatePopupStatus(`Critical error in Yahoo ETF scraping process: ${error.message}`, 'error', true);
        console.error("Critical error in startYahooScrapingProcess:", error);
    } finally {
        if (tab && tab.id) {
            try {
                // Optional: close the tab after scraping is done or if an error occurs
                // For debugging, you might want to leave it open.
                // await chrome.tabs.remove(tab.id);
                // updatePopupStatus('Scraping tab closed.', 'info');
            } catch (closeError) {
                console.error("Error closing tab:", closeError);
            }
        }
        updatePopupStatus('Yahoo ETF scraping process finished.', 'info', true);
    }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startYahooScraping') {
        startYahooScrapingProcess();
        sendResponse({ status: 'started' });
        return true; // Indicates that the response will be sent asynchronously
    }
    // It's good practice to return true if you might send an async response for other actions too.
    return true;
});