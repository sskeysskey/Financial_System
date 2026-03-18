// Array to store scraped data
let allYahooETFData = [];

// ====== 关键并发参数 ======
const CONCURRENCY = 3;         // 同时打开4个标签页并发抓取
const MAX_RETRIES = 3;         // 最大重试次数
const SCRAPE_TIMEOUT = 30000;  // 抓取超时时间 (30秒)
const POST_LOAD_DELAY = 3000;  // 页面加载完成后的等待时间 (3秒，Yahoo加载较慢)
const RETRY_DELAY = 2000;      // 重试前的等待时间 (2秒)

// 辅助函数：睡眠/等待
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Function to update status in popup
function updatePopupStatus(text, logType = 'info', completed = false) {
    chrome.runtime.sendMessage({
        type: 'statusUpdate',
        text: text,
        logType: logType,
        completed: completed
    }).catch(error => {
        // 如果 Popup 关闭了，忽略错误
    });
}

/**
 * 并发池：同时运行最多 limit 个任务
 * 返回按原始顺序排列的结果数组
 */
async function runWithConcurrency(items, limit) {
    const results = new Array(items.length);
    let nextIndex = 0;
    let completedCount = 0;

    async function worker() {
        while (nextIndex < items.length) {
            const i = nextIndex++;
            const url = items[i];

            updatePopupStatus(`[${i + 1}/${items.length}] 正在处理: ${url}...`, 'info');

            // 调用带重试机制的单页抓取
            const pageResults = await scrapePageWithRetry(url, MAX_RETRIES);
            results[i] = pageResults || [];

            completedCount++;
            if (pageResults && pageResults.length > 0) {
                updatePopupStatus(`成功获取 ${pageResults.length} 条数据 (${completedCount}/${items.length})`, 'success');
            } else {
                updatePopupStatus(`重试 ${MAX_RETRIES} 次后仍未获取到数据: ${url} (${completedCount}/${items.length})`, 'warning');
            }
        }
    }

    // 启动 limit 个并发 worker
    const workers = [];
    for (let w = 0; w < Math.min(limit, items.length); w++) {
        workers.push(worker());
    }
    await Promise.all(workers);

    return results;
}

/**
 * 带重试机制的页面抓取函数 (每次创建新标签页，抓完销毁)
 */
async function scrapePageWithRetry(url, maxRetries) {
    let attempt = 0;

    while (attempt < maxRetries) {
        attempt++;

        // 如果是重试，打印日志
        if (attempt > 1) {
            updatePopupStatus(`[Attempt ${attempt}/${maxRetries}] Retrying ${url}...`, 'warning');
        }

        let tab = null;

        try {
            // 1. 创建新标签页 (后台静默打开)
            tab = await chrome.tabs.create({ url, active: false });

            // 2. 等待页面加载完成
            await new Promise((resolve, reject) => {
                // 设置一个超时，防止页面永远加载不完
                const timeoutId = setTimeout(() => {
                    chrome.tabs.onUpdated.removeListener(listener);
                    reject(new Error("Page load timeout"));
                }, 30000); // 30秒超时

                const listener = (tabIdUpdated, changeInfo) => {
                    if (tabIdUpdated === tab.id && changeInfo.status === 'complete') {
                        chrome.tabs.onUpdated.removeListener(listener);
                        clearTimeout(timeoutId);
                        // 额外等待动态内容加载
                        setTimeout(resolve, POST_LOAD_DELAY);
                    }
                };
                chrome.tabs.onUpdated.addListener(listener);
            });

            // 3. 发送抓取指令并等待响应
            const response = await new Promise((resolve, reject) => {
                chrome.tabs.sendMessage(tab.id, { action: 'scrapeYahooETFs' }, res => {
                    if (chrome.runtime.lastError) {
                        reject(new Error(chrome.runtime.lastError.message));
                    } else if (res) {
                        resolve(res);
                    } else {
                        reject(new Error("Content script did not send a response."));
                    }
                });
                // 设置抓取超时
                setTimeout(() => reject(new Error("Scrape timeout")), SCRAPE_TIMEOUT);
            });

            // 4. 检查结果
            if (response && response.success && response.data && response.data.length > 0) {
                return response.data; // 成功，返回数据
            } else {
                const errorMsg = response ? response.error : "No data returned";
                console.warn(`Attempt ${attempt} failed for ${url}: ${errorMsg}`);

                if (attempt < maxRetries) {
                    await sleep(RETRY_DELAY);
                }
                // 继续循环进行下一次重试
            }

        } catch (error) {
            console.error(`Error in scrapePageWithRetry (Attempt ${attempt}) for ${url}:`, error);

            if (attempt < maxRetries) {
                await sleep(RETRY_DELAY);
            }
        } finally {
            // 5. 无论成功失败，确保关闭该标签页释放资源
            if (tab && tab.id) {
                await chrome.tabs.remove(tab.id).catch(e => console.warn("Could not remove tab:", e));
            }
            // 继续循环进行下一次重试
        }
    }

    return []; // 所有重试均失败，返回空数组
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
        updatePopupStatus(`Error sending CSV to popup for download: ${error.message}`, 'error');
        console.error("Error sending CSV to popup:", error);
    });
}

// Main function to coordinate the Yahoo ETF scraping process
async function startYahooScrapingProcess() {
    updatePopupStatus(`Starting Yahoo ETF scraping process with concurrency: ${CONCURRENCY}...`, 'info');
    allYahooETFData = []; // Reset data

    try {
        const urls = [
            "https://finance.yahoo.com/markets/etfs/top/?start=0&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=100&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=200&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=300&count=100",
            "https://finance.yahoo.com/markets/etfs/top/?start=400&count=100"
        ];

        // ====== 核心改动：使用并发池替代串行循环 ======
        const orderedResults = await runWithConcurrency(urls, CONCURRENCY);

        // 合并所有结果（保持原有顺序）
        allYahooETFData = orderedResults.flat();

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
        updatePopupStatus('Yahoo ETF scraping process finished.', 'info', true);
    }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startYahooScraping') {
        startYahooScrapingProcess();
        sendResponse({ status: 'started' });
        return true;
    }
    return true;
});