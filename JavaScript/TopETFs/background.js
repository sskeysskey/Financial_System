// Array to store scraped data
let allYahooETFData = [];
const MAX_RETRIES = 3; // 定义最大重试次数

// 辅助函数：睡眠/等待
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Function to update status in popup
function updatePopupStatus(text, logType = 'info', completed = false) {
    chrome.runtime.sendMessage({
        type: 'statusUpdate', // Changed from 'status'
        text: text,
        logType: logType, // Changed from 'status'
        completed: completed
    }).catch(error => {
        // 如果 Popup 关闭了，忽略错误，但在控制台打印
        // console.log("Popup closed, status update skipped.");
    });
}

// Function to scrape data from a tab for Yahoo Finance (带有重试机制)
async function scrapeYahooETFFromTab(tabId, url) {
    let attempt = 0;

    while (attempt < MAX_RETRIES) {
        attempt++;

        // 如果是重试，打印日志
        if (attempt > 1) {
            updatePopupStatus(`[Attempt ${attempt}/${MAX_RETRIES}] Retrying ${url}...`, 'warning');
            await sleep(2000); // 重试前等待2秒
        } else {
            updatePopupStatus(`Navigating to ${url}`, 'info');
        }

        try {
            // 1. Navigate to the URL (每次重试都会重新加载页面)
            await chrome.tabs.update(tabId, { url: url });

            // 2. Wait for the page to load
            await new Promise((resolve, reject) => {
                // 设置一个超时，防止页面永远加载不完
                const timeoutId = setTimeout(() => {
                    chrome.tabs.onUpdated.removeListener(listener);
                    reject(new Error("Page load timeout"));
                }, 30000); // 30秒超时

                const listener = (tabIdUpdated, changeInfo) => {
                    if (tabIdUpdated === tabId && changeInfo.status === 'complete') {
                        chrome.tabs.onUpdated.removeListener(listener);
                        clearTimeout(timeoutId);
                        // Additional delay for dynamic content loading
                        setTimeout(resolve, 3000); // 增加等待时间到3秒，Yahoo比较慢
                    }
                };
                chrome.tabs.onUpdated.addListener(listener);
            });

            updatePopupStatus(`Page loaded. Sending scrape command (Attempt ${attempt})...`, 'info');

            // 3. Execute content script to scrape data
            // 注意：这里可能会抛出错误（如果 content script 没准备好），所以放在 try block 里
            const results = await chrome.tabs.sendMessage(tabId, { action: 'scrapeYahooETFs' });

            // 4. Check results
            if (results && results.success && results.data && results.data.length > 0) {
                updatePopupStatus(`Successfully scraped ${results.data.length} ETFs from ${url}`, 'success');
                allYahooETFData = [...allYahooETFData, ...results.data];
                return true; // 成功！跳出函数
            } else {
                // 虽然通信成功，但返回了错误或没有数据
                const errorMsg = results ? results.error : "No data returned";
                console.warn(`Attempt ${attempt} failed: ${errorMsg}`);

                if (attempt === MAX_RETRIES) {
                    updatePopupStatus(`Failed to scrape ${url} after ${MAX_RETRIES} attempts. Error: ${errorMsg}`, 'error');
                }
                // 继续循环进行下一次重试
            }

        } catch (error) {
            console.error(`Error in scrapeYahooETFFromTab (Attempt ${attempt}):`, error);

            if (attempt === MAX_RETRIES) {
                updatePopupStatus(`Critical error scraping ${url}: ${error.message}`, 'error');
            }
            // 继续循环进行下一次重试
        }
    }

    return false; // 所有重试都失败了
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
        // Create a new tab for scraping.
        tab = await chrome.tabs.create({ active: false, url: 'about:blank' });

        const urls = [
            "https://finance.yahoo.com/markets/etfs/top/?start=0&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=100&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=200&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=300&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=400&count=100"
        ];

        for (const url of urls) {
            const success = await scrapeYahooETFFromTab(tab.id, url);

            if (!success) {
                // 即使失败，我们也可以选择继续抓取下一个 URL，而不是直接 break
                // 这里我保留了你原来的逻辑：如果一个失败，停止后续操作。
                // 如果你想即使失败也继续，可以注释掉下面这行 break;
                updatePopupStatus(`Stopping process due to failure on ${url}.`, 'error');
                break;
            }

            // URL 之间的间隔，避免请求过快
            await sleep(1000);
        }

        if (allYahooETFData.length > 0) {
            updatePopupStatus(`Generating CSV with ${allYahooETFData.length} ETF records...`, 'info');
            const csv = generateETFCSV(allYahooETFData);
            const now = new Date();
            const year = now.getFullYear().toString().slice(-2);
            const month = (now.getMonth() + 1).toString().padStart(2, '0');
            const day = now.getDate().toString().padStart(2, '0');
            const timestamp = `${year}${month}${day}`;
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
                await chrome.tabs.remove(tab.id);
                updatePopupStatus('Scraping tab closed.', 'info');
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
    return true;
});