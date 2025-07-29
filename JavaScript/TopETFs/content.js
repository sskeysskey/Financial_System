// /Users/yanzhang/Documents/Financial_System/JavaScript/TopETFs/content.js

function normalizeVolume(raw) {
    if (!raw || typeof raw !== 'string') return '';
    let s = raw.trim().toUpperCase();
    let mul = 1;
    if (s.endsWith('B')) {
        mul = 1e9;
        s = s.slice(0, -1);
    } else if (s.endsWith('M')) {
        mul = 1e6;
        s = s.slice(0, -1);
    } else if (s.endsWith('K')) {
        mul = 1e3;
        s = s.slice(0, -1);
    }
    s = s.replace(/,/g, '');
    const n = parseFloat(s);
    if (isNaN(n)) return '';
    return Math.round(n * mul).toString();
}

const MAX_WAIT_TIME_TABLE = 30000; // 最大等待表格加载时间 (30秒)
const CHECK_INTERVAL_TABLE = 500;  // 检查表格是否存在的时间间隔 (每500毫秒)

// 封装表格查找逻辑
function findTargetTableAndHeaders() {
    let targetTable = null;
    let headerIndexMap = {};
    let headersFound = false;

    console.log("Yahoo ETF Scraper: content.js - Attempting to find the target table...");

    // 尝试1: 通过 data-testid="scr-res-table"
    const scrResTableDiv = document.querySelector('div[data-testid="scr-res-table"]');
    if (scrResTableDiv) {
        targetTable = scrResTableDiv.querySelector('table');
        if (targetTable) {
            console.log("Yahoo ETF Scraper: content.js - Table found via 'scr-res-table' data-testid.");
        }
    }

    // 尝试2: 通过 data-testid="top-etfs-table"
    if (!targetTable) {
        const topEtfsTableDiv = document.querySelector('div[data-testid="top-etfs-table"]');
        if (topEtfsTableDiv) {
            targetTable = topEtfsTableDiv.querySelector('table');
            if (targetTable) {
                console.log("Yahoo ETF Scraper: content.js - Table found via 'top-etfs-table' data-testid.");
            }
        }
    }

    // 尝试3: 通过表头文本匹配
    if (!targetTable) {
        console.log("Yahoo ETF Scraper: content.js - Table not found by data-testid, trying header content matching.");
        const tables = document.querySelectorAll('table');
        for (let table of tables) {
            const thElements = Array.from(table.querySelectorAll('thead th'));
            const headerTexts = thElements.map(th => th.textContent.trim().toLowerCase());
            const hasSymbolHeader = headerTexts.some(text => text.includes('symbol'));
            const hasNameHeader = headerTexts.some(text => text.includes('name'));
            const hasPriceHeader = headerTexts.some(text => text.includes('price')); // 增加价格表头检查
            const hasVolumeHeader = headerTexts.some(text => text.includes('volume')); // 增加成交量表头检查
            const hasBodyRows = table.querySelector('tbody tr');

            if (hasSymbolHeader && hasNameHeader && hasPriceHeader && hasVolumeHeader && hasBodyRows) {
                targetTable = table;
                console.log("Yahoo ETF Scraper: content.js - Target table found by flexible header text matching.");
                break;
            }
        }
    }

    // 尝试4: 查找页面上主要的、包含多行数据的表格 (W(100%) 类)
    if (!targetTable) {
        console.log("Yahoo ETF Scraper: content.js - Table still not found, trying class 'W(100%)' and row count.");
        const tables = document.querySelectorAll('table.W\\(100\\%\\)'); // 转义括号
        let potentialTable = null;
        if (tables.length === 1 && tables[0].querySelector('tbody tr')) {
            potentialTable = tables[0];
        } else if (tables.length > 0) {
            let maxRows = 0;
            tables.forEach(tbl => {
                const rowCount = tbl.querySelectorAll('tbody tr').length;
                if (rowCount > maxRows) {
                    maxRows = rowCount;
                    potentialTable = tbl;
                }
            });
        }
        // 确保选中的表格有足够的数据行，例如至少5-10行，避免选中小的辅助表格
        if (potentialTable && potentialTable.querySelectorAll('tbody tr').length > 5) {
            targetTable = potentialTable;
            console.log(`Yahoo ETF Scraper: content.js - Table found by 'W(100%)' class and significant row count.`);
        } else {
            console.log(`Yahoo ETF Scraper: content.js - 'W(100%)' table check did not yield a suitable table.`);
        }
    }

    if (targetTable) {
        // 获取表头并映射列名到索引
        const thElements = Array.from(targetTable.querySelectorAll('thead th'));
        thElements.forEach((th, index) => {
            const text = th.textContent.trim().toLowerCase();
            if (text.includes('symbol')) headerIndexMap.symbol = index;
            else if (text.includes('name')) headerIndexMap.name = index;
            else if (text.includes('price')) headerIndexMap.price = index;
            else if (text.includes('volume')) headerIndexMap.volume = index;
        });

        // 检查关键列是否都已映射
        if (headerIndexMap.symbol !== undefined && headerIndexMap.name !== undefined &&
            headerIndexMap.price !== undefined && headerIndexMap.volume !== undefined) {
            headersFound = true;
            console.log("Yahoo ETF Scraper: content.js - Header index map:", headerIndexMap);
        } else {
            console.warn("Yahoo ETF Scraper: content.js - Critical headers (symbol, name, price, volume) not fully mapped. Table might be found, but headers are problematic.", headerIndexMap);
            // 清空 targetTable 如果表头不完整，迫使重试或最终失败
            // targetTable = null; // 或者标记为 header_incomplete
        }
    }

    return { table: targetTable, headerMap: headerIndexMap, headersComplete: headersFound };
}


