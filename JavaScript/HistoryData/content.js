// content.js

(function () {
    // ---- 辅助函数：向 popup 发送状态更新 ----
    function sendStatus(message, type = 'info') { // type: 'info', 'success', 'error'
        chrome.runtime.sendMessage({
            action: 'updateStatus',
            data: { message, type }
        });
    }

    // ---- 辅助：找出目标表格 ---- 
    function findHistoryTable() {
        // ... (这部分函数代码保持不变) ...
        let tbl = document.querySelector('[data-testid="history-table"] table');
        if (tbl) return tbl;
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

    // ---- 辅助：提取表头列索引 ---- 
    function getColumnIndices(table) {
        // ... (这部分函数代码保持不变) ...
        const headers = Array.from(table.querySelectorAll('thead th'))
            .map(th => th.textContent.trim());
        return {
            date: headers.indexOf('Date'),
            close: headers.findIndex(h => /Close/i.test(h)),
            volume: headers.findIndex(h => /Volume/i.test(h))
        };
    }

    // ---- 辅助：提取 ticker ---- 
    function getTicker() {
        // ... (这部分函数代码保持不变) ...
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

    // ---- 主流程 ---- 
    function main() {
        sendStatus('内容脚本已注入，开始执行...');

        // 步骤 1: 查找数据表格
        sendStatus('步骤 1: 正在查找历史数据表格...');
        const table = findHistoryTable();
        if (!table) {
            sendStatus('未找到历史数据表格，请确认页面正确。', 'error');
            return;
        }
        sendStatus('成功找到数据表格。', 'success');

        // 步骤 2: 解析表头
        sendStatus('步骤 2: 正在解析表头列...');
        const cols = getColumnIndices(table);
        if (cols.date < 0 || cols.close < 0 || cols.volume < 0) {
            sendStatus('表头列不符合预期 (Date, Close, Volume)，脚本可能需要更新。', 'error');
            console.error('表头列不符合预期', cols);
            return;
        }
        sendStatus('成功解析表头列。', 'success');

        // 步骤 3: 提取 Ticker
        sendStatus('步骤 3: 正在提取 Ticker 名称...');
        const ticker = getTicker();
        sendStatus(`提取到 Ticker: ${ticker}`, 'success');

        // 步骤 4: 提取并解析数据行
        sendStatus('步骤 4: 正在提取并解析表格数据...');
        const rows = Array.from(table.querySelectorAll('tbody tr'));
        if (rows.length === 0) {
            sendStatus('表格中没有数据行。', 'error');
            return;
        }
        sendStatus(`找到 ${rows.length} 行数据，开始处理...`, 'info');

        const scraped = [];
        rows.forEach(r => {
            const cells = Array.from(r.querySelectorAll('td'));
            if (cells.length <= Math.max(cols.date, cols.close, cols.volume)) return;

            let rawDate = cells[cols.date].textContent.trim().split('::')[0].replace(/"/g, '');
            let d = new Date(rawDate);
            const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
            const priceText = cells[cols.close].textContent.trim().replace(/,/g, '');
            const price = parseFloat(priceText);
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
            sendStatus('解析后无有效数据。', 'error');
            return;
        }
        sendStatus(`成功解析 ${scraped.length} 条有效数据。`, 'success');

        // 步骤 5: 生成 CSV 内容
        sendStatus('步骤 5: 正在生成 CSV 文件内容...');
        const includeVolume = scraped.some(e => e.volume !== null);
        let csv = includeVolume ? 'date,price,volume\n' : 'date,price\n';
        scraped.forEach(e => {
            let line = `${e.date},${e.price}`;
            if (includeVolume) {
                line += e.volume !== null ? `,${e.volume}` : ',';
            }
            csv += line + '\n';
        });
        sendStatus('CSV 内容生成完毕。', 'success');

        // 步骤 6: 发送下载请求
        sendStatus('步骤 6: 发送下载指令到后台...');
        chrome.runtime.sendMessage({
            action: 'downloadCSV',
            csv,
            filename: `${ticker}.csv`
        });
    }

    // 执行主函数
    main();

})();