/* =========================================================================
 * TopETFs Scraper — background.js (v2.0，架构参照 Screener v2.0)
 * 特性：
 *  - 全部逻辑跑在 Service Worker，popup 关闭不影响任务（含下载）
 *  - 不再等待 tab 'complete'，而是直接轮询 DOM，表格一出现且行数稳定就抓
 *  - 所有 chrome API 调用带硬超时，绝不永久挂起
 *  - 状态持久化 + alarms 看门狗，SW 被回收后自动断点续跑
 *  - 页面卡住 -> 自动 reload -> 换前台标签页 -> 多轮重试
 *  - 下载用 data URL（SW 无 FileReader / URL.createObjectURL）
 * ========================================================================= */

const CONFIG = {
    STATE_KEY: 'etfScraperState',
    ALARM: 'etf-scraper-watchdog',
    ALARM_PERIOD_MIN: 0.5,        // 30秒唤醒一次（看门狗 + 保活）

    CONCURRENCY: 3,               // 并发标签页数

    TAB_CREATE_TIMEOUT: 20000,
    EXEC_TIMEOUT: 10000,
    PAGE_READY_TIMEOUT: 70000,    // 单次尝试内等待表格出现的硬上限
    RELOAD_AFTER: 25000,          // 超过这个时间还没数据 -> 强制刷新
    POLL_INTERVAL: 800,
    POST_READY_DELAY: 300,        // 行数稳定后再稍等一下
    TAB_REMOVE_TIMEOUT: 6000,

    MAX_ATTEMPTS_PER_ROUND: 4,
    MAX_ROUNDS: 8,
    RETRY_BASE_DELAY: 2500,
    RETRY_MAX_DELAY: 20000,
    ROUND_GAP: 8000,

    ACTIVATE_ON_RETRY: true,      // 第2次及以后的尝试用前台标签页

    MAX_LOGS: 400,
    // 上次完成超过这个时间后，打开 popup 自动开新任务
    // （Python 端等待 5 分钟没文件才会重新拉起，二者配合保证重拉一定能触发新任务）
    AUTO_RESTART_AFTER_MS: 3 * 60 * 1000
};

const URLS = [
    'https://finance.yahoo.com/markets/etfs/top/?start=0&count=100',
    'https://finance.yahoo.com/markets/etfs/top/?start=100&count=100',
    'https://finance.yahoo.com/markets/etfs/top/?start=200&count=100',
    'https://finance.yahoo.com/markets/etfs/top/?start=300&count=100',
    'https://finance.yahoo.com/markets/etfs/top/?start=400&count=100'
];

/* ------------------------------- 全局运行态 ------------------------------- */
let state = null;
let loopRunning = false;

/* --------------------------------- 工具 ---------------------------------- */
function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

function withTimeout(promise, ms, label) {
    return new Promise((resolve, reject) => {
        let done = false;
        const t = setTimeout(() => {
            if (done) return;
            done = true;
            reject(new Error(`${label} 超时(${ms}ms)`));
        }, ms);
        Promise.resolve(promise).then(
            v => { if (!done) { done = true; clearTimeout(t); resolve(v); } },
            e => { if (!done) { done = true; clearTimeout(t); reject(e); } }
        );
    });
}

function dateStr() {
    const n = new Date();
    return `${String(n.getFullYear() % 100).padStart(2, '0')}${String(n.getMonth() + 1).padStart(2, '0')}${String(n.getDate()).padStart(2, '0')}`;
}

function taskLabel(task) {
    return `[Page #${task.id + 1}]`;
}

/* ------------------------------- 状态持久化 ------------------------------- */
let lastSave = 0, saveTimer = null;

async function saveState(immediate = false) {
    if (!state) return;
    const now = Date.now();
    if (immediate || now - lastSave > 600) {
        lastSave = now;
        if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
        try { await chrome.storage.local.set({ [CONFIG.STATE_KEY]: state }); } catch (e) { }
    } else if (!saveTimer) {
        saveTimer = setTimeout(() => { saveTimer = null; saveState(true); }, 600);
    }
}

