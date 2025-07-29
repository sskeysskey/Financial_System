// 五个任务：每个任务定义 name、urls、scraper（注入到页面的函数）、filename
const tasks = [
    {
        name: 'Bonds',
        urls: [
            'https://tradingeconomics.com/united-states/government-bond-yield',
            'https://tradingeconomics.com/bonds'
        ],
        // 抓取函数：在页面 context 执行，返回 [{name, price}, …]
        scraper: (allUrls, thisUrl) => {
            const results = [];
            if (thisUrl.includes('united-states/government-bond-yield')) {
                // US 2Y 示例
                const links = Array.from(document.querySelectorAll('a'))
                    .filter(a => a.textContent.trim() === 'US 2Y');
                links.forEach(link => {
                    const tr = link.closest('tr');
                    const p = tr?.querySelector('#p');
                    if (p) results.push({ name: 'US2Y', price: p.textContent.trim() });
                });
            } else {
                // 其它五国十年期
                const map = {
                    "United Kingdom": "UK10Y",
                    "Japan": "JP10Y",
                    "Brazil": "BR10Y",
                    "India": "IND10Y",
                    "Turkey": "TUR10Y"
                };
                Array.from(document.querySelectorAll('a b')).forEach(b => {
                    const country = b.textContent.trim();
                    if (map[country]) {
                        const tr = b.closest('tr');
                        const p = tr?.querySelector('#p');
                        if (p) results.push({ name: map[country], price: p.textContent.trim() });
                    }
                });
            }
            // —— 去重 —— 
            const seen = new Set();
            return results.filter(item => {
                if (seen.has(item.name)) return false;
                seen.add(item.name);
                return true;
            });
        },
        filename: () => `bonds_${today()}.csv`
    },
    {
        name: 'Commodities',
        urls: [
            'https://tradingeconomics.com/commodity/baltic',
            'https://tradingeconomics.com/commodities'
        ],
        scraper: ([], thisUrl) => {
            const out = [];
            const date = null; // 由 background 填充
            if (thisUrl.includes('/commodity/baltic')) {
                const td = document.querySelector('table tr td:nth-child(2)');
                if (td) {
                    const raw = td.textContent.trim();          // e.g. "1,340.00"
                    const price = raw.replace(/,/g, '');        // 变成 "1340.00"
                    out.push({ name: 'BalticDry', price });
                }
            } else {
                // commodity 列表示例
                const list = ["Coal", "Uranium", "Steel", "Lithium", "Wheat", "Palm Oil", "Aluminum",
                    "Nickel", "Tin", "Zinc", "Palladium", "Poultry", "Salmon", "Iron Ore", "Orange Juice"];
                list.forEach(c => {
                    const a = Array.from(document.querySelectorAll('a'))
                        .find(x => x.textContent.includes(c) && x.href.includes('/commodity/'));
                    const tr = a?.closest('tr');
                    const td = tr?.querySelector('td#p');
                    if (td) out.push({ name: c.replace(' ', ''), price: td.textContent.trim() });
                });
            }
            return out;
        },
        filename: () => `commodities_${today()}.csv`
    },
    {
        name: 'Currencies',
        urls: ['https://tradingeconomics.com/currencies?base=cny'],
        scraper: ([], thisUrl) => {
            const targets = ["CNYARS", "CNYINR", "CNYKRW", "CNYMXN", "CNYRUB", "CNYSGD",
                "CNYBRL", "CNYPHP", "CNYIDR", "CNYEGP", "CNYTHB", "CNYIRR"];
            const out = [];
            targets.forEach(code => {
                let a = document.querySelector(`a[href*="${code.toLowerCase()}"]`);
                if (!a) a = Array.from(document.querySelectorAll('a'))
                    .find(x => x.textContent.trim() === code);
                const tr = a?.closest('tr');
                const p = tr?.querySelector('#p') || tr?.querySelector('.datatable-item');
                if (p) out.push({ name: code, price: p.textContent.trim() });
            });
            return out;
        },
        filename: () => `currencies_${today()}.csv`
    },
    {
        name: 'Economics',
        urls: ['https://tradingeconomics.com/united-states/indicators'],
        scraper: (allUrls, thisUrl) => {
            // “指标名称 → CSV 中的字段名” 映射
            const map = {
                "GDP Growth Rate": "USGDP",
                "Non Farm Payrolls": "USNonFarm",
                "Inflation Rate": "USCPI",
                "Interest Rate": "USInterest",
                "Balance of Trade": "USTrade",
                "Consumer Confidence": "USConfidence",
                "Retail Sales MoM": "USRetailM",
                "Unemployment Rate": "USUnemploy",
                "Non Manufacturing PMI": "USNonPMI",
                "Initial Jobless Claims": "USInitial",
                "ADP Employment Change": "USNonFarmA",
                "Core PCE Price Index Annual Change": "CorePCEY",
                "Core PCE Price Index MoM": "CorePCEM",
                "Core Inflation Rate": "CoreCPI",
                "Producer Prices Change": "USPPI",
                "Core Producer Prices YoY": "CorePPI",
                "PCE Price Index Annual Change": "PCEY",
                "Import Prices MoM": "ImportPriceM",
                "Import Prices YoY": "ImportPriceY",
                "Real Consumer Spending": "USConspending"
            };
            const out = [];
            // 遍历所有第一列
            document.querySelectorAll('td:first-child').forEach(td => {
                const key = td.textContent.trim();
                if (map[key]) {
                    const vtd = td.nextElementSibling;
                    if (vtd) {
                        out.push({
                            name: map[key],
                            price: vtd.textContent.trim()
                        });
                    }
                }
            });
            return out;
        },
        filename: () => `economics_${today()}.csv`
    },
    {
        name: 'Indices',
        urls: ['https://tradingeconomics.com/stocks'],
        scraper: ([], thisUrl) => {
            // 示例只抓 MOEX → Russia
            const out = [];
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'MOEX');
            const tr = link?.closest('tr');
            const p = tr?.querySelector('#p');
            if (p) out.push({ name: 'Russia', price: p.textContent.trim() });
            return out;
        },
        filename: () => `indices_${today()}.csv`
    }
];

