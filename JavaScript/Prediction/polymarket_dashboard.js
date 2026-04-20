// ============ State ============
let mainTabId = null;
const params = new URLSearchParams(window.location.search);
mainTabId = parseInt(params.get('mainTabId'), 10);
const autoStart = params.get('auto') === '1';

let scrapedCards = null;
let isRunning = false;
let cooldownUntil = 0;
let globalFailures = [];
let globalResults = [];

// ============ DOM ============
const statusEl = document.getElementById('status');
const debugLogEl = document.getElementById('debugLog');
const progressContainer = document.getElementById('progressContainer');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const startBtn = document.getElementById('startBtn');
const retryBtn = document.getElementById('retryBtn');
const clearBtn = document.getElementById('clearBtn');

// ============ Utilities ============
function getTimestampedFilename(base) {
    var d = new Date();
    var yy = String(d.getFullYear()).slice(-2);
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    var dd = String(d.getDate()).padStart(2, '0');
    return base + '_' + yy + mm + dd + '.json';
}

function parseVolumeStr(v) {
    if (!v) return 0;
    var s = v.trim().toLowerCase().replace(/\$/g, '').replace(/vol\.?/gi, '').replace(/,/g, '').trim();
    var multiplier = 1;
    if (/[\d.]\s*b/.test(s)) { multiplier = 1e9; s = s.replace(/\s*b.*$/, '').trim(); }
    else if (/[\d.]\s*m/.test(s)) { multiplier = 1e6; s = s.replace(/\s*m.*$/, '').trim(); }
    else if (/[\d.]\s*k/.test(s)) { multiplier = 1e3; s = s.replace(/\s*k.*$/, '').trim(); }
    var num = parseFloat(s);
    return isNaN(num) ? 0 : Math.round(num * multiplier);
}

function log(message, type) {
    if (!type) type = 'info';
    var cls = { info: 'log-info', warn: 'log-warn', error: 'log-error', data: 'log-data', section: 'log-section', dim: 'log-dim' }[type] || '';
    var time = new Date().toLocaleTimeString();
    var span = document.createElement('span');
    span.className = cls;
    span.textContent = '[' + time + '] ' + message + '\n';
    debugLogEl.appendChild(span);
    debugLogEl.scrollTop = debugLogEl.scrollHeight;
}

function setStatus(text, type) {
    if (!type) type = 'info';
    statusEl.textContent = text;
    statusEl.className = 'status-box status-' + type;
}

function updateProgress(current, total, name) {
    progressContainer.style.display = 'block';
    progressFill.style.width = Math.round((current / total) * 100) + '%';
    progressText.textContent = '(' + current + '/' + total + ') ' + name;
}

function createTab(url, active) {
    if (active === undefined) active = true;
    return new Promise(function (resolve, reject) {
        chrome.tabs.create({ url: url, active: active }, function (tab) {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
            else resolve(tab);
        });
    });
}

function navigateAndWait(tabId, url, timeoutMs) {
    if (!timeoutMs) timeoutMs = 15000;
    return new Promise(function (resolve, reject) {
        var isDone = false;
        var timeout = setTimeout(function () {
            if (!isDone) { isDone = true; chrome.tabs.onUpdated.removeListener(listener); resolve(false); }
        }, timeoutMs);
        function listener(id, info) {
            if (id === tabId && info.status === 'complete') {
                if (!isDone) { isDone = true; chrome.tabs.onUpdated.removeListener(listener); clearTimeout(timeout); resolve(true); }
            }
        }
        chrome.tabs.onUpdated.addListener(listener);
        chrome.tabs.update(tabId, { url: url }, function () {
            if (chrome.runtime.lastError) {
                if (!isDone) { isDone = true; chrome.tabs.onUpdated.removeListener(listener); clearTimeout(timeout); reject(new Error(chrome.runtime.lastError.message)); }
            }
        });
    });
}

async function pollForContent(tabId, maxMs) {
    if (!maxMs) maxMs = 10000;
    var start = Date.now();
    while (Date.now() - start < maxMs) {
        try {
            var r = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                func: function () {
                    // 页面就绪条件：h1 存在 或 有 accordion 或 有 "% chance" 或 "resolved" 按钮
                    var h1 = document.querySelector('h1');
                    var acc = document.querySelectorAll('[data-scroll-anchor*="event-detail-accordion"]');
                    var bodyText = (document.body && document.body.innerText) || '';
                    var hasChance = /% chance/.test(bodyText);
                    var hasNumberFlow = !!document.querySelector('number-flow-react');
                    var hasResolved = /View\s+resolved/i.test(bodyText);
                    var hasGamingSidebar = document.querySelectorAll('a[href*="/esports/"]').length >= 3;
                    var isBot = !!document.getElementById('challenge-form') || document.title.toLowerCase().includes('just a moment');
                    return {
                        hasContent: !!h1 && (acc.length > 0 || hasChance || hasNumberFlow || hasGamingSidebar || bodyText.length > 500),
                        isBotPage: isBot
                    };
                }
            });
            var c = r && r[0] && r[0].result;
            if (c && c.hasContent) {
                await new Promise(function (res) { setTimeout(res, 300); });
                return { ready: true, isBotPage: false };
            }
            if (c && c.isBotPage) await new Promise(function (res) { setTimeout(res, 1500); });
            else await new Promise(function (res) { setTimeout(res, 250); });
        } catch (e) { await new Promise(function (res) { setTimeout(res, 300); }); }
    }
    return { ready: false, isBotPage: false };
}

