/* =========================================================================
 * Screener Data Scraper — background.js (v2.0)
 * 特性：
 *  - 全部逻辑跑在 Service Worker，popup 关闭不影响任务
 *  - 所有 chrome API 调用带硬超时，绝不永久挂起
 *  - 状态持久化 + alarms 看门狗，SW 被回收后自动断点续跑
 *  - 页面卡住 -> 自动 reload -> 换前台标签页 -> 无限轮次重试
 *  - 下载用 data URL（SW 无 FileReader / URL.createObjectURL）
 * ========================================================================= */

const CONFIG = {
    STATE_KEY: 'scraperState',
    ALARM: 'scraper-watchdog',
    ALARM_PERIOD_MIN: 0.5,        // 30秒唤醒一次（看门狗 + 保活）

    CONCURRENCY: 3,               // 并发标签页数（网络差时建议 2~3）

    TAB_CREATE_TIMEOUT: 20000,    // 创建标签页超时
    EXEC_TIMEOUT: 10000,          // 单次注入脚本超时
    PAGE_READY_TIMEOUT: 70000,    // 单次尝试内等待表格出现的硬上限
    RELOAD_AFTER: 25000,          // 等待超过这个时间还没数据 -> 强制刷新
    POLL_INTERVAL: 800,           // 探测间隔
    POST_READY_DELAY: 700,        // 表格出现后再等一下，让行渲染完
    TAB_REMOVE_TIMEOUT: 6000,

    MAX_ATTEMPTS_PER_ROUND: 4,    // 每轮内单页最多尝试次数
    MAX_ROUNDS: 12,               // 总轮次上限（失败页会一轮轮重来）
    RETRY_BASE_DELAY: 2500,
    RETRY_MAX_DELAY: 20000,
    ROUND_GAP: 8000,              // 轮次之间的休息

    ACTIVATE_ON_RETRY: true,      // 第2次及以后的尝试用前台标签页（成功率高很多）

    MAX_LOGS: 400,
    AUTO_RESTART_AFTER_MS: 10 * 60 * 1000 // 上次完成超过10分钟后，打开popup自动开新任务
};