async function loadState() {
    try {
        const o = await chrome.storage.local.get(CONFIG.STATE_KEY);
        state = o[CONFIG.STATE_KEY] || null;
    } catch (e) { state = null; }
    return state;
}

function log(text, type = 'info') {
    const line = { seq: (state ? ++state.logSeq : 0), t: Date.now(), text, type };
    console.log(`[${type}] ${text}`);
    if (!state) return;
    state.logs.push(line);
    if (state.logs.length > CONFIG.MAX_LOGS) state.logs.splice(0, state.logs.length - CONFIG.MAX_LOGS);
    state.lastActivity = Date.now();
    saveState();
}

function doneCount() {
    return state.tasks.filter(t => t.status === 'done').length;
}

/* ------------------------- 注入到页面里执行的函数 ------------------------- */
/* 注意：该函数会被序列化后注入页面，内部不能引用任何外部变量。
 * doExtract=false -> 只探测（轻量）；doExtract=true -> 提取数据 */
function pageScan(doExtract) {
    function txt(el) {
        return el ? (el.textContent || '').replace(/\s+/g, ' ').trim() : '';
    }

    function mapHeaders(table) {
        const map = {};
        table.querySelectorAll('thead th').forEach((th, i) => {
            const t = txt(th).toLowerCase();
            if (!t) return;
            // 只取第一个匹配，防止后面的列覆盖
            if (map.symbol === undefined && t.includes('symbol')) map.symbol = i;
            else if (map.name === undefined && t.includes('name')) map.name = i;
            else if (map.price === undefined && t.includes('price')) map.price = i;
            else if (map.volume === undefined && t.includes('volume') && !t.includes('avg')) map.volume = i;
        });
        const ok = ['symbol', 'name', 'price', 'volume'].every(k => map[k] !== undefined);
        return { map, ok };
    }

    function bodyRows(table) {
        let rows = table.querySelectorAll('tbody tr[data-testid="data-table-v2-row"]');
        if (!rows.length) rows = table.querySelectorAll('tbody tr');
        return rows;
    }

    function findTable() {
        const seen = new Set();
        const cands = [];
        const preferred = [
            'div[data-testid="screener-table"] table',
            'div[data-testid="scr-res-table"] table',
            'div[data-testid="top-etfs-table"] table'
        ];
        for (const sel of preferred) {
            const t = document.querySelector(sel);
            if (t && !seen.has(t)) { seen.add(t); cands.push(t); }
        }
        document.querySelectorAll('table').forEach(t => {
            if (!seen.has(t)) { seen.add(t); cands.push(t); }
        });

        let best = null;
        for (const t of cands) {
            const h = mapHeaders(t);
            if (!h.ok) continue;
            const rows = bodyRows(t);
            if (!rows.length) continue;
            if (!best || rows.length > best.rows.length) best = { table: t, map: h.map, rows };
        }
        return best;
    }

    function normalizeVolume(raw) {
        if (!raw) return '';
        let s = String(raw).trim().toUpperCase();
        if (s === '' || s === '--' || s === 'N/A') return '';
        let mul = 1;
        const last = s.slice(-1);
        if (last === 'T') { mul = 1e12; s = s.slice(0, -1); }
        else if (last === 'B') { mul = 1e9; s = s.slice(0, -1); }
        else if (last === 'M') { mul = 1e6; s = s.slice(0, -1); }
        else if (last === 'K') { mul = 1e3; s = s.slice(0, -1); }
        const n = parseFloat(s.replace(/,/g, ''));
        return isNaN(n) ? '' : String(Math.round(n * mul));
    }

    function streamerValue(cell, selector) {
        if (!cell) return '';
        const fs = cell.querySelector(selector);
        if (fs) {
            const v = (fs.getAttribute('value') || '').trim();
            if (v) return v;
            const t = txt(fs);
            if (t) return t;
        }
        return txt(cell);
    }

    try {
        const best = findTable();

        if (!doExtract) {
            return {
                readyState: document.readyState,
                hasAnyTable: !!document.querySelector('table'),
                headersOk: !!best,
                rowCount: best ? best.rows.length : 0,
                href: location.href
            };
        }

        if (!best) return { success: false, data: [], message: '未找到包含 Symbol/Name/Price/Volume 的表格' };

        const { map, rows } = best;
        const out = [];
        let skipped = 0;

        for (const row of rows) {
            try {
                const cells = row.querySelectorAll('td');

                // Symbol
                const symCell = cells[map.symbol];
                const symEl = row.querySelector('a[data-testid="table-cell-ticker"] span.symbol')
                    || row.querySelector('a[data-testid="table-cell-ticker"]')
                    || symCell;
                const symbol = txt(symEl).split(' ')[0];

                // Name
                const nameCell = cells[map.name];
                let name = '';
                if (nameCell) {
                    const titled = nameCell.querySelector('[title]');
                    name = (titled && (titled.getAttribute('title') || '').trim()) || txt(nameCell);
                }

                // Price
                const priceCell = row.querySelector('td[data-testid-cell="intradayprice"]') || cells[map.price];
                const priceRaw = streamerValue(priceCell, 'fin-streamer[data-field="regularMarketPrice"]');
                const m = priceRaw.replace(/,/g, '').match(/-?\d+(\.\d+)?/);
                const price = m ? m[0] : '';

                // Volume
                const volCell = row.querySelector('td[data-testid-cell="dayvolume"]') || cells[map.volume];
                const volRaw = streamerValue(volCell,
                    'fin-streamer[data-field="regularMarketVolume"], fin-streamer[data-field="volume"]');
                const volume = normalizeVolume(volRaw);

                if (!symbol || !name || !price || !(parseFloat(price) > 0) || volume === '') {
                    skipped++;
                    continue;
                }
                out.push({ symbol, name, price, volume });
            } catch (e) { skipped++; }
        }

        return {
            success: true,
            data: out,
            rowCount: rows.length,
            message: `抓取 ${out.length} 条${skipped ? '，跳过 ' + skipped + ' 行' : ''}`
        };
    } catch (e) {
        return doExtract
            ? { success: false, data: [], message: '注入脚本异常: ' + e.message }
            : null;
    }
}