function closeTab(tabId) {
    return new Promise(function (resolve) {
        chrome.tabs.remove(tabId, function () {
            if (chrome.runtime.lastError) { }
            resolve();
        });
    });
}

function saveJsonFile(data, filename) {
    try {
        var jsonStr = JSON.stringify(data, null, 2);
        var blob = new Blob([jsonStr], { type: 'application/json' });
        var blobUrl = URL.createObjectURL(blob);
        chrome.downloads.download({ url: blobUrl, filename: filename, conflictAction: 'overwrite', saveAs: false }, function () {
            if (chrome.runtime.lastError) log('  ⚠️ 保存失败: ' + chrome.runtime.lastError.message, 'warn');
            setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 5000);
        });
    } catch (e) { log('  ⚠️ 保存异常: ' + e.message, 'warn'); }
}

function saveTextFile(text, filename) {
    try {
        var blob = new Blob([text], { type: 'text/plain' });
        var blobUrl = URL.createObjectURL(blob);
        chrome.downloads.download({ url: blobUrl, filename: filename, conflictAction: 'overwrite', saveAs: false }, function () {
            setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 5000);
        });
    } catch (e) { }
}

function generateFailureReport(failures) {
    var lines = [
        'Polymarket Scraper - 抓取异常(失败)记录',
        '生成时间: ' + new Date().toLocaleString(),
        '共 ' + failures.length + ' 个项目',
        '',
        '========================================'
    ];
    failures.forEach(function (f, fi) {
        lines.push('');
        lines.push('[' + (fi + 1) + '] ' + f.name);
        lines.push('    URL: ' + f.url);
        lines.push('    Volume: ' + f.volume);
        if (f.debugInfo && f.debugInfo.length > 0) lines.push('    Debug: ' + f.debugInfo.join(' | '));
        log('  ❌ "' + f.name + '" → ' + f.url, 'error');
    });
    lines.push('');
    lines.push('========================================');
    saveTextFile(lines.join('\n'), 'polymarket_failure.txt');
    log('📄 异常记录已保存到 polymarket_failure.txt', 'warn');
}

// ============================================================
//  注入函数：Polymarket 主页面抓取
// ============================================================
function injectedScrapePolymarketMainPage() {
    var predictions = [];
    function clean(t) { return (t || '').trim().replace(/\s+/g, ' '); }

    // 每一项都有一个 a.absolute.inset-0 覆盖层，href 指向 /event/slug
    var eventAnchors = document.querySelectorAll('a.absolute.inset-0[href^="/event/"]');

    eventAnchors.forEach(function (anchor) {
        try {
            var href = anchor.getAttribute('href');
            var cleanHref = href.split('#')[0].split('?')[0];

            // 向上找到包含整个项目的容器（含 title + breadcrumbs）
            var card = anchor.parentElement;
            var titleEl = null;
            for (var i = 0; i < 8 && card; i++) {
                titleEl = card.querySelector('p[class*="text-heading-lg"]');
                if (titleEl) break;
                card = card.parentElement;
            }
            if (!card || !titleEl) return;
            var name = clean(titleEl.textContent);

            // 面包屑 type/subtype
            var breadcrumbs = card.querySelectorAll('a[href^="/predictions/"]');
            var type = '', subtype = '';
            if (breadcrumbs.length >= 1) type = clean(breadcrumbs[0].textContent);
            if (breadcrumbs.length >= 2) subtype = clean(breadcrumbs[1].textContent);
            if (type && !subtype) subtype = type;

            // Volume：匹配 "$XXX Vol." 或 "$XXXM Vol."
            var volume = '';
            var candidates = card.querySelectorAll('p, span');
            for (var ci = 0; ci < candidates.length; ci++) {
                var txt = candidates[ci].textContent.trim();
                if (/^\$[\d.,]+\s*[KMB]?\s*Vol\.?$/i.test(txt)) { volume = clean(txt); break; }
            }

            // 首页概率值（% chance 型子页面会用到）
            var homePercentage = '';
            var pctEl = card.querySelector('p[title][class*="text-heading-2xl"]');
            if (pctEl) {
                var titleAttr = pctEl.getAttribute('title') || '';
                var txtV = pctEl.textContent.trim();
                if (/^\d+(\.\d+)?%$/.test(titleAttr)) homePercentage = titleAttr;
                else homePercentage = clean(txtV);
            }

            predictions.push({
                name: name,
                type: type,
                subtype: subtype,
                volume: volume,
                subUrl: cleanHref,
                homePercentage: homePercentage
            });
        } catch (e) { }
    });

    // 去重
    var seen = {}, unique = [];
    predictions.forEach(function (p) {
        if (!seen[p.subUrl]) { seen[p.subUrl] = true; unique.push(p); }
    });
    return unique;
}