const URLS = [
    { url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=0&count=100', category: 'Technology' },
    { url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=100&count=100', category: 'Technology' },
    { url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=200&count=100', category: 'Technology' },
    { url: 'https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=0&count=100', category: 'Industrials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=100&count=100', category: 'Industrials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=200&count=100', category: 'Industrials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=0&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=100&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=200&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=300&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/e5221069-608f-419e-a3ff-24e61e4a07ac/?start=0&count=100', category: 'Basic_Materials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/90966b0c-2902-425c-870a-f19eb1ffd0b8/?start=0&count=100', category: 'Consumer_Defensive' },
    { url: 'https://finance.yahoo.com/research-hub/screener/84e650e0-3916-4907-ad56-2fba4209fa3f/?start=0&count=100', category: 'Utilities' },
    { url: 'https://finance.yahoo.com/research-hub/screener/1788e450-82cf-449a-b284-b174e8e3f6d6/?start=0&count=100', category: 'Energy' },
    { url: 'https://finance.yahoo.com/research-hub/screener/1788e450-82cf-449a-b284-b174e8e3f6d6/?start=100&count=100', category: 'Energy' },
    { url: 'https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=0&count=100', category: 'Consumer_Cyclical' },
    { url: 'https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=100&count=100', category: 'Consumer_Cyclical' },
    { url: 'https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=200&count=100', category: 'Consumer_Cyclical' },
    { url: 'https://finance.yahoo.com/research-hub/screener/9a217ba3-966a-4340-83b9-edb160f05f8e/?start=0&count=100', category: 'Real_Estate' },
    { url: 'https://finance.yahoo.com/research-hub/screener/9a217ba3-966a-4340-83b9-edb160f05f8e/?start=100&count=100', category: 'Real_Estate' },
    { url: 'https://finance.yahoo.com/research-hub/screener/f99d96f0-a144-48be-b220-0be74c55ebf4/?start=0&count=100', category: 'Healthcare' },
    { url: 'https://finance.yahoo.com/research-hub/screener/f99d96f0-a144-48be-b220-0be74c55ebf4/?start=100&count=100', category: 'Healthcare' },
    { url: 'https://finance.yahoo.com/research-hub/screener/360b16ee-2692-4617-bd1a-a6c715dd0c29/?start=0&count=100', category: 'Communication_Services' }
];

/* ------------------------------- 全局运行态 ------------------------------- */
let state = null;        // 持久化状态（内存副本）
let loopRunning = false; // 当前 SW 实例里是否有主循环在跑

/* --------------------------------- 工具 ---------------------------------- */
function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

/** 给任意 Promise 加硬超时，防止 chrome API 回调永不返回导致死锁 */
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
/* 注意：这两个函数会被序列化后注入页面，内部不能引用任何外部变量 */

function pageProbe() {
    const c = document.querySelector('div[data-testid="screener-table"]');
    let rows = 0;
    if (c) {
        rows = c.querySelectorAll('tbody tr[data-testid="data-table-v2-row"]').length
            || c.querySelectorAll('tbody tr').length;
    }
    return {
        readyState: document.readyState,
        rowCount: rows,
        hasContainer: !!c,
        href: location.href
    };
}

function pageExtract(category) {
    function parseSuffixedNumber(text) {
        if (!text) return 'N/A';
        let t = String(text).trim().toUpperCase();
        if (t === '' || t === '--' || t === 'N/A') return 'N/A';
        let mul = 1;
        const last = t.slice(-1);
        if (last === 'T') { mul = 1e12; t = t.slice(0, -1); }
        else if (last === 'B') { mul = 1e9; t = t.slice(0, -1); }
        else if (last === 'M') { mul = 1e6; t = t.slice(0, -1); }
        else if (last === 'K') { mul = 1e3; t = t.slice(0, -1); }
        const v = parseFloat(t.replace(/,/g, ''));
        return isNaN(v) ? 'N/A' : v * mul;
    }

    try {
        const container = document.querySelector('div[data-testid="screener-table"]');
        if (!container) return { success: false, data: [], message: '未找到表格容器' };

        let rows = container.querySelectorAll('tbody tr[data-testid="data-table-v2-row"]');
        if (!rows.length) rows = container.querySelectorAll('tbody tr');
        if (!rows.length) return { success: false, data: [], message: '表格内没有数据行' };

        const out = [];
        let skipped = 0;

        for (const row of rows) {
            try {
                let symbol = null;
                const symEl = row.querySelector('a[data-testid="table-cell-ticker"] span.symbol')
                    || row.querySelector('a[data-testid="table-cell-ticker"]')
                    || row.querySelector('td:first-child a');
                if (symEl) symbol = symEl.textContent.trim().split(/\s+/)[0];
                if (!symbol) { skipped++; continue; }

                const priceText = (row.querySelector('td[data-testid-cell="intradayprice"]')?.textContent || '').trim();
                const price = (priceText && priceText !== '--')
                    ? parseFloat(priceText.replace(/,/g, '')) : 'N/A';

                const mcText = (row.querySelector('td[data-testid-cell="intradaymarketcap"]')?.textContent || '--').trim();
                const marketCap = parseSuffixedNumber(mcText);

                const volText = (row.querySelector('td[data-testid-cell="dayvolume"]')?.textContent || '--').trim();
                const volume = parseSuffixedNumber(volText);

                if (typeof marketCap !== 'number' || isNaN(marketCap)) { skipped++; continue; }

                out.push({ symbol, marketCap, category, price, volume });
            } catch (e) { skipped++; }
        }

        return {
            success: true,
            data: out,
            message: `抓取 ${out.length} 条${skipped ? '，跳过 ' + skipped + ' 行' : ''}`
        };
    } catch (e) {
        return { success: false, data: [], message: '注入脚本异常: ' + e.message };
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

/** 安全注入：失败/超时返回 null，绝不抛出、绝不挂起 */
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

        // 防止后台标签被 Chrome 丢弃
        try { await withTimeout(chrome.tabs.update(tabId, { autoDiscardable: false }), 4000, 'update'); } catch (e) { }

        const start = Date.now();
        const deadline = start + CONFIG.PAGE_READY_TIMEOUT;
        let reloaded = false;
        let ready = false;
        let lastProbe = null;

        while (Date.now() < deadline) {
            if (!state || !state.running) throw new Error('任务已停止');

            const probe = await safeExec(tabId, pageProbe);
            lastProbe = probe;
            if (probe && probe.rowCount > 0) { ready = true; break; }

            // 卡住：强制刷新一次
            if (!reloaded && Date.now() - start > CONFIG.RELOAD_AFTER) {
                reloaded = true;
                log(`[${task.category} #${task.id + 1}] 页面疑似卡住，强制刷新...`, 'warning');
                try { await withTimeout(chrome.tabs.reload(tabId, { bypassCache: true }), 8000, 'reload'); } catch (e) { }
            }

            state.lastActivity = Date.now();
            await sleep(CONFIG.POLL_INTERVAL);
        }

        if (!ready) {
            let extra = '';
            if (lastProbe === null) extra = '（脚本无法注入，可能被重定向到同意页/错误页）';
            else if (!lastProbe.hasContainer) extra = `（readyState=${lastProbe.readyState}，表格容器未出现）`;
            throw new Error('等待表格数据超时' + extra);
        }

        await sleep(CONFIG.POST_READY_DELAY);

        const res = await safeExec(tabId, pageExtract, [task.category]);
        if (!res) throw new Error('抓取脚本无返回（页面可能已跳转）');
        if (!res.success) throw new Error(res.message || '抓取失败');
        if (!res.data || res.data.length === 0) throw new Error('抓取到 0 条数据');

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
            log(`[${task.category} #${task.id + 1}] ✅ 获取 ${data.length} 条  (${doneCount()}/${state.tasks.length})`, 'success');
            await saveState(true);
            return;
        } catch (e) {
            task.error = e.message;
            log(`[${task.category} #${task.id + 1}] 第 ${attempt} 次失败: ${e.message}`, 'error');
            await saveState();

            if (!state.running) return;

            if (attempt >= CONFIG.MAX_ATTEMPTS_PER_ROUND) {
                task.status = 'failed';
                log(`[${task.category} #${task.id + 1}] 本轮暂时放弃，稍后整体重试`, 'warning');
                await saveState(true);
                return;
            }
            const delay = Math.min(CONFIG.RETRY_BASE_DELAY * attempt, CONFIG.RETRY_MAX_DELAY);
            log(`[${task.category} #${task.id + 1}] ${Math.round(delay / 1000)} 秒后重试...`, 'warning');
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
            // 把上次被中断的 running 任务重新入队
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
                break; // 全部完成，或轮次用尽
            }

            // 并发执行
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
function toText(rows) {
    let s = '';
    for (const r of rows) s += `${r.symbol}: ${r.marketCap}, ${r.category}, ${r.price}, ${r.volume}\n`;
    return s;
}

function toDataUrl(text) {
    const bytes = new TextEncoder().encode(text);
    let bin = '';
    const CHUNK = 0x8000;
    for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    return 'data:text/plain;base64,' + btoa(bin);
}

async function downloadText(filename, text) {
    const url = toDataUrl(text);
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
    for (const t of state.tasks) {
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
        log(`⚠️ 有 ${failed.length} 个页面最终未成功：${failed.map(t => t.category + '#' + (t.id + 1)).join(', ')}`, 'warning');
    }

    if (all.length === 0) {
        log('未收集到任何数据，不生成文件', 'error');
    } else {
        const above = all.filter(r => typeof r.marketCap === 'number' && r.marketCap >= 5e9);
        const below = all.filter(r => !(typeof r.marketCap === 'number' && r.marketCap >= 5e9));
        const d = dateStr();
        log(`共 ${all.length} 条（去重后）：above ${above.length} / below ${below.length}`, 'final');
        try {
            if (above.length) await downloadText(`screener_above_${d}.txt`, toText(above));
            if (below.length) await downloadText(`screener_below_${d}.txt`, toText(below));
        } catch (e) {
            log('下载阶段异常: ' + e.message, 'error');
        }
    }

    state.running = false;
    state.finished = true;
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

    // 关掉上一轮遗留标签
    if (state) { state.running = false; await cleanupOrphanTabs(); }

    state = {
        running: true,
        finished: false,
        startedAt: Date.now(),
        finishedAt: 0,
        round: 1,
        logSeq: 0,
        logs: [],
        openTabIds: [],
        lastActivity: Date.now(),
        tasks: URLS.map((u, i) => ({
            id: i, url: u.url, category: u.category,
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
    // popup 的 ping 也顺便帮 SW 保活
    port.onMessage.addListener(() => { });
    resumeIfNeeded();
});

chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    (async () => {
        try {
            if (req.action === 'start') {
                const s = await loadState();
                const canAuto = !s || (!s.running &&
                    (!s.finishedAt || Date.now() - s.finishedAt > CONFIG.AUTO_RESTART_AFTER_MS));
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