// content.js
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === "scrapeData") {
        scrapeFinanceData(request.category)
            .then(results => sendResponse(results))
            .catch(err => {
                console.error(err);
                sendResponse([]);
            });
        return true; // async
    }
});

async function scrapeFinanceData(category) {
    const results = [];

    // 等待表格加载
    const waitForTable = () => new Promise((resolve, reject) => {
        let attempts = 0, maxAttempts = 30;
        const check = () => {
            const rows = document.querySelectorAll("table tbody tr");
            if (rows.length > 0) return resolve(rows);
            if (++attempts >= maxAttempts) return reject(new Error("Table loading timeout"));
            setTimeout(check, 500);
        };
        check();
    });

    const rows = await waitForTable();
    for (const row of rows) {
        try {
            // 1) 抓 symbol
            const symEl = row.querySelector("span.symbol");
            if (!symEl) continue;
            const symbol = symEl.textContent.trim();

            // 2) 抓 price
            const priceEl = row.querySelector('fin-streamer[data-field="regularMarketPrice"]');
            const price = priceEl
                ? parseFloat(priceEl.getAttribute("data-value"))
                : "--";

            // 3) 抓所有 td
            const cells = row.querySelectorAll("td");

            // 4) 抓 volume （假设是第 8 个 td，索引 7）
            const volumeText = cells[7]?.textContent.trim() || "";
            const volume = volumeText
                ? parseMarketCap(volumeText)
                : "--";

            // 5) 抓 marketCap（已有逻辑，略微调整后缀支持）
            let marketCapText = "";
            for (let i = 9; i < Math.min(12, cells.length); i++) {
                const t = cells[i].textContent.trim();
                if (/^\d+(\.\d+)?[TBMK]$/.test(t)) { marketCapText = t; break; }
            }
            if (!marketCapText) continue;
            const marketCap = parseMarketCap(marketCapText);

            // 只要有数值型市值就收集
            if (typeof marketCap === "number" && !isNaN(marketCap)) {
                results.push({ symbol, marketCap, category, price, volume });
            }
        } catch (e) {
            console.error("row error:", e);
        }
    }

    return results;
}

// 将带后缀的字符串转成纯数字
function parseMarketCap(text) {
    if (!text || text === "--") return NaN;
    let m = 1;
    let s = text.trim().toUpperCase();
    if (s.endsWith("T")) { m = 1e12; s = s.slice(0, -1); }
    else if (s.endsWith("B")) { m = 1e9; s = s.slice(0, -1); }
    else if (s.endsWith("M")) { m = 1e6; s = s.slice(0, -1); }
    else if (s.endsWith("K")) { m = 1e3; s = s.slice(0, -1); }
    return parseFloat(s.replace(/,/g, "")) * m;
}