// ============================================================
//  注入函数：Polymarket 子页面抓取（修复了 Multi 误判为 Chance 的问题）
// ============================================================
function injectedScrapePolymarketSubpage() {
    var result = {
        pageType: 'unknown',
        enddate: '',
        options: [],
        subpagePercentage: '',
        debug: []
    };

    // ━━━━━━━━━━━━ Check 2: gaming ━━━━━━━━━━━━
    var esportsLinks = document.querySelectorAll('a[href*="/esports/"]');
    if (esportsLinks.length >= 3) {
        result.pageType = 'gaming';
        result.debug.push('Found ' + esportsLinks.length + ' esports links → 跳过');
        return result;
    }
    var ucHeaders = document.querySelectorAll('p[class*="uppercase"]');
    // 定义需要过滤的关键词列表
    var filterKeywords = ['games', 'all sports'];
    for (var i = 0; i < ucHeaders.length; i++) {
        var text = ucHeaders[i].textContent.trim().toLowerCase();
        if (filterKeywords.includes(text)) {
            result.pageType = 'gaming'; // 注意：这里根据你的逻辑保持不变，或者你可能需要根据不同关键词设置不同的 pageType
            result.debug.push('Found "' + text + '" header → 跳过');
            return result;
        }
    }

    // ━━━━━━━━━━━━ 提取 enddate ━━━━━━━━━━━━
    var monthRe = /^(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}$/i;
    var allSpans = document.querySelectorAll('span');
    for (var i = 0; i < allSpans.length; i++) {
        var st = allSpans[i].textContent.trim();
        if (monthRe.test(st)) { result.enddate = st; break; }
    }
    if (!result.enddate) {
        var bodyText0 = (document.body && document.body.innerText) || '';
        var m = bodyText0.match(/\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b/);
        if (m) result.enddate = m[0];
    }

    // ━━━━━━━━━━━━ 核心修复：优先判断是否为 Multi 页面 ━━━━━━━━━━━━
    var accItems = document.querySelectorAll('[data-scroll-anchor*="event-detail-accordion"]');

    // 如果有手风琴列表，绝对是 Multi 页面，跳过 Chance 的判断
    if (accItems.length === 0) {
        // ━━━━━━━━━━━━ Check 3: "% chance" 单选项页 ━━━━━━━━━━━━
        var bodyText = (document.body && document.body.innerText) || '';
        var hasChanceText = bodyText.indexOf('% chance') !== -1;

        var numberFlowEls = document.querySelectorAll('number-flow-react');

        var shadowChanceFound = false;
        for (var nf = 0; nf < numberFlowEls.length; nf++) {
            try {
                var sr = numberFlowEls[nf].shadowRoot;
                if (sr) {
                    var sText = sr.textContent || '';
                    if (sText.indexOf('chance') !== -1) {
                        shadowChanceFound = true;
                        break;
                    }
                }
            } catch (e) { }
        }

        var spanChanceFound = false;
        if (!hasChanceText && !shadowChanceFound) {
            for (var i = 0; i < allSpans.length; i++) {
                if (allSpans[i].textContent.trim() === '% chance') {
                    spanChanceFound = true;
                    break;
                }
            }
        }

        var likelyChanceByStructure = (numberFlowEls.length >= 1);
        var isChancePage = hasChanceText || shadowChanceFound || spanChanceFound || likelyChanceByStructure;

        if (isChancePage) {
            result.pageType = 'chance';
            var pct = '';

            for (var nf2 = 0; nf2 < numberFlowEls.length; nf2++) {
                try {
                    var sr2 = numberFlowEls[nf2].shadowRoot;
                    if (!sr2) continue;
                    var digitEls = sr2.querySelectorAll('[part*="integer-digit"]');
                    if (digitEls.length === 0) continue;

                    var digitVals = [];
                    digitEls.forEach(function (d) {
                        var style = d.getAttribute('style') || '';
                        var mc = style.match(/--current\s*:\s*(\d+)/);
                        if (mc) digitVals.push(mc[1]);
                    });
                    if (digitVals.length > 0) {
                        pct = digitVals.join('') + '%';
                        break;
                    }

                    var sTxt = (sr2.textContent || '').replace(/\s+/g, ' ').trim();
                    var mNum = sTxt.match(/(\d+(?:\.\d+)?)\s*%/);
                    if (mNum) {
                        pct = mNum[1] + '%';
                        break;
                    }
                } catch (e) { }
            }

            if (!pct) {
                var bigPs = document.querySelectorAll('p[title][class*="text-heading-2xl"]');
                for (var bi = 0; bi < bigPs.length; bi++) {
                    var titleA = bigPs[bi].getAttribute('title') || '';
                    if (/^\d+(\.\d+)?%$/.test(titleA)) { pct = titleA; break; }
                    var tx = bigPs[bi].textContent.trim();
                    if (/^\d+(\.\d+)?%$/.test(tx)) { pct = tx; break; }
                }
            }

            if (!pct) {
                var mBody = bodyText.match(/(\d+(?:\.\d+)?)\s*%\s*chance/i);
                if (mBody) pct = mBody[1] + '%';
            }

            result.subpagePercentage = pct;
            return result;
        }
    }

    // ━━━━━━━━━━━━ 默认：多选项手风琴 ━━━━━━━━━━━━
    result.pageType = 'multi';
    result.debug.push('accordion items: ' + accItems.length);

    accItems.forEach(function (item) {
        try {
            // 选项名
            var nameEl = item.querySelector('p.font-semibold[class*="text-heading-lg"]') ||
                item.querySelector('p[class*="text-heading-lg"]');
            if (!nameEl) return;
            var optName = nameEl.textContent.trim().replace(/\s+/g, ' ');
            if (!optName) return;

            // 选项值
            var valEl = item.querySelector('p[class*="text-heading-2xl"]');
            if (!valEl) {
                var allP = item.querySelectorAll('p');
                for (var pi = 0; pi < allP.length; pi++) {
                    var v = allP[pi].textContent.trim();
                    if (/^\d+(\.\d+)?%$/.test(v)) { valEl = allP[pi]; break; }
                }
            }
            if (!valEl) return;
            var value = valEl.textContent.trim().replace(/\s+/g, ' ');

            // 丢弃 <1% / 1%
            if (value === '<1%' || value === '1%') return;

            result.options.push({ name: optName, value: value });
        } catch (e) { }
    });

    // Fallback：如果 accordion 抓不到，兜底从全页面找 name+value 对
    if (result.options.length === 0) {
        result.debug.push('No accordion options, trying fallback...');
        var nameEls = document.querySelectorAll('p.font-semibold[class*="text-heading-lg"]');
        nameEls.forEach(function (nEl) {
            var n = nEl.textContent.trim().replace(/\s+/g, ' ');
            if (!n || n.length > 100) return;
            var cont = nEl.parentElement;
            for (var j = 0; j < 6 && cont; j++) {
                var vEl = cont.querySelector('p[class*="text-heading-2xl"]');
                if (vEl && !nEl.contains(vEl)) {
                    var v = vEl.textContent.trim();
                    if (v && v !== '<1%' && v !== '1%' && /\d/.test(v)) {
                        result.options.push({ name: n, value: v });
                    }
                    break;
                }
                cont = cont.parentElement;
            }
        });
    }

    return result;
}

