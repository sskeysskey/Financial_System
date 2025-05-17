chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'scrapeYahooETFs') {
        console.log("Yahoo ETF Scraper: content.js - 'scrapeYahooETFs' action received.");
        try {
            const results = [];
            let targetTable = null;

            // 尝试使用 data-testid 查找表格，这通常比较稳定
            // Yahoo Finance 的 ETF 列表格外面可能有一个 <div data-testid="top-etfs-table">
            const testIdTableContainer = document.querySelector('div[data-testid="top-etfs-table"]');
            if (testIdTableContainer) {
                targetTable = testIdTableContainer.querySelector('table');
            }

            // 如果通过 data-testid 没找到，尝试更通用的表格选择器
            if (!targetTable) {
                console.log("Yahoo ETF Scraper: content.js - Table not found by data-testid, trying fallback selectors.");
                // 查找页面上所有可能的表格，然后根据表头内容进一步筛选
                const tables = document.querySelectorAll('table');
                for (let table of tables) {
                    const symbolHeader = table.querySelector('thead th[aria-label="Symbol"], thead th[data-field="symbol"], thead th div[data-column-name="symbol"]'); // 查找Symbol列头
                    const nameHeader = table.querySelector('thead th[aria-label="Name"], thead th[data-field="longName"], thead th div[data-column-name="name"]'); // 查找Name列头
                    const hasBodyRows = table.querySelector('tbody tr');
                    if (symbolHeader && nameHeader && hasBodyRows) {
                        targetTable = table;
                        console.log("Yahoo ETF Scraper: content.js - Target table found by header content.");
                        break;
                    }
                }
            }

            // 最后的通用回退：查找一个包含很多数据行的表格
            if (!targetTable) {
                console.log("Yahoo ETF Scraper: content.js - Table still not found, trying generic row count fallback.");
                const allTables = document.querySelectorAll('table');
                for (let tbl of allTables) {
                    if (tbl.querySelector('thead') && tbl.querySelectorAll('tbody tr').length > 5) { // 假设ETF列表至少有几行
                        targetTable = tbl;
                        console.log("Yahoo ETF Scraper: content.js - Target table found by generic row count.");
                        break;
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
                        // 根据您提供的HTML片段，Symbol, Name, Price, Volume 分别在不同列
                        // 需要确保有足够的列来避免错误
                        if (cells.length < 7) { // 假设至少需要7列才能覆盖到Volume (Symbol, Name, ., Price, Chg, %Chg, Volume)
                            // console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} has only ${cells.length} cells, skipping.`);
                            return;
                        }

                        let symbol = null, name = null, price = null, volume = null;

                        // 1. Symbol (第一列: cells[0])
                        //    <a data-testid="table-cell-ticker">...<span class="symbol yf-5ogvqh">BLOK</span>...</a>
                        const symbolLink = cells[0] ? cells[0].querySelector('a[data-testid="table-cell-ticker"]') : null;
                        if (symbolLink) {
                            const symbolSpan = symbolLink.querySelector('span.symbol'); // 更精确地定位 symbol span
                            symbol = symbolSpan ? symbolSpan.textContent.trim() : symbolLink.textContent.trim(); // 如果没有span.symbol，尝试整个链接文本
                        } else if (cells[0]) {
                            symbol = cells[0].textContent.trim(); // 最后的备选
                        }


                        // 2. Name (第二列: cells[1])
                        //    <div title="Amplify Transformational Data Sharing ETF"...>...</div>
                        const nameDiv = cells[1] ? cells[1].querySelector('div[title]') : null; // 查找有title属性的div
                        if (nameDiv) {
                            name = nameDiv.getAttribute('title').trim();
                        } else if (cells[1]) {
                            name = cells[1].textContent.trim(); // 如果没有div[title]，取单元格文本
                        }

                        // 3. Price (第四列: cells[3], 因为第三列是 '•')
                        //    <fin-streamer data-field="regularMarketPrice" data-value="47.91"...>
                        const priceStreamerCell = cells[3] ? cells[3].querySelector('fin-streamer[data-field="regularMarketPrice"]') : null;
                        if (priceStreamerCell) {
                            price = priceStreamerCell.getAttribute('data-value');
                        } else if (cells[3]) { // 如果没有fin-streamer，尝试直接取单元格内容（不太可能）
                            price = cells[3].textContent.trim();
                        }
                        // 如果cells[3]中没找到，尝试cells[2] （以防列结构略有不同）
                        if (!price && cells[2]) {
                            const priceStreamerCellFallback = cells[2].querySelector('fin-streamer[data-field="regularMarketPrice"]');
                            if (priceStreamerCellFallback) {
                                price = priceStreamerCellFallback.getAttribute('data-value');
                            }
                        }


                        // 4. Volume (第七列: cells[6])
                        //    <fin-streamer data-field="regularMarketVolume" data-value="321151"...>
                        const volumeStreamerCell = cells[6] ? cells[6].querySelector('fin-streamer[data-field="regularMarketVolume"]') : null;
                        if (volumeStreamerCell) {
                            volume = volumeStreamerCell.getAttribute('data-value');
                        } else if (cells[6]) {
                            volume = cells[6].textContent.trim();
                        }
                        // 如果cells[6]中没找到，尝试cells[5]
                        if (!volume && cells[5]) {
                            const volumeStreamerCellFallback = cells[5].querySelector('fin-streamer[data-field="regularMarketVolume"]');
                            if (volumeStreamerCellFallback) {
                                volume = volumeStreamerCellFallback.getAttribute('data-value');
                            }
                        }


                        if (volume) {
                            volume = volume.replace(/,/g, ''); // 去除逗号
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
                console.error("Yahoo ETF Scraper: content.js - Target table NOT found after all attempts.");
                sendResponse({ success: false, error: 'Could not find the target ETF table on the page.' });
            }
        } catch (error) {
            console.error('Yahoo ETF Scraper: content.js - Critical error in scrapeYahooETFs:', error);
            sendResponse({ success: false, error: error.message });
        }
        return true; // 异步发送响应时必须返回 true
    }
});