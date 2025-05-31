chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'scrapeYahooETFs') {
        console.log("Yahoo ETF Scraper: content.js - 'scrapeYahooETFs' action received for URL:", window.location.href);
        try {
            const results = [];
            let targetTable = null;
            let headerIndexMap = {}; // To store column indices by header name

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

                // --- 获取表头并映射列名到索引 ---
                const headers = Array.from(targetTable.querySelectorAll('thead th'));
                headers.forEach((th, index) => {
                    const text = th.textContent.trim().toLowerCase();
                    // 我们需要更灵活地匹配，因为表头文本可能会变化
                    if (text.includes('symbol')) headerIndexMap.symbol = index;
                    else if (text.includes('name')) headerIndexMap.name = index;
                    // "price (intraday)" 或 "price"
                    else if (text.includes('price')) headerIndexMap.price = index;
                    else if (text.includes('volume')) headerIndexMap.volume = index;
                    // 你可以根据需要添加更多列的映射
                });

                console.log("Yahoo ETF Scraper: content.js - Header index map:", headerIndexMap);

                // 检查关键列是否都已映射，如果某些列的表头找不到，则提取会失败
                if (headerIndexMap.symbol === undefined || headerIndexMap.name === undefined || headerIndexMap.price === undefined || headerIndexMap.volume === undefined) {
                    console.error("Yahoo ETF Scraper: content.js - Critical headers (symbol, name, price, volume) not found or mapped. Check table structure and header texts.");
                    sendResponse({ success: false, error: "Critical headers not found in table.", data: [] });
                    return true; // 确保异步响应被发送
                }


                const rows = targetTable.querySelectorAll('tbody tr');
                console.log(`Yahoo ETF Scraper: content.js - Found ${rows.length} rows in the table.`);

                rows.forEach((row, rowIndex) => {
                    try {
                        const cells = row.querySelectorAll('td');
                        if (cells.length === 0) {
                            console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} has no cells, skipping.`);
                            return;
                        }

                        let symbol = null, name = null, price = null, volume = null;

                        // --- 新的数据提取逻辑 ---

                        // Symbol
                        if (cells[headerIndexMap.symbol]) {
                            // 尝试更具体的选择器，如果存在的话
                            const symbolLink = cells[headerIndexMap.symbol].querySelector('a[data-testid="table-cell-ticker"]');
                            if (symbolLink) {
                                symbol = symbolLink.textContent.trim();
                            } else {
                                symbol = cells[headerIndexMap.symbol].textContent.trim();
                            }
                            // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Raw Symbol Cell Content:`, cells[headerIndexMap.symbol].innerHTML);
                            // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Extracted Symbol:`, symbol);
                        } else {
                            console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Symbol cell not found using index ${headerIndexMap.symbol}.`);
                        }

                        // Name
                        if (cells[headerIndexMap.name]) {
                            // 雅虎财经的名称有时在 title 属性中，有时直接是文本
                            const nameDivWithTitle = cells[headerIndexMap.name].querySelector('div[title]');
                            if (nameDivWithTitle && nameDivWithTitle.getAttribute('title')) {
                                name = nameDivWithTitle.getAttribute('title').trim();
                            } else {
                                name = cells[headerIndexMap.name].textContent.trim();
                            }
                            // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Raw Name Cell Content:`, cells[headerIndexMap.name].innerHTML);
                            // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Extracted Name:`, name);
                        } else {
                            console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Name cell not found using index ${headerIndexMap.name}.`);
                        }

                        // Price
                        // 页面上的价格通常是动态加载的，但如果结构改变，我们需要直接从DOM中获取
                        // 你的HTML片段显示价格是 "105.63"
                        if (cells[headerIndexMap.price]) {
                            const priceCell = cells[headerIndexMap.price];
                            // 优先尝试从具有特定 data-field 的 fin-streamer 获取 value
                            let priceStreamer = priceCell.querySelector('fin-streamer[data-field="regularMarketPrice"]');
                            if (priceStreamer) {
                                if (priceStreamer.hasAttribute('value') && priceStreamer.getAttribute('value').trim() !== "") {
                                    price = priceStreamer.getAttribute('value').trim();
                                } else {
                                    // 如果 value 属性为空或不存在，则取该 fin-streamer 的 textContent
                                    price = priceStreamer.textContent.trim();
                                }
                            } else {
                                // 如果找不到特定的 fin-streamer，尝试获取单元格内第一个看起来像数字的文本
                                // 这通常是价格本身，避免获取到后面的变化量和百分比
                                const cellText = priceCell.textContent.trim();
                                // 正则表达式匹配开头的数字 (可能包含小数点)
                                const priceMatch = cellText.match(/^[\d\.]+/);
                                if (priceMatch) {
                                    price = priceMatch[0];
                                } else {
                                    // 如果还是没匹配到，记录警告，price 将为 null
                                    console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Could not extract price from cell content: '${cellText}' using fallback.`);
                                    price = priceCell.textContent.trim(); // 作为最后的手段，取全部内容，但通常不应到这一步
                                }
                            }
                            // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Raw Price Cell Content:`, priceCell.innerHTML);
                            // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Extracted Price:`, price);
                        } else {
                            console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Price cell not found using index ${headerIndexMap.price}.`);
                        }


                        // Volume
                        // 页面上的成交量也是动态的
                        // 你的HTML片段显示成交量是 "2.327M"
                        if (cells[headerIndexMap.volume]) {
                            // 尝试查找 fin-streamer (旧逻辑)
                            let volumeStreamer = cells[headerIndexMap.volume].querySelector('fin-streamer[data-field="regularMarketVolume"], fin-streamer[data-field="volume"]');
                            if (volumeStreamer && volumeStreamer.hasAttribute('value') && volumeStreamer.getAttribute('value').trim() !== "") {
                                volume = volumeStreamer.getAttribute('value').trim();
                            } else { // 直接取单元格文本
                                volume = cells[headerIndexMap.volume].textContent.trim();
                            }
                            // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Raw Volume Cell Content:`, cells[headerIndexMap.volume].innerHTML);
                            // console.log(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Extracted Volume:`, volume);
                        } else {
                            console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Volume cell not found using index ${headerIndexMap.volume}.`);
                        }


                        if (symbol && name && price !== null && volume !== null) { // price 和 volume 可以是 0
                            results.push({ symbol, name, price, volume });
                        } else {
                            console.warn(`Yahoo ETF Scraper: content.js - Row ${rowIndex} - Missing data, skipping. Symbol: ${symbol}, Name: ${name}, Price: ${price}, Volume: ${volume}`);
                        }

                    } catch (e) {
                        console.error(`Yahoo ETF Scraper: content.js - Error processing row ${rowIndex}:`, e, "Row HTML:", row.innerHTML);
                    }
                });

                console.log(`Yahoo ETF Scraper: content.js - Successfully scraped ${results.length} ETFs from current page.`);
                sendResponse({ success: true, data: results });

            } else {
                console.error("Yahoo ETF Scraper: content.js - Target table could not be found on the page.");
                sendResponse({ success: false, error: "Table not found on page.", data: [] });
            }
        } catch (error) {
            console.error("Yahoo ETF Scraper: content.js - Error in 'scrapeYahooETFs' message handler:", error);
            sendResponse({ success: false, error: error.message, data: [] });
        }
        return true; // Indicate that the response will be sent asynchronously
    }
});