// ============================================================
//  Phase 1: 抓主页面卡片
// ============================================================
async function scrapeMainPage() {
    if (isRunning) return;
    isRunning = true;
    startBtn.disabled = true;
    retryBtn.style.display = 'none';
    startBtn.textContent = '正在抓取主页面...';
    debugLogEl.innerHTML = '';
    scrapedCards = null;
    if (chrome.power) chrome.power.requestKeepAwake('display');

    log('════════════════════════════════════════', 'section');
    log('  Polymarket Scraper - Phase 1: 抓主页面', 'section');
    log('════════════════════════════════════════', 'section');
    log('mainTabId=' + mainTabId);

    try {
        await new Promise(function (res, rej) {
            chrome.tabs.get(mainTabId, function (t) {
                if (chrome.runtime.lastError) rej(new Error(chrome.runtime.lastError.message));
                else res(t);
            });
        });
    } catch (e) {
        log('❌ 主标签页不存在: ' + e.message, 'error');
        setStatus('错误: Polymarket 主标签页已关闭', 'error');
        startBtn.disabled = false; isRunning = false;
        if (chrome.power) chrome.power.releaseKeepAwake();
        return;
    }

    setStatus('正在抓取主页面...');

    try {
        var r = await chrome.scripting.executeScript({
            target: { tabId: mainTabId },
            func: injectedScrapePolymarketMainPage
        });
        var cards = r && r[0] && r[0].result;
        if (!cards || cards.length === 0) {
            log('❌ 主页面未找到卡片', 'error');
            setStatus('主页面未找到数据，请确认已滚动加载完成', 'error');
            startBtn.disabled = false; startBtn.textContent = '重新抓取主页面';
            isRunning = false;
            if (chrome.power) chrome.power.releaseKeepAwake();
            return;
        }

        cards.forEach(function (c) {
            c.volumeNum = parseVolumeStr(c.volume);
            c.volume = String(c.volumeNum);
        });

        log('✅ 找到 ' + cards.length + ' 个项目', 'info');
        cards.slice(0, 10).forEach(function (c, i) {
            log('  [' + i + '] "' + c.name + '" vol:' + c.volume + ' hPct:' + (c.homePercentage || '-') + ' type:' + c.type, 'data');
        });
        if (cards.length > 10) log('  ... 还有 ' + (cards.length - 10) + ' 个', 'dim');

        scrapedCards = cards;
        setStatus('✅ 主页面抓取完成，共 ' + cards.length + ' 个项目。请配置参数后点击「开始抓取」', 'success');
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';
    } catch (e) {
        log('❌ 主页面脚本失败: ' + e.message, 'error');
        setStatus('主页面抓取失败', 'error');
        startBtn.disabled = false; startBtn.textContent = '重新抓取主页面';
    }

    isRunning = false;
    if (chrome.power) chrome.power.releaseKeepAwake();
}

