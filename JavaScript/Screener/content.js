// content.js
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === "scrapeData") {
        scrapeFinanceData(request.category)
            .then(results => sendResponse(results))
            .catch(err => {
                console.error("Scraping failed:", err);
                sendResponse([]);
            });
        return true; // 保持通道开放以进行异步响应
    }
});

/**
 * 从Yahoo Finance的screener页面抓取数据
 * @param {string} category - 股票分类
 * @returns {Promise<Array<object>>}
 */
async function scrapeFinanceData(category) {
    const results = [];

    // 1. 等待表格加载完成
    const table = await waitForElement("table.yf-ao6als");
    if (!table) {
        console.error("Could not find the data table.");
        return [];
    }

    // 2. 获取表头并创建列索引映射
    // 我们只关心 Volume 和 Market Cap 的位置
    const headers = Array.from(table.querySelectorAll("thead th"));
    const columnIndexMap = {};
    const headerMapping = {
        'Volume': 'volume',
        'Market Cap': 'marketCap',
    };

    headers.forEach((header, index) => {
        const headerText = header.textContent.trim();
        for (const key in headerMapping) {
            if (headerText.includes(key)) {
                columnIndexMap[headerMapping[key]] = index;
                break;
            }
        }
    });

    console.log("Column Index Map:", columnIndexMap); // 调试用

    // 3. 遍历表格的每一行 (tbody tr)
    const rows = table.querySelectorAll("tbody tr.row");
    for (const row of rows) {
        try {
            const cells = row.querySelectorAll("td");
            if (cells.length < 2) continue; // 至少要有几列

            // 使用可靠的选择器抓取 Symbol
            const symbolEl = row.querySelector('a[data-testid="table-cell-ticker"] span.symbol');
            const symbol = symbolEl ? symbolEl.textContent.trim() : null;

            if (!symbol) continue; // 如果没有symbol，跳过此行

            // 使用 fin-streamer 抓取价格
            const priceEl = row.querySelector('fin-streamer[data-field="regularMarketPrice"]');
            const price = priceEl ? parseFloat(priceEl.getAttribute("data-value")) : "N/A";

            // 使用动态索引从单元格中提取数据
            const volumeText = columnIndexMap.volume !== undefined ? cells[columnIndexMap.volume].textContent.trim() : "--";
            const marketCapText = columnIndexMap.marketCap !== undefined ? cells[columnIndexMap.marketCap].textContent.trim() : "--";

            const volume = parseSuffixedNumber(volumeText);
            const marketCap = parseSuffixedNumber(marketCapText);

            // 只要有市值数据，就收集
            if (typeof marketCap === "number" && !isNaN(marketCap)) {
                results.push({
                    symbol,
                    marketCap, // MarketCap 在前
                    category,
                    price,
                    volume
                });
            }
        } catch (e) {
            console.error("Error processing a row:", e, row);
        }
    }

    return results;
}

/**
 * 将带有后缀（如 K, M, B, T）的字符串转换为纯数字
 * @param {string} text - 输入的字符串，例如 "182.532M" 或 "3.794T"
 * @returns {number|string} - 解析后的数字或 "N/A"
 */
function parseSuffixedNumber(text) {
    if (!text || text === "--" || text === "N/A") return "N/A";
    let multiplier = 1;
    let numericPart = text.trim().toUpperCase();

    if (numericPart.endsWith("T")) {
        multiplier = 1e12;
        numericPart = numericPart.slice(0, -1);
    } else if (numericPart.endsWith("B")) {
        multiplier = 1e9;
        numericPart = numericPart.slice(0, -1);
    } else if (numericPart.endsWith("M")) {
        multiplier = 1e6;
        numericPart = numericPart.slice(0, -1);
    } else if (numericPart.endsWith("K")) {
        multiplier = 1e3;
        numericPart = numericPart.slice(0, -1);
    }

    const value = parseFloat(numericPart.replace(/,/g, ""));
    return isNaN(value) ? "N/A" : value * multiplier;
}

/**
 * 等待特定选择器的元素出现在页面上
 * @param {string} selector - CSS 选择器
 * @param {number} timeout - 超时时间（毫秒）
 * @returns {Promise<Element|null>}
 */
function waitForElement(selector, timeout = 15000) {
    return new Promise((resolve) => {
        const startTime = Date.now();
        const interval = setInterval(() => {
            const element = document.querySelector(selector);
            if (element) {
                clearInterval(interval);
                resolve(element);
            } else if (Date.now() - startTime > timeout) {
                clearInterval(interval);
                resolve(null);
            }
        }, 500);
    });
}