async function scrapeDataWhenReady(sendResponse) {
    console.log("Yahoo ETF Scraper: content.js - Starting to wait for target table and its headers...");
    let elapsedTime = 0;
    let tableSearchResult;

    while (elapsedTime < MAX_WAIT_TIME_TABLE) {
        tableSearchResult = findTargetTableAndHeaders();
        if (tableSearchResult.table && tableSearchResult.headersComplete) {
            console.log(`Yahoo ETF Scraper: content.js - Target table and complete headers found after ${elapsedTime}ms.`);
            break;
        }
        await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL_TABLE));
        elapsedTime += CHECK_INTERVAL_TABLE;
        console.log(`Yahoo ETF Scraper: content.js - Waiting for table/headers... ${elapsedTime}ms elapsed.`);
        if (!tableSearchResult.table) {
            console.log("Yahoo ETF Scraper: content.js - Table not yet found in this interval.");
        } else if (!tableSearchResult.headersComplete) {
            console.log("Yahoo ETF Scraper: content.js - Table found, but headers are incomplete or not as expected. Will re-check.");
        }
    }

    const { table: targetTable, headerMap: headerIndexMap, headersComplete } = tableSearchResult;

    if (!targetTable) {
        console.error(`Yahoo ETF Scraper: content.js - Target table could not be found on the page after ${MAX_WAIT_TIME_TABLE / 1000}s.`);
        sendResponse({ success: false, error: `Table not found on page after ${MAX_WAIT_TIME_TABLE / 1000}s.`, data: [] });
        return;
    }

    if (!headersComplete) {
        console.error("Yahoo ETF Scraper: content.js - Critical headers (symbol, name, price, volume) not found or mapped correctly even after waiting. Check table structure and header texts.", headerIndexMap);
        sendResponse({ success: false, error: "Critical headers not found/mapped in table.", data: [] });
        return;
    }

    console.log("Yahoo ETF Scraper: content.js - Target table identified:", targetTable);
    const results = [];
    const rows = targetTable.querySelectorAll('tbody tr');
    console.log(`Yahoo ETF Scraper: content.js - Found ${rows.length} rows in the table.`);

    rows.forEach((row, rowIndex) => {
        try {
            const cells = row.querySelectorAll('td');
            if (cells.length < Math.max(headerIndexMap.symbol, headerIndexMap.name, headerIndexMap.price, headerIndexMap.volume) + 1) {
                console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} has insufficient cells (${cells.length}), skipping.`);
                return;
            }

            let symbol = null, name = null, price = null, rawVol = null;

            // Symbol
            if (cells[headerIndexMap.symbol]) {
                const symbolLink = cells[headerIndexMap.symbol].querySelector('a[data-testid="table-cell-ticker"]');
                symbol = symbolLink ? symbolLink.textContent.trim() : cells[headerIndexMap.symbol].textContent.trim();
            } else {
                console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Symbol cell not found at index ${headerIndexMap.symbol}.`);
            }

            // Name
            if (cells[headerIndexMap.name]) {
                const nameDivWithTitle = cells[headerIndexMap.name].querySelector('div[title]');
                name = (nameDivWithTitle && nameDivWithTitle.getAttribute('title')) ? nameDivWithTitle.getAttribute('title').trim() : cells[headerIndexMap.name].textContent.trim();
            } else {
                console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Name cell not found at index ${headerIndexMap.name}.`);
            }

            // Price
            if (cells[headerIndexMap.price]) {
                const priceCell = cells[headerIndexMap.price];
                let priceStreamer = priceCell.querySelector('fin-streamer[data-field="regularMarketPrice"]');
                if (priceStreamer) {
                    price = (priceStreamer.hasAttribute('value') && priceStreamer.getAttribute('value').trim() !== "") ? priceStreamer.getAttribute('value').trim() : priceStreamer.textContent.trim();
                } else {
                    const cellText = priceCell.textContent.trim();
                    const priceMatch = cellText.match(/^[\d,]+\.?\d*/); // Improved regex to match numbers with commas and decimals
                    if (priceMatch) {
                        price = priceMatch[0].replace(/,/g, ''); // Remove commas before parsing
                    } else {
                        console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Could not extract price from cell content: '${cellText}' using fallback.`);
                        price = priceCell.textContent.trim().replace(/,/g, '');
                    }
                }
            } else {
                console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Price cell not found at index ${headerIndexMap.price}.`);
            }

            // Volume
            if (cells[headerIndexMap.volume]) {
                let vs = cells[headerIndexMap.volume].querySelector(
                    'fin-streamer[data-field="regularMarketVolume"], fin-streamer[data-field="volume"]'
                );
                if (vs && vs.hasAttribute('value') && vs.getAttribute('value').trim() !== "") {
                    rawVol = vs.getAttribute('value').trim();
                } else {
                    rawVol = cells[headerIndexMap.volume].textContent.trim();
                }
            } else {
                console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Volume cell not found at index ${headerIndexMap.volume}.`);
            }
            const volume = normalizeVolume(rawVol);

            if (symbol && name && price !== null && volume !== null) {
                results.push({ symbol, name, price, volume });
            } else {
                console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Missing data. Symbol: '${symbol}', Name: '${name}', Price: '${price}', RawVol: '${rawVol}' (Normalized Vol: '${volume}'). Skipping row.`);
            }
        } catch (e) {
            console.error(`Yahoo ETF Scraper: content.js - Error processing row ${rowIndex}:`, e, "Row HTML:", row.innerHTML);
        }
    });

    if (results.length > 0) {
        console.log(`Yahoo ETF Scraper: content.js - Successfully scraped ${results.length} ETFs from current page.`);
        sendResponse({ success: true, data: results });
    } else if (rows.length > 0 && results.length === 0) {
        console.warn(`Yahoo ETF Scraper: content.js - Found ${rows.length} rows, but scraped 0 ETFs. Check cell parsing logic or data format.`);
        sendResponse({ success: false, error: "Table rows found, but no data could be extracted.", data: [] });
    } else { // rows.length === 0
        console.warn(`Yahoo ETF Scraper: content.js - No data rows found in the table, although table structure was identified.`);
        sendResponse({ success: false, error: "Table found, but it contains no data rows.", data: [] });
    }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'scrapeYahooETFs') {
        console.log("Yahoo ETF Scraper: content.js - 'scrapeYahooETFs' action received for URL:", window.location.href);
        scrapeDataWhenReady(sendResponse);
        return true; // Crucial: Indicates that the response will be sent asynchronously.
    }
    // Optional: handle other messages or return false if not handling them asynchronously.
    // return true; // If you have other async message handlers.
});