// ============================================================
//  Worker：并行抓子页面
// ============================================================
async function workerLoop(workerId, tabId, queue, results, config) {
    while (queue.length > 0) {
        // 共享冷却
        if (Date.now() < cooldownUntil) {
            var waitMs = cooldownUntil - Date.now();
            if (waitMs > 500) {
                log('[W' + workerId + '] ⏸️ 冷却中，等待 ' + Math.ceil(waitMs / 1000) + 's', 'warn');
                await new Promise(function (res) { setTimeout(res, waitMs); });
                if (Date.now() >= cooldownUntil) setStatus('抓取中...');
            }
        }

        var item = queue.shift();
        if (!item) break;
        var card = item.card;
        var idx = item.index;
        var short = card.name.length > 35 ? card.name.substring(0, 35) + '...' : card.name;
        var sub = null;

        try {
            var maxAttempts = 3;
            for (var attempt = 1; attempt <= maxAttempts; attempt++) {
                if (Date.now() < cooldownUntil) {
                    await new Promise(function (res) { setTimeout(res, cooldownUntil - Date.now()); });
                }

                if (attempt > 1) {
                    var retryDelay = 3000 * attempt + Math.floor(Math.random() * 4000);
                    log('[W' + workerId + '] 🔄 重试#' + (attempt - 1) + ' "' + short + '" (等待' + Math.round(retryDelay / 1000) + 's)', 'warn');
                    await new Promise(function (res) { setTimeout(res, retryDelay); });
                    try {
                        await chrome.scripting.executeScript({
                            target: { tabId: tabId },
                            func: function () { window.location.reload(true); }
                        });
                    } catch (e) {
                        chrome.tabs.reload(tabId, { bypassCache: true });
                    }
                    await new Promise(function (res) { setTimeout(res, 2000); });
                } else {
                    await navigateAndWait(tabId, 'https://polymarket.com' + card.subUrl, 15000);
                }

                var poll = await pollForContent(tabId, attempt === 1 ? 10000 : 15000);
                if (!poll.ready) {
                    if (poll.isBotPage) {
                        cooldownUntil = Math.max(cooldownUntil, Date.now() + 30000);
                        log('[W' + workerId + '] 🛡️ 反爬虫页面! 冷却30s', 'warn');
                        try {
                            await new Promise(function (r) { chrome.tabs.update(tabId, { active: true }, r); });
                        } catch (e) { }
                        await new Promise(function (res) { setTimeout(res, 25000); });
                        poll = await pollForContent(tabId, 15000);
                    }
                    if (!poll.ready) {
                        if (attempt < maxAttempts) continue;
                        log('[W' + workerId + '] ❌ "' + short + '" 加载超时', 'error');
                        sub = null;
                        break;
                    }
                }

                // 多等一会，让 React 完成渲染
                await new Promise(function (res) { setTimeout(res, 800); });

                var scrapeR = await chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    func: injectedScrapePolymarketSubpage
                });
                sub = (scrapeR && scrapeR[0] && scrapeR[0].result) || null;

                if (sub && sub.debug && sub.debug.length > 0) {
                    sub.debug.forEach(function (m) { log('[W' + workerId + ']   → ' + m, 'dim'); });
                }

                if (sub && (
                    sub.pageType === 'gaming' ||
                    (sub.pageType === 'chance' && sub.subpagePercentage) ||
                    (sub.pageType === 'multi' && sub.options && sub.options.length > 0)
                )) {
                    break;
                }

                if (sub && sub.pageType === 'chance' && !sub.subpagePercentage && card.homePercentage) {
                    log('[W' + workerId + ']   ℹ️ chance 页未抓到百分比, 将回退用 homePercentage=' + card.homePercentage, 'dim');
                    break;
                }
            }

            // ═══ 根据 pageType 组装结果 ═══
            if (!sub) {
                results[idx] = null;
                config.failures.push({
                    name: card.name,
                    url: 'https://polymarket.com' + card.subUrl,
                    volume: card.volume,
                    debugInfo: ['Failed to load or scrape subpage'],
                    card: card, index: idx
                });
            } else if (sub.pageType === 'gaming') {
                log('[W' + workerId + '] ⏭️ "' + short + '" 跳过 (' + sub.pageType + ')', 'dim');
                results[idx] = null; // 不写入
            } else if (sub.pageType === 'chance') {
                var pct = sub.subpagePercentage || card.homePercentage || '';
                var pctSource = sub.subpagePercentage ? 'subpage' : (card.homePercentage ? 'home' : 'none');

                if (!pct) {
                    log('[W' + workerId + '] ⏭️ "' + short + '" chance 无有效百分比 (sub=' + (sub.subpagePercentage || '-') + ', home=' + (card.homePercentage || '-') + ')', 'dim');
                    results[idx] = null;
                    config.failures.push({
                        name: card.name,
                        url: 'https://polymarket.com' + card.subUrl,
                        volume: card.volume,
                        debugInfo: [
                            'chance page but no percentage',
                            'sub=' + (sub.subpagePercentage || '-'),
                            'home=' + (card.homePercentage || '-')
                        ].concat(sub.debug || []),
                        card: card, index: idx
                    });
                } else {
                    results[idx] = {
                        name: card.name,
                        type: card.type,
                        subtype: card.subtype,
                        volume: card.volume,
                        enddate: sub.enddate || '',
                        option1: 'Chance',
                        value1: pct,
                        hide: "1"
                    };
                    log('[W' + workerId + '] ✅ "' + short + '" [chance/' + pctSource + '] = ' + pct, 'info');
                }
            } else if (sub.pageType === 'multi' && sub.options.length > 0) {
                var final = {
                    name: card.name,
                    type: card.type,
                    subtype: card.subtype,
                    volume: card.volume,
                    enddate: sub.enddate || '',
                    hide: "1"
                };
                sub.options.forEach(function (o, i) {
                    final['option' + (i + 1)] = o.name;
                    final['value' + (i + 1)] = o.value;
                });
                results[idx] = final;
                log('[W' + workerId + '] ✅ "' + short + '" [multi] ' + sub.options.length + ' opts', 'info');
            } else {
                // multi 但没抓到 options → 失败
                results[idx] = null;
                config.failures.push({
                    name: card.name,
                    url: 'https://polymarket.com' + card.subUrl,
                    volume: card.volume,
                    debugInfo: ['pageType=' + (sub && sub.pageType) + ', options=0'].concat(sub && sub.debug || []),
                    card: card, index: idx
                });
            }
        } catch (err) {
            log('[W' + workerId + '] ❌ "' + short + '": ' + err.message, 'error');
            results[idx] = null;
            config.failures.push({
                name: card.name,
                url: 'https://polymarket.com' + card.subUrl,
                volume: card.volume,
                debugInfo: ['Exception: ' + err.message],
                card: card, index: idx
            });

            try {
                await new Promise(function (resolve, reject) {
                    chrome.tabs.get(tabId, function () {
                        if (chrome.runtime.lastError) reject(new Error('gone')); else resolve();
                    });
                });
            } catch (e) {
                log('[W' + workerId + '] ⚠️ 标签页已关闭，退出', 'error');
                config.onProgress();
                break;
            }
        }

        config.onProgress();

        if (queue.length > 0) {
            var humanDelay = 3500 + Math.floor(Math.random() * 4000);
            log('[W' + workerId + '] ⏳ 节流 ' + (humanDelay / 1000).toFixed(1) + 's (剩 ' + queue.length + ')', 'dim');
            await new Promise(function (res) { setTimeout(res, humanDelay); });
        }
    }
    log('[W' + workerId + '] 🏁 完成', 'dim');
}