/* ------------------------------ 标签页操作 ------------------------------- */
async function registerTab(tabId) {
    if (!state.openTabIds) state.openTabIds = [];
    state.openTabIds.push(tabId);
    await saveState(true);
}

async function closeTab(tabId) {
    try { await withTimeout(chrome.tabs.remove(tabId), CONFIG.TAB_REMOVE_TIMEOUT, 'tabs.remove'); } catch (e) { }
    if (state && state.openTabIds) {
        state.openTabIds = state.openTabIds.filter(x => x !== tabId);
        await saveState();
    }
}

async function cleanupOrphanTabs() {
    if (!state || !state.openTabIds || !state.openTabIds.length) return;
    const ids = state.openTabIds.slice();
    state.openTabIds = [];
    await saveState(true);
    for (const id of ids) {
        try { await withTimeout(chrome.tabs.remove(id), 4000, 'cleanup'); } catch (e) { }
    }
    log(`清理了 ${ids.length} 个遗留标签页`, 'warning');
}

async function safeExec(tabId, func, args = []) {
    try {
        const res = await withTimeout(
            chrome.scripting.executeScript({ target: { tabId }, func, args }),
            CONFIG.EXEC_TIMEOUT, 'executeScript'
        );
        return (res && res[0]) ? res[0].result : null;
    } catch (e) {
        return null;
    }
}

