chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'scrapeYahooETFs') {
        console.log("Yahoo ETF Scraper: content.js - 'scrapeYahooETFs' action received for URL:", window.location.href);
        try {
            const results = [];
            let targetTable = null;

            // --- 更稳健的表格选择逻辑 ---
            console.log("Yahoo ETF Scraper: content.js - Attempting to find the target table...");

            // 优先尝试1: 通过更具体的 data-testid (如果存在)
            // Yahoo Finance 列表格通常在 <div data-testid="scr-res-table"> 下
            const scrResTableDiv = document.querySelector('div[data-testid="scr-res-table"]');
            if (scrResTableDiv) {
                targetTable = scrResTableDiv.querySelector('table');
                if (targetTable) {
                    console.log("Yahoo ETF Scraper: content.js - Table found via 'scr-res-table' data-testid.");
                }
            }

            // 尝试2: 通过 'top-etfs-table' data-testid (之前的尝试)
            if (!targetTable) {
                const topEtfsTableDiv = document.querySelector('div[data-testid="top-etfs-table"]');
                if (topEtfsTableDiv) {
                    targetTable = topEtfsTableDiv.querySelector('table');
                    if (targetTable) {
                        console.log("Yahoo ETF Scraper: content.js - Table found via 'top-etfs-table' data-testid.");
                    }
                }
            }

            // 尝试3: 查找包含特定表头文本的表格 (更灵活的文本匹配)
            if (!targetTable) {
                console.log("Yahoo ETF Scraper: content.js - Table not found by data-testid, trying header content matching.");
                const tables = document.querySelectorAll('table');
                for (let table of tables) {
                    const headers = Array.from(table.querySelectorAll('thead th'));
                    const headerTexts = headers.map(th => th.textContent.trim().toLowerCase());

                    // 检查是否包含 "symbol" 和 "name" (不区分大小写)
                    const hasSymbolHeader = headerTexts.some(text => text.includes('symbol'));
                    const hasNameHeader = headerTexts.some(text => text.includes('name'));
                    const hasPriceHeader = headerTexts.some(text => text.includes('price')); // 可选，增加确定性
                    const hasBodyRows = table.querySelector('tbody tr');

                    if (hasSymbolHeader && hasNameHeader && hasPriceHeader && hasBodyRows) {
                        targetTable = table;
                        console.log("Yahoo ETF Scraper: content.js - Target table found by flexible header text matching.");
                        break;
                    }
                }
            }

            // 尝试4: 查找页面上主要的、包含多行数据的表格 (作为最后的备选)
            // 这个选择器 W(100%) 是 Yahoo Finance 中常见的表格宽度类，但仍需谨慎
            if (!targetTable) {
                console.log("Yahoo ETF Scraper: content.js - Table still not found, trying class 'W(100%)' and row count.");
                const tables = document.querySelectorAll('table.W\\(100\\%\\)'); // 需要转义括号
                if (tables.length === 1 && tables[0].querySelector('tbody tr')) { // 如果页面只有一个这样的主表格
                    targetTable = tables[0];
                    console.log("Yahoo ETF Scraper: content.js - Table found by single 'W(100%)' class.");
                } else if (tables.length > 0) { // 如果有多个，选包含最多数据行的那个
                    let maxRows = 0;
                    let potentialTable = null;
                    tables.forEach(tbl => {
                        const rowCount = tbl.querySelectorAll('tbody tr').length;
                        if (rowCount > maxRows) {
                            maxRows = rowCount;
                            potentialTable = tbl;
                        }
                    });
                    if (potentialTable && maxRows > 0) { // 至少要有一行数据
                        targetTable = potentialTable;
                        console.log(`Yahoo ETF Scraper: content.js - Table found by 'W(100%)' class and max rows (${maxRows}).`);
                    }
                }
            }


            if (targetTable) {
                console.log("Yahoo ETF Scraper: content.js - Target table identified:", targetTable);
                const rows = targetTable.querySelectorAll('tbody tr');
                console.log(`Yahoo ETF Scraper: content.js - Found ${rows.length} rows in the table.`);

                rows.forEach((row, rowIndex) => {
                    try {
                        const cells = row.querySelectorAll('td');
                        if (cells.length === 0) {
                            // console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} has no cells, skipping.`);
                            return;
                        }

                        let symbol = null, name = null, price = null, volume = null;

                        // --- 数据提取逻辑 (使用 aria-label 辅助定位，如果存在) ---
                        // Symbol (通常在第一列)
                        const symbolCell = row.querySelector('td[aria-label="Symbol"]') || cells[0];
                        if (symbolCell) {
                            const symbolLink = symbolCell.querySelector('a[data-testid="table-cell-ticker"]');
                            if (symbolLink) {
                                const symbolSpan = symbolLink.querySelector('span.symbol');
                                symbol = symbolSpan ? symbolSpan.textContent.trim() : symbolLink.textContent.trim();
                            } else { // 如果没有链接，直接取单元格文本
                                symbol = symbolCell.textContent.trim();
                            }
                        }

                        // Name (通常在第二列)
                        const nameCell = row.querySelector('td[aria-label="Name"]') || cells[1];
                        if (nameCell) {
                            const nameDiv = nameCell.querySelector('div[title]');
                            name = nameDiv ? nameDiv.getAttribute('title').trim() : nameCell.textContent.trim();
                        }

                        // Price (查找包含 fin-streamer[data-field="regularMarketPrice"])
                        // 遍历所有单元格，直到找到包含价格的 fin-streamer
                        for (let i = 0; i < cells.length; i++) {
                            const priceStreamer = cells[i].querySelector('fin-streamer[data-field="regularMarketPrice"]');
                            if (priceStreamer) {
                                price = priceStreamer.getAttribute('data-value');
                                break;
                            }
                        }

                        // Volume (查找包含 fin-streamer[data-field="regularMarketVolume"])
                        for (let i = 0; i < cells.length; i++) {
                            const volumeStreamer = cells[i].querySelector('fin-streamer[data-field="regularMarketVolume"]');
                            if (volumeStreamer) {
                                volume = volumeStreamer.getAttribute('data-value');
                                break;
                            }
                        }

                        if (volume) {
                            volume = volume.replace(/,/g, '');
                        }

                        // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex}: Symbol='${symbol}', Name='${name}', Price='${price}', Volume='${volume}'`);

                        if (symbol && name && price && volume) {
                            results.push({ symbol, name, price, volume });
                        } else {
                            // console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex}: Missing some data. S:${symbol}, N:${name}, P:${price}, V:${volume}`);
                        }
                    } catch (e) {
                        console.error(`Yahoo ETF Scraper: content.js - Error processing row ${rowIndex}:`, e, row.innerHTML);
                    }
                });
                console.log(`Yahoo ETF Scraper: content.js - Successfully processed ${results.length} ETFs from this page.`);
                sendResponse({ success: true, data: results });
            } else {
                console.error("Yahoo ETF Scraper: content.js - Target table NOT found after all attempts for URL:", window.location.href);
                sendResponse({ success: false, error: 'Could not find the target ETF table on the page.' });
            }
        } catch (error) {
            console.error('Yahoo ETF Scraper: content.js - Critical error in scrapeYahooETFs:', error);
            sendResponse({ success: false, error: error.message });
        }
        return true;
    }
});