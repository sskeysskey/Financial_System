// content.js
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === "scrapeData") {
        scrapeFinanceData(request.category)
            .then(response => sendResponse(response)) // 直接转发结构化响应
            .catch(err => {
                console.error("Scraping failed with unexpected error:", err);
                // 捕获意外错误，并发送一个结构化的错误响应
                sendResponse({
                    success: false,
                    data: [],
                    message: `An unexpected error occurred: ${err.message}`
                });
            });
        return true; // 保持通道开放以进行异步响应
    }
});

/**
 * 从Yahoo Finance的screener页面抓取数据 (已更新以适应新版页面并返回详细结果)
 * @param {string} category - 股票分类
 * @returns {Promise<object>} - 返回一个包含 {success, data, message} 的对象
 */
async function scrapeFinanceData(category) {
    // 1. 等待新版表格加载完成
    // 我们等待包含 data-testid="screener-table" 的 div 出现，这比单纯等 table 元素更可靠
    const tableContainer = await waitForElement("div[data-testid='screener-table']");
    if (!tableContainer) {
        const errorMsg = "抓取失败: 未在页面上找到数据表格容器。可能是页面未完全加载或结构已再次改变。";
        console.error(errorMsg);
        return { success: false, data: [], message: errorMsg };
    }

    const table = tableContainer.querySelector('table');
    if (!table) {
        const errorMsg = "抓取失败: 在容器内未找到 <table> 元素。";
        console.error(errorMsg);
        return { success: false, data: [], message: errorMsg };
    }

    const results = [];
    let skippedRowsCount = 0; // 记录因数据不完整而被跳过的行数

    // 2. 遍历表格的每一行
    // 新的行选择器使用 data-testid，更加稳定
    const rows = table.querySelectorAll("tbody tr[data-testid='data-table-v2-row']");
    if (rows.length === 0) {
        const warnMsg = "警告: 找到了表格，但表格内没有数据行。";
        console.warn(warnMsg);
        return { success: true, data: [], message: warnMsg };
    }

    for (const row of rows) {
        try {
            // 3. 使用 data-testid 直接从单元格中提取数据

            // 提取 Symbol (股票代码)
            const symbolEl = row.querySelector('a[data-testid="table-cell-ticker"] span.symbol');
            const symbol = symbolEl ? symbolEl.textContent.trim() : null;

            if (!symbol) {
                skippedRowsCount++;
                console.warn("跳过一行: 未找到股票代码(Symbol)。", row);
                continue;
            }

            // ---------------------------------------------------------
            // 提取 Price (价格) - [这里是修改的地方]
            // ---------------------------------------------------------
            const priceText = row.querySelector('td[data-testid-cell="intradayprice"]')?.textContent.trim();
            // 如果取到的文本是 "--" 或空，则设为 "N/A"，否则去除逗号后转浮点数
            const price = (priceText && priceText !== "--")
                ? parseFloat(priceText.replace(/,/g, ''))
                : "N/A";


            // 提取 Market Cap (市值)
            const marketCapText = row.querySelector('td[data-testid-cell="intradaymarketcap"]')?.textContent.trim() || "--";
            const marketCap = parseSuffixedNumber(marketCapText);

            // 提取 Volume (成交量)
            const volumeText = row.querySelector('td[data-testid-cell="dayvolume"]')?.textContent.trim() || "--";
            const volume = parseSuffixedNumber(volumeText);

            // 检查关键数据是否存在
            if (typeof marketCap !== "number" || isNaN(marketCap)) {
                skippedRowsCount++;
                console.warn(`跳过股票 ${symbol}: 市值(MarketCap)数据缺失或无效。 值为: '${marketCapText}'`);
                continue;
            }

            results.push({
                symbol,
                marketCap,
                category,
                price,
                volume
            });

        } catch (e) {
            skippedRowsCount++;
            console.error("处理某一行时出错:", e, row);
        }
    }

    let message = `成功抓取 ${results.length} 条记录。`;
    if (skippedRowsCount > 0) {
        message += ` 因数据不完整或错误跳过了 ${skippedRowsCount} 行。`;
    }

    return { success: true, data: results, message: message };
}

/**
 * 将带有后缀（如 K, M, B, T）的字符串转换为纯数字
 * @param {string} text - 输入的字符串，例如 "182.532M" 或 "4.403T"
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
                console.error(`Timeout waiting for element with selector: ${selector}`);
                resolve(null);
            }
        }, 500);
    });
}