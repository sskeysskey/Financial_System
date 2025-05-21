// Array to store scraped data
let allScrapedData = [];
const today = new Date().toISOString().split('T')[0]; // Format: YYYY-MM-DD
// Calculate yesterday's date
const yesterday = new Date();
yesterday.setDate(yesterday.getDate() - 1);
const formattedYesterday = yesterday.toISOString().split('T')[0]; // Format: YYYY-MM-DD

// Function to update status in popup
function updateStatus(text, status = 'info', completed = false) {
    chrome.runtime.sendMessage({
        type: 'status',
        text: text,
        status: status,
        completed: completed
    });
}

// Function to scrape data from a tab
async function scrapeFromTab(tabId, url) {
    try {
        // Navigate to the URL
        await chrome.tabs.update(tabId, { url: url });

        // Wait for the page to load
        await new Promise(resolve => setTimeout(resolve, 3000));

        // Execute content script to scrape data
        const results = await chrome.tabs.sendMessage(tabId, { action: 'scrapeBonds' });

        if (results && results.success) {
            updateStatus(`Successfully scraped ${results.data.length} bonds from ${url}`, 'success');

            // Add yesterday's date and category to each result
            const processedResults = results.data.map(item => ({
                date: formattedYesterday,
                name: item.name,
                price: item.price,
                category: 'Bonds'
            }));

            allScrapedData = [...allScrapedData, ...processedResults];
            return true;
        } else {
            updateStatus(`Failed to scrape data from ${url}: ${results.error}`, 'error');
            return false;
        }
    } catch (error) {
        updateStatus(`Error scraping from ${url}: ${error.message}`, 'error');
        return false;
    }
}

// Function to generate CSV from data
function generateCSV(data) {
    // CSV header
    let csv = 'date,name,price,category\n';

    // Add each row
    data.forEach(item => {
        csv += `${item.date},${item.name},${item.price},${item.category}\n`;
    });

    return csv;
}

// Function to save CSV file
function saveCSV(csv) {
    // 使用 Data URL 而不是 Blob URL
    const dataUrl = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);

    const filename = `bonds_${today}.csv`;

    chrome.downloads.download({
        url: dataUrl,
        filename: filename,
        saveAs: false,
        conflictAction: 'uniquify'
    }, downloadId => {
        if (chrome.runtime.lastError) {
            updateStatus(`Error saving CSV: ${chrome.runtime.lastError.message}`, 'error', true);
        } else {
            updateStatus(`CSV file saved successfully as ${filename}`, 'success', true);
        }
    });
}

// Main function to coordinate the scraping process
async function startScrapingProcess() {
    updateStatus('Starting the scraping process...', 'info');
    allScrapedData = []; // Reset data

    try {
        // Create a new tab for scraping
        const tab = await chrome.tabs.create({ active: false, url: 'about:blank' });

        // URLs to scrape
        const urls = [
            'https://tradingeconomics.com/united-states/government-bond-yield',
            'https://tradingeconomics.com/bonds'
        ];

        // Scrape each URL
        for (const url of urls) {
            updateStatus(`Opening ${url}...`, 'info');
            await scrapeFromTab(tab.id, url);
        }

        // Generate and save CSV
        if (allScrapedData.length > 0) {
            updateStatus(`Generating CSV with ${allScrapedData.length} records...`, 'info');
            const csv = generateCSV(allScrapedData);
            saveCSV(csv);
        } else {
            updateStatus('No data was scraped. Cannot generate CSV.', 'error', true);
        }

        // Close the tab
        chrome.tabs.remove(tab.id);

    } catch (error) {
        updateStatus(`Error in scraping process: ${error.message}`, 'error', true);
    }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startScraping') {
        startScrapingProcess();
        sendResponse({ status: 'started' });
    }
    return true;
});