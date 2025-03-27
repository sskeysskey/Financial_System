// Listen for messages from popup.js
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === "scrapeData") {
        const category = request.category;
        scrapeFinanceData(category).then(results => {
            sendResponse(results);
        }).catch(error => {
            console.error("Scraping error:", error);
            sendResponse([]);
        });
        return true; // Indicates async response
    }
});

async function scrapeFinanceData(category) {
    try {
        const results = [];

        // Wait for the table to load
        const waitForTable = () => {
            return new Promise((resolve, reject) => {
                let attempts = 0;
                const maxAttempts = 30;
                const checkInterval = 500; // 500ms

                const checkForTable = () => {
                    const rows = document.querySelectorAll("table tbody tr");
                    if (rows && rows.length > 0) {
                        resolve(rows);
                        return;
                    }

                    attempts++;
                    if (attempts >= maxAttempts) {
                        reject(new Error("Table loading timeout"));
                        return;
                    }

                    setTimeout(checkForTable, checkInterval);
                };

                checkForTable();
            });
        };

        // Try to wait for table and scrape data
        const rows = await waitForTable();
        console.log(`Found ${rows.length} rows in the table`);

        for (const row of rows) {
            try {
                // Get symbol - updated selector based on the HTML structure
                const symbolElement = row.querySelector("span.symbol");
                if (!symbolElement) {
                    console.log("No symbol element found in row");
                    continue;
                }
                const symbol = symbolElement.textContent.trim();
                console.log(`Found symbol: ${symbol}`);

                // Get market cap - finding the correct cell that contains market cap
                // Market cap is in the 10th cell (index 9) according to your HTML
                const cells = row.querySelectorAll("td");

                // Debug logging
                console.log(`Found ${cells.length} cells in row`);

                if (cells.length < 10) {
                    console.log("Not enough cells in row");
                    continue;
                }

                // Try to find the market cap cell (it's usually the 10th cell)
                let marketCapText = "";
                for (let i = 9; i < Math.min(12, cells.length); i++) {
                    const cellText = cells[i].textContent.trim();
                    // Check if this cell contains a value with T, B, or M suffix
                    if (/^\d+(\.\d+)?[TBM]$/.test(cellText)) {
                        marketCapText = cellText;
                        console.log(`Found market cap in cell ${i}: ${marketCapText}`);
                        break;
                    }
                }

                if (!marketCapText) {
                    console.log("No market cap found in row");
                    continue;
                }

                // Parse market cap
                const marketCap = parseMarketCap(marketCapText);
                console.log(`Parsed market cap: ${marketCap}`);

                // Only save if market cap >= 5,000,000,000 (5 billion)
                if (marketCap !== '--' && marketCap >= 5000000000) {
                    results.push({
                        symbol,
                        marketCap,
                        category
                    });
                    console.log(`Added to results: ${symbol}, ${marketCap}, ${category}`);
                } else {
                    console.log(`Skipped: Market cap ${marketCap} is less than 5 billion`);
                }
            } catch (e) {
                console.error("Error processing row:", e);
                continue;
            }
        }

        console.log(`Total results: ${results.length}`);
        return results;

    } catch (error) {
        console.error("Error scraping data:", error);
        return [];
    }
}

function parseMarketCap(text) {
    if (text === '--' || text === '-' || text === '') {
        return '--';
    }

    let multiplier = 1;
    let cleanText = text.trim();

    if (cleanText.includes('T')) {
        multiplier = 1e12;
        cleanText = cleanText.replace('T', '');
    } else if (cleanText.includes('B')) {
        multiplier = 1e9;
        cleanText = cleanText.replace('B', '');
    } else if (cleanText.includes('M')) {
        multiplier = 1e6;
        cleanText = cleanText.replace('M', '');
    }

    return parseFloat(cleanText.replace(/,/g, '')) * multiplier;
}