// 工具函数
function today() {
    return new Date().toISOString().split('T')[0];
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// 给 popup 发日志
function log(text, status = 'info') {
    chrome.runtime.sendMessage({ type: 'log', text, status });
}

// 把一批 {name,price} 生成 CSV 并下载
async function downloadCSV(rows, filename) {
    const header = 'date,name,price,category\n';
    const date = today();
    const csv = header + rows.map(r => `${date},${r.name},${r.price},${r.category}`).join('\n');
    const url = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    await chrome.downloads.download({ url, filename, conflictAction: 'uniquify', saveAs: false });
}

// 主流程
async function runAll() {
    log('开始所有任务', 'info');
    // 新建一个隐身标签
    let tab = await chrome.tabs.create({ url: 'about:blank', active: false });

    for (const task of tasks) {
        log(`→ 任务 [${task.name}]`, 'info');
        let all = [];
        for (const url of task.urls) {
            log(`加载 ${url}`, 'info');
            await chrome.tabs.update(tab.id, { url });
            await sleep(3000);
            let [res] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: task.scraper,
                args: [task.urls, url]
            });
            if (res && Array.isArray(res.result)) {
                res.result.forEach(r => r.category = task.name);
                all = all.concat(res.result);
                log(`  抓取到 ${res.result.length} 条`, 'success');
            } else {
                log(`  抓取失败或无数据`, 'error');
            }
        }
        if (all.length > 0) {
            const fname = task.filename();
            log(`  生成并下载 ${fname}`, 'info');
            await downloadCSV(all, fname);
            log(`  下载完成`, 'success');
        } else {
            log(`  无数据跳过下载`, 'error');
        }
    }

    // 关闭标签
    chrome.tabs.remove(tab.id);
    log('所有任务执行完毕', 'success');
}

// 监听 popup 的启动命令
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === 'startAll') {
        runAll();
        sendResponse({ started: true });
    }
    return true;
});