// ============================================================
//  Phase 2: 并行启动
// ============================================================
async function startSubpageScraping() {
    if (isRunning) return;
    isRunning = true;
    startBtn.disabled = true;
    retryBtn.style.display = 'none';
    startBtn.textContent = '抓取中...';
    cooldownUntil = 0;
    if (chrome.power) chrome.power.requestKeepAwake('display');

    var autoClose = document.getElementById('autoClose').checked;
    var doIncremental = document.getElementById('incrementalSaveToggle').checked;
    var concurrency = parseInt(document.getElementById('concurrencyInput').value, 10) || 2;
    if (concurrency < 1) concurrency = 1; if (concurrency > 8) concurrency = 8;

    var pauseInterval = parseInt(document.getElementById('pauseInterval').value, 10) || 0;
    var pauseDuration = parseInt(document.getElementById('pauseDuration').value, 10) || 3;

    var rangeInput = document.getElementById('rangeInput').value.trim();
    var startIndex = 0, endIndex = -1, hasRange = false;
    if (rangeInput) {
        if (rangeInput.includes('-')) {
            var parts = rangeInput.split('-').map(function (p) { return parseInt(p.trim(), 10); });
            if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1]) && parts[0] > 0 && parts[1] >= parts[0]) {
                startIndex = parts[0] - 1; endIndex = parts[1]; hasRange = true;
            }
        } else {
            var single = parseInt(rangeInput, 10);
            if (!isNaN(single) && single > 0) { startIndex = single - 1; endIndex = single; hasRange = true; }
        }
    }

    var minVolRaw = document.getElementById('minVolume').value.trim();
    var minVolume = minVolRaw === '' ? 100000 : parseInt(minVolRaw, 10);
    var hasMinVolume = !isNaN(minVolume) && minVolume > 0;

    var outputFilename = getTimestampedFilename('polymarket');
    var cards = scrapedCards.slice();

    log('', 'dim');
    log('════════════════════════════════════════', 'section');
    log('  Phase 2: 并行子页面抓取', 'section');
    log('════════════════════════════════════════', 'section');
    log('并行=' + concurrency + '  minVol=' + (hasMinVolume ? minVolume : '不限') +
        '  休息=' + (pauseInterval > 0 ? ('每' + pauseInterval + '个休' + pauseDuration + 'min') : '否'));
    log('📁 输出: ' + outputFilename, 'info');

    if (hasMinVolume) {
        var before = cards.length;
        cards = cards.filter(function (c) { return c.volumeNum >= minVolume; });
        log('📊 Volume 过滤: ' + before + ' → ' + cards.length, 'warn');
    }

    if (hasRange) {
        if (endIndex === -1 || endIndex > cards.length) endIndex = cards.length;
        if (startIndex >= cards.length) { cards = []; }
        else { cards = cards.slice(startIndex, endIndex); log('📊 范围: ' + (startIndex + 1) + '-' + endIndex, 'warn'); }
    }

    if (cards.length === 0) {
        setStatus('过滤后没有需要抓取的项目', 'error');
        startBtn.disabled = false; startBtn.textContent = '开始抓取';
        isRunning = false;
        if (chrome.power) chrome.power.releaseKeepAwake();
        return;
    }

    if (concurrency > cards.length) concurrency = cards.length;
    log('📋 最终 ' + cards.length + ' 项, ' + concurrency + ' worker', 'info');

    // 创建工作标签
    var workerTabIds = [];
    for (var w = 0; w < concurrency; w++) {
        try {
            var tab = await createTab('about:blank', false);
            workerTabIds.push(tab.id);
        } catch (e) { log('  ⚠️ 创建标签失败: ' + e.message, 'warn'); }
    }

    if (workerTabIds.length === 0) {
        setStatus('错误: 无法创建标签页', 'error');
        startBtn.disabled = false; isRunning = false;
        if (chrome.power) chrome.power.releaseKeepAwake();
        return;
    }

    var queue = [];
    for (var i = 0; i < cards.length; i++) queue.push({ card: cards[i], index: i });

    globalResults = new Array(cards.length);
    globalFailures = [];
    var completedCount = 0, lastSaveCount = 0;
    var scrapeStartTime = Date.now();

    function onProgress() {
        completedCount++;
        var pct = Math.round((completedCount / cards.length) * 100);
        updateProgress(completedCount, cards.length, completedCount + '/' + cards.length + ' (' + pct + '%)');

        if (pauseInterval > 0 && completedCount % pauseInterval === 0 && completedCount < cards.length) {
            var pauseMs = pauseDuration * 60 * 1000;
            cooldownUntil = Math.max(cooldownUntil, Date.now() + pauseMs);
            log('⏸️ 休息 ' + pauseDuration + ' 分钟...', 'warn');
        }

        if (Date.now() < cooldownUntil) {
            setStatus('休息中... 剩 ' + Math.ceil((cooldownUntil - Date.now()) / 60000) + ' 分钟', 'warn');
        } else {
            setStatus('抓取中: ' + completedCount + '/' + cards.length + ' (' + pct + '%)');
        }

        if (doIncremental && completedCount - lastSaveCount >= 10) {
            var partial = globalResults.filter(function (r) { return r; });
            saveJsonFile(partial, outputFilename);
            log('💾 增量保存 (' + partial.length + '条)', 'data');
            lastSaveCount = completedCount;
        }
    }

    var workerPromises = workerTabIds.map(async function (tabId, w) {
        if (w > 0) await new Promise(function (res) { setTimeout(res, w * 5000); });
        return workerLoop(w, tabId, queue, globalResults, {
            onProgress: onProgress,
            failures: globalFailures
        });
    });

    await Promise.all(workerPromises);

    if (autoClose) {
        for (var w = 0; w < workerTabIds.length; w++) await closeTab(workerTabIds[w]);
    }

    try {
        var dashTab = await new Promise(function (resolve) { chrome.tabs.getCurrent(function (t) { resolve(t); }); });
        if (dashTab) chrome.tabs.update(dashTab.id, { active: true });
    } catch (e) { }

    var finalResults = globalResults.filter(function (r) { return r; });
    var elapsed = Math.round((Date.now() - scrapeStartTime) / 1000);

    log('', 'dim');
    log('════════════════════════════════════════', 'section');
    log('  完成! ' + finalResults.length + '条, 耗时 ' + elapsed + 's', 'section');
    log('════════════════════════════════════════', 'section');

    saveJsonFile(finalResults, outputFilename);
    log('💾 最终保存: ' + outputFilename + ' (' + finalResults.length + '条)', 'data');

    if (globalFailures.length > 0) {
        log('⚠️ ' + globalFailures.length + ' 个失败项', 'warn');
        generateFailureReport(globalFailures);
        retryBtn.style.display = 'inline-block';
        retryBtn.textContent = '纠错 (' + globalFailures.length + '个失败项)';
    }

    // 通知 .scpt
    try {
        var doneBlob = new Blob(['done'], { type: 'text/plain' });
        var doneUrl = URL.createObjectURL(doneBlob);
        chrome.downloads.download({
            url: doneUrl,
            filename: 'polymarket_scraping_done.txt',
            conflictAction: 'overwrite',
            saveAs: false
        }, function () { setTimeout(function () { URL.revokeObjectURL(doneUrl); }, 5000); });
    } catch (e) { }

    progressContainer.style.display = 'none';
    var msg = '✅ 完成! ' + finalResults.length + ' 条, 耗时 ' + elapsed + 's → ' + outputFilename;
    if (globalFailures.length > 0) msg += '  ⚠️ ' + globalFailures.length + ' 个异常';
    setStatus(msg, 'success');

    scrapedCards = null;
    startBtn.disabled = false; startBtn.textContent = '重新开始';
    isRunning = false;
    if (chrome.power) chrome.power.releaseKeepAwake();
}

// ============================================================
//  纠错
// ============================================================
async function retryFailedItems() {
    if (isRunning || globalFailures.length === 0) return;
    isRunning = true;
    startBtn.disabled = true;
    retryBtn.disabled = true;
    retryBtn.textContent = '纠错中...';
    cooldownUntil = 0;
    if (chrome.power) chrome.power.requestKeepAwake('display');

    var concurrency = parseInt(document.getElementById('concurrencyInput').value, 10) || 2;
    if (concurrency > globalFailures.length) concurrency = globalFailures.length;
    var outputFilename = getTimestampedFilename('polymarket');

    log('', 'dim');
    log('════════════════════════════════════════', 'section');
    log('  纠错 (' + globalFailures.length + ' 项)', 'section');
    log('════════════════════════════════════════', 'section');

    var workerTabIds = [];
    for (var w = 0; w < concurrency; w++) {
        try { var tab = await createTab('about:blank', false); workerTabIds.push(tab.id); } catch (e) { }
    }

    var queue = globalFailures.map(function (f) { return { card: f.card, index: f.index }; });
    var totalRetrying = globalFailures.length;
    globalFailures = [];
    var completedCount = 0, scrapeStartTime = Date.now();

    function onProgress() {
        completedCount++;
        updateProgress(completedCount, totalRetrying, '纠错 ' + completedCount + '/' + totalRetrying);
        setStatus('纠错中: ' + completedCount + '/' + totalRetrying);
    }

    var workerPromises = workerTabIds.map(async function (tabId, w) {
        if (w > 0) await new Promise(function (res) { setTimeout(res, w * 5000); });
        return workerLoop(w, tabId, queue, globalResults, { onProgress: onProgress, failures: globalFailures });
    });

    await Promise.all(workerPromises);

    if (document.getElementById('autoClose').checked) {
        for (var w = 0; w < workerTabIds.length; w++) await closeTab(workerTabIds[w]);
    }

    var finalResults = globalResults.filter(function (r) { return r; });
    saveJsonFile(finalResults, outputFilename);
    log('💾 纠错后保存 (' + finalResults.length + '条)', 'data');

    if (globalFailures.length > 0) {
        retryBtn.style.display = 'inline-block';
        retryBtn.disabled = false;
        retryBtn.textContent = '再次纠错 (' + globalFailures.length + ')';
        generateFailureReport(globalFailures);
    } else {
        retryBtn.style.display = 'none';
    }

    progressContainer.style.display = 'none';
    setStatus('✅ 纠错完成! 总 ' + finalResults.length + ' 条', 'success');
    startBtn.disabled = false; isRunning = false;
    if (chrome.power) chrome.power.releaseKeepAwake();
}

// ============ 事件 ============
startBtn.addEventListener('click', function () {
    if (isRunning) return;
    if (scrapedCards) startSubpageScraping();
    else scrapeMainPage();
});
retryBtn.addEventListener('click', retryFailedItems);
clearBtn.addEventListener('click', function () { debugLogEl.innerHTML = ''; log('日志已清空'); });

// ============ 初始化 ============
if (mainTabId && !isNaN(mainTabId)) {
    log('Dashboard 就绪. mainTabId=' + mainTabId);
    if (autoStart) {
        setStatus('正在自动抓取主页面...');
        setTimeout(scrapeMainPage, 500);
    } else {
        setStatus('就绪 — 点击按钮抓取主页面');
        startBtn.disabled = false;
        startBtn.textContent = '抓取主页面';
    }
} else {
    setStatus('错误: 请从 Polymarket 页面启动', 'error');
    startBtn.disabled = true;
}