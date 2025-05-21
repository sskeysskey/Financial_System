// 定义要爬取的货币
const currencies = [
    "CNYARS", "CNYINR", "CNYKRW", "CNYMXN", "CNYRUB", "CNYSGD", "CNYBRL",
    "CNYPHP", "CNYIDR", "CNYEGP", "CNYTHB", "CNYIRR"
];

// 获取前一天的日期
function getYesterdayDate() {
    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    return yesterday.toISOString().split('T')[0];
}

// 处理爬取请求
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "startScraping") {
        scrapeData();
    }
    return true; // 表示将异步发送响应
});

// 主要爬取函数
async function scrapeData() {
    let tab = null;
    try {
        // 打开一个新标签页
        updateStatus("Opening new tab...");
        tab = await chrome.tabs.create({
            url: 'https://tradingeconomics.com/currencies?base=cny',
            active: false
        });

        // 等待页面加载完成
        updateStatus("Waiting for page to load...");
        await new Promise(resolve => setTimeout(resolve, 5000)); // 增加等待时间确保页面加载

        // 注入content script，执行爬取
        updateStatus("Starting to scrape data...");

        try {
            const results = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: scrapeCurrencyData,
                args: [currencies]
            });

            updateStatus("Script executed, processing results...");

            if (!results || results.length === 0) {
                updateStatus("No results returned from script.", true);
                return;
            }

            const scrapedData = results[0].result;
            if (!scrapedData || scrapedData.length === 0) {
                updateStatus("No data found in scraped results.", true);
                return;
            }

            // 生成CSV文件
            updateStatus(`Successfully scraped ${scrapedData.length} currency items. Generating CSV...`);
            const yesterday = getYesterdayDate();
            const csvData = generateCSV(scrapedData, yesterday);

            updateStatus("CSV generated, preparing download...");

            // 使用Data URL而不是Object URL
            const dataUrl = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvData);
            const filename = 'Currencies_' + yesterday + '.csv';

            updateStatus("Starting download process...");

            // 尝试下载文件
            try {
                const downloadId = await initiateDownload(dataUrl, filename);
                updateStatus(`Download started with ID: ${downloadId}`);

                // 关闭标签页
                if (tab) {
                    await new Promise(resolve => setTimeout(resolve, 2000)); // 等待下载开始
                    updateStatus("Closing tab...");
                    await chrome.tabs.remove(tab.id);
                    tab = null;
                    updateStatus("Tab closed. Process completed successfully!");
                }
            } catch (downloadError) {
                updateStatus(`Download error: ${downloadError.message}`, true);
            }

        } catch (scriptError) {
            updateStatus(`Error executing script: ${scriptError.message}`, true);
        }

    } catch (error) {
        updateStatus(`General error: ${error.message}`, true);
    } finally {
        // 确保标签页被关闭，即使出错
        if (tab) {
            try {
                await chrome.tabs.remove(tab.id);
                updateStatus("Tab closed after error.");
            } catch (e) {
                updateStatus(`Error closing tab: ${e.message}`);
            }
        }
    }
}

// 在页面中爬取数据的函数
function scrapeCurrencyData(currencies) {
    console.log("Starting scraping currencies:", currencies);
    const results = [];

    for (const currency of currencies) {
        try {
            // 尝试查找货币链接 - 使用更灵活的选择器
            console.log(`Looking for currency: ${currency}`);
            let element = document.querySelector(`a[href*="${currency.toLowerCase()}"]`);

            // 备用方法：尝试更直接的方式查找链接
            if (!element) {
                const links = Array.from(document.querySelectorAll('a'));
                element = links.find(link => link.textContent.trim() === currency);
            }

            if (!element) {
                console.log(`Currency ${currency} not found`);
                continue;
            }

            // 找到包含该元素的行
            const row = element.closest('tr');
            if (!row) {
                console.log(`Row for ${currency} not found`);
                continue;
            }

            // 获取价格 - 尝试多种方式
            let priceElement = row.querySelector('#p');
            if (!priceElement) {
                priceElement = row.querySelector('.datatable-item');
            }

            if (!priceElement) {
                console.log(`Price element for ${currency} not found`);
                continue;
            }

            const price = priceElement.textContent.trim();
            console.log(`Found ${currency} with price ${price}`);

            // 存储结果
            results.push({
                name: currency,
                price: price
            });
        } catch (e) {
            console.error(`Error scraping ${currency}: ${e.message}`);
        }
    }

    console.log(`Scraped ${results.length} currencies`);
    return results;
}

// 生成CSV数据
function generateCSV(data, date) {
    // CSV头
    let csv = "date\tname\tprice\tcategory\n";

    // 添加数据行
    data.forEach(item => {
        csv += `${date}\t${item.name}\t${item.price}\tCurrencies\n`;
    });

    return csv;
}

// 更新状态
function updateStatus(status, isError = false) {
    console.log(status);
    chrome.runtime.sendMessage({
        action: "updateStatus",
        status: status,
        isError: isError
    });
}

// 启动下载
function initiateDownload(url, filename) {
    return new Promise((resolve, reject) => {
        chrome.downloads.download({
            url: url,
            filename: filename,
            saveAs: false,
            conflictAction: 'uniquify'
        }, (downloadId) => {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
            } else if (downloadId === undefined) {
                reject(new Error("Download failed, no download ID returned"));
            } else {
                resolve(downloadId);
            }
        });
    });
}