/* ------------------------------ 单页抓取一次 ----------------------------- */
async function scrapeOnce(task, attempt) {
    let tabId = null;
    try {
        const active = CONFIG.ACTIVATE_ON_RETRY && attempt >= 2;
        const tab = await withTimeout(
            chrome.tabs.create({ url: task.url, active }),
            CONFIG.TAB_CREATE_TIMEOUT, 'tabs.create'
        );
        tabId = tab.id;
        await registerTab(tabId);

        try { await withTimeout(chrome.tabs.update(tabId, { autoDiscardable: false }), 4000, 'update'); } catch (e) { }

        const start = Date.now();
        const deadline = start + CONFIG.PAGE_READY_TIMEOUT;
        let reloaded = false;
        let ready = false;
        let lastProbe = null;
        let prevRows = -1;

        while (Date.now() < deadline) {
            if (!state || !state.running) throw new Error('任务已停止');

            const probe = await safeExec(tabId, pageScan, [false]);
            lastProbe = probe;

            if (probe && probe.headersOk && probe.rowCount > 0) {
                // 连续两次探测行数一致 -> 认为渲染完成（避免抓到半截表格）
                if (probe.rowCount === prevRows) { ready = true; break; }
                prevRows = probe.rowCount;
            } else {
                prevRows = -1;
            }

            if (!reloaded && Date.now() - start > CONFIG.RELOAD_AFTER) {
                reloaded = true;
                prevRows = -1;
                log(`${taskLabel(task)} 页面疑似卡住，强制刷新...`, 'warning');
                try { await withTimeout(chrome.tabs.reload(tabId, { bypassCache: true }), 8000, 'reload'); } catch (e) { }
            }

            state.lastActivity = Date.now();
            await sleep(CONFIG.POLL_INTERVAL);
        }

        if (!ready) {
            let extra = '';
            if (lastProbe === null) extra = '（脚本无法注入，可能被重定向到同意页/错误页）';
            else if (!lastProbe.hasAnyTable) extra = `（readyState=${lastProbe.readyState}，表格未出现）`;
            else if (!lastProbe.headersOk) extra = '（找到表格但表头/数据行不完整）';
            throw new Error('等待表格数据超时' + extra);
        }

        await sleep(CONFIG.POST_READY_DELAY);

        const res = await safeExec(tabId, pageScan, [true]);
        if (!res) throw new Error('抓取脚本无返回（页面可能已跳转）');
        if (!res.success) throw new Error(res.message || '抓取失败');
        if (!res.data || res.data.length === 0) throw new Error(`抓取到 0 条数据（表格 ${res.rowCount || 0} 行）`);

        return res.data;
    } finally {
        if (tabId != null) await closeTab(tabId);
    }
}

/* ------------------------------ 单页任务（含重试） ----------------------- */
async function processTask(task) {
    while (state && state.running) {
        task.attempts = (task.attempts || 0) + 1;
        const attempt = task.attempts;
        task.startedAt = Date.now();
        await saveState();

        try {
            const data = await scrapeOnce(task, attempt);
            task.data = data;
            task.status = 'done';
            task.error = null;
            log(`${taskLabel(task)} ✅ 获取 ${data.length} 条  (${doneCount()}/${state.tasks.length})`, 'success');
            await saveState(true);
            return;
        } catch (e) {
            task.error = e.message;
            log(`${taskLabel(task)} 第 ${attempt} 次失败: ${e.message}`, 'error');
            await saveState();

            if (!state.running) return;

            if (attempt >= CONFIG.MAX_ATTEMPTS_PER_ROUND) {
                task.status = 'failed';
                log(`${taskLabel(task)} 本轮暂时放弃，稍后整体重试`, 'warning');
                await saveState(true);
                return;
            }
            const delay = Math.min(CONFIG.RETRY_BASE_DELAY * attempt, CONFIG.RETRY_MAX_DELAY);
            log(`${taskLabel(task)} ${Math.round(delay / 1000)} 秒后重试...`, 'warning');
            await sleep(delay);
        }
    }
}

