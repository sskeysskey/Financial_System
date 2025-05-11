// content.js

(function () {
    // —— 辅助：找出目标表格 —— 
    function findHistoryTable() {
        // 1) 优先 data-testid 容器
        let tbl = document.querySelector('[data-testid="history-table"] table');
        if (tbl) return tbl;

        // 2) 再遍历所有 table，看 header 是否包含 Date & Volume
        const all = Array.from(document.querySelectorAll('table'));
        for (let t of all) {
            const ths = Array.from(t.querySelectorAll('thead th'))
                .map(th => th.textContent.trim());
            if (ths.includes('Date') && ths.some(h => /Volume/i.test(h))) {
                return t;
            }
        }
        return null;
    }

    // —— 辅助：提取表头列索引 —— 
    function getColumnIndices(table) {
        const headers = Array.from(table.querySelectorAll('thead th'))
            .map(th => th.textContent.trim());
        return {
            date: headers.indexOf('Date'),
            // 根据你关心的列名再调整正则/关键字
            close: headers.findIndex(h => /Close/i.test(h)),
            volume: headers.findIndex(h => /Volume/i.test(h))
        };
    }

    // —— 辅助：提取 ticker，同之前方案，保底再去 h1.yf-xxbei9 —— 
    function getTicker() {
        try {
            const ps = location.pathname.split('/');
            if (ps[1] === 'quote' && ps[2]) return ps[2].toUpperCase();
            const p = new URLSearchParams(location.search).get('p');
            if (p) return p.toUpperCase();
        } catch (e) { }
        const h1a = document.querySelector('[data-testid="quote-hdr"] h1');
        if (h1a) {
            const m = h1a.textContent.match(/\(([^)]+)\)/);
            if (m) return m[1].trim().toUpperCase();
        }
        const h1b = document.querySelector('h1.yf-xxbei9');
        if (h1b) {
            const m = h1b.textContent.match(/\(([^)]+)\)/);
            if (m) return m[1].trim().toUpperCase();
        }
        return 'data';
    }

    // —— 主流程 —— 
    const table = findHistoryTable();
    if (!table) {
        console.error('未找到历史数据表格');
        return;
    }

    const cols = getColumnIndices(table);
    if (cols.date < 0 || cols.close < 0 || cols.volume < 0) {
        console.error('表头列不符合预期', cols);
        return;
    }

    const rows = Array.from(table.querySelectorAll('tbody tr'));
    if (rows.length === 0) {
        console.error('表格无数据行');
        return;
    }

    const scraped = [];
    rows.forEach(r => {
        const cells = Array.from(r.querySelectorAll('td'));
        // 简单容错
        if (cells.length <= Math.max(cols.date, cols.close, cols.volume)) return;

        // 1) 解析日期
        let rawDate = cells[cols.date].textContent.trim()
            .split('::')[0].replace(/"/g, '');
        let d = new Date(rawDate);
        const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

        // 2) 解析价格
        const priceText = cells[cols.close].textContent.trim().replace(/,/g, '');
        const price = parseFloat(priceText);

        // 3) 解析成交量，如果是 "-" 就当作 null
        const volText = cells[cols.volume].textContent.trim().replace(/,/g, '');
        let volume = null;
        if (volText !== '-' && !isNaN(parseInt(volText, 10))) {
            volume = parseInt(volText, 10);
        }

        if (!isNaN(d) && !isNaN(price)) {
            scraped.push({ date, price, volume });
        }
    });

    if (scraped.length === 0) {
        console.error('解析后无有效数据');
        return;
    }

    // —— 根据是否有有效 volume 决定 CSV 列 —— 
    const includeVolume = scraped.some(e => e.volume !== null);

    // 组装 CSV
    let csv = includeVolume
        ? 'date,price,volume\n'
        : 'date,price\n';

    scraped.forEach(e => {
        let line = `${e.date},${e.price}`;
        if (includeVolume) {
            line += e.volume !== null ? `,${e.volume}` : ',';
        }
        csv += line + '\n';
    });

    // 发消息给 background.js 去下载
    const ticker = getTicker();
    chrome.runtime.sendMessage({
        action: 'downloadCSV',
        csv,
        filename: `${ticker}.csv`
    });

})();