/* --------------------------------- 主循环 -------------------------------- */
async function runLoop() {
    if (loopRunning) return;
    loopRunning = true;
    try {
        if (!state) await loadState();
        if (!state || !state.running) return;

        await cleanupOrphanTabs();

        while (state && state.running) {
            state.tasks.forEach(t => { if (t.status === 'running') t.status = 'pending'; });

            const pending = state.tasks.filter(t => t.status === 'pending');
            if (pending.length === 0) {
                const failed = state.tasks.filter(t => t.status === 'failed');
                if (failed.length && state.round < CONFIG.MAX_ROUNDS) {
                    state.round++;
                    failed.forEach(t => { t.status = 'pending'; t.attempts = 0; });
                    log(`还有 ${failed.length} 个页面未成功 → 开始第 ${state.round} 轮重试`, 'warning');
                    await saveState(true);
                    await sleep(CONFIG.ROUND_GAP);
                    continue;
                }
                break;
            }

            const workers = [];
            const n = Math.min(CONFIG.CONCURRENCY, pending.length);
            for (let i = 0; i < n; i++) workers.push(workerLoop());
            await Promise.all(workers);
        }

        if (state && state.running) await finalize();
    } catch (e) {
        log('主循环异常: ' + e.message + '（看门狗将自动恢复）', 'error');
    } finally {
        loopRunning = false;
    }
}

async function workerLoop() {
    while (state && state.running) {
        const task = state.tasks.find(t => t.status === 'pending');
        if (!task) return;
        task.status = 'running';
        await saveState();
        await processTask(task);
    }
}

/* -------------------------------- 生成 & 下载 ---------------------------- */
function csvField(v) {
    return `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;
}

function toCSV(rows) {
    let s = 'Symbol,Name,Price,Volume\n';
    for (const r of rows) {
        s += `${csvField(r.symbol)},${csvField(r.name)},${csvField(r.price)},${csvField(r.volume)}\n`;
    }
    return s;
}

function toDataUrl(text, mime) {
    const bytes = new TextEncoder().encode(text);
    let bin = '';
    const CHUNK = 0x8000;
    for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    return `data:${mime};base64,` + btoa(bin);
}

async function downloadText(filename, text, mime = 'text/csv') {
    const url = toDataUrl(text, mime);
    for (let i = 1; i <= 5; i++) {
        try {
            const id = await withTimeout(
                chrome.downloads.download({ url, filename, conflictAction: 'uniquify', saveAs: false }),
                25000, 'downloads.download'
            );
            log(`⬇️ 下载成功: ${filename} (id=${id})`, 'success');
            return true;
        } catch (e) {
            log(`下载 ${filename} 第 ${i} 次失败: ${e.message}`, 'error');
            await sleep(3000);
        }
    }
    log(`❌ 下载 ${filename} 最终失败`, 'error');
    return false;
}

async function finalize() {
    const all = [];
    const seen = new Set();
    // 按页面顺序合并 + 去重（盘中排名变动会导致相邻页重复）
    const ordered = state.tasks.slice().sort((a, b) => a.id - b.id);
    for (const t of ordered) {
        if (t.status === 'done' && Array.isArray(t.data)) {
            for (const r of t.data) {
                if (seen.has(r.symbol)) continue;
                seen.add(r.symbol);
                all.push(r);
            }
        }
    }

    const failed = state.tasks.filter(t => t.status !== 'done');
    if (failed.length) {
        log(`⚠️ 有 ${failed.length} 个页面最终未成功：${failed.map(t => '#' + (t.id + 1)).join(', ')}`, 'warning');
    }

    let ok = false;
    if (all.length === 0) {
        log('未收集到任何数据，不生成文件', 'error');
    } else {
        log(`共 ${all.length} 条 ETF（去重后），生成 CSV...`, 'final');
        try {
            ok = await downloadText(`topetf_${dateStr()}.csv`, toCSV(all));
        } catch (e) {
            log('下载阶段异常: ' + e.message, 'error');
        }
    }

    state.running = false;
    state.finished = true;
    state.downloaded = ok;
    state.finishedAt = Date.now();
    await cleanupOrphanTabs();
    log('🎉 全部任务结束', 'final');
    await saveState(true);
    try { await chrome.alarms.clear(CONFIG.ALARM); } catch (e) { }
}

/* --------------------------------- 启停控制 ------------------------------ */
async function startScraping(force = false) {
    await loadState();

    if (state && state.running && !force) {
        if (!loopRunning) { log('检测到已有任务在跑，恢复执行', 'warning'); runLoop(); }
        return { started: false, reason: 'already-running' };
    }

    if (state) { state.running = false; await cleanupOrphanTabs(); }

    state = {
        running: true,
        finished: false,
        downloaded: false,
        stoppedByUser: false,
        startedAt: Date.now(),
        finishedAt: 0,
        round: 1,
        logSeq: 0,
        logs: [],
        openTabIds: [],
        lastActivity: Date.now(),
        tasks: URLS.map((url, i) => ({
            id: i, url,
            status: 'pending', attempts: 0, data: null, error: null, startedAt: 0
        }))
    };
    await saveState(true);
    log(`初始化：共 ${URLS.length} 个页面，并发 ${CONFIG.CONCURRENCY}`, 'final');

    try { await chrome.alarms.create(CONFIG.ALARM, { periodInMinutes: CONFIG.ALARM_PERIOD_MIN }); } catch (e) { }

    runLoop();
    return { started: true };
}

async function stopScraping() {
    await loadState();
    if (!state) return;
    state.running = false;
    state.finished = true;
    state.stoppedByUser = true;
    state.finishedAt = Date.now();
    log('用户手动停止', 'warning');
    await saveState(true);
    await cleanupOrphanTabs();
    try { await chrome.alarms.clear(CONFIG.ALARM); } catch (e) { }
}

/* -------------------------------- 看门狗 --------------------------------- */
chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (alarm.name !== CONFIG.ALARM) return;
    await loadState();
    if (!state || !state.running) {
        try { await chrome.alarms.clear(CONFIG.ALARM); } catch (e) { }
        return;
    }
    if (!loopRunning) {
        log('⏰ 看门狗：检测到任务中断（后台被回收/异常），自动恢复...', 'warning');
        state.tasks.forEach(t => { if (t.status === 'running') t.status = 'pending'; });
        await saveState(true);
        runLoop();
    }
});

/* ------------------------- 启动 / 安装 时自动续跑 ------------------------ */
async function resumeIfNeeded() {
    await loadState();
    if (state && state.running && !loopRunning) {
        log('浏览器重启/扩展重载，自动续跑未完成任务', 'warning');
        try { await chrome.alarms.create(CONFIG.ALARM, { periodInMinutes: CONFIG.ALARM_PERIOD_MIN }); } catch (e) { }
        runLoop();
    }
}
chrome.runtime.onStartup.addListener(resumeIfNeeded);
chrome.runtime.onInstalled.addListener(resumeIfNeeded);

/* ------------------------------- 与 popup 通信 --------------------------- */
chrome.runtime.onConnect.addListener(port => {
    if (port.name !== 'popup') return;
    port.onMessage.addListener(() => { });
    resumeIfNeeded();
});

chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    (async () => {
        try {
            if (req.action === 'start') {
                const s = await loadState();
                // 可自动开新任务的条件：
                //  1) 从没跑过；或
                //  2) 没在跑，且（距上次结束已超过阈值，或上次没成功下载且不是用户手动停止）
                const canAuto = !s || (!s.running && (
                    !s.finishedAt ||
                    Date.now() - s.finishedAt > CONFIG.AUTO_RESTART_AFTER_MS ||
                    (!s.downloaded && !s.stoppedByUser)
                ));
                if (req.force) {
                    sendResponse(await startScraping(true));
                } else if (canAuto) {
                    sendResponse(await startScraping(false));
                } else {
                    if (s && s.running && !loopRunning) runLoop();
                    sendResponse({ started: false, reason: 'recent-or-running' });
                }
            } else if (req.action === 'stop') {
                await stopScraping();
                sendResponse({ ok: true });
            } else if (req.action === 'getState') {
                await loadState();
                sendResponse({ state });
            } else {
                sendResponse({ ok: false, error: 'unknown action' });
            }
        } catch (e) {
            sendResponse({ ok: false, error: e.message });
        }
    })();
    return true;
});