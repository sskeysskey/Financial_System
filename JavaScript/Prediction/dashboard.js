// ============ 状态 ============
let mainTabId = null;
const params = new URLSearchParams(window.location.search);
mainTabId = parseInt(params.get('mainTabId'), 10);
const autoStart = params.get('auto') === '1';

let scrapedCards = null;
let isRunning = false;

// ============ DOM 引用 ============
const statusEl = document.getElementById('status');
const debugLogEl = document.getElementById('debugLog');
const progressContainer = document.getElementById('progressContainer');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const startBtn = document.getElementById('startBtn');
const clearBtn = document.getElementById('clearBtn');

// ============ 文件名工具（带日期戳） ============
function getTimestampedFilename(base) {
    var d = new Date();
    var yy = String(d.getFullYear()).slice(-2);
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    var dd = String(d.getDate()).padStart(2, '0');
    return base + '_' + yy + mm + dd + '.json';
}

// ============ Volume 解析工具 ============
function parseVolumeStr(v) {
    if (!v) return 0;
    var s = v.trim().toLowerCase()
        .replace(/\$/g, '')
        .replace(/vol\.?/gi, '')
        .replace(/,/g, '')
        .trim();
    var multiplier = 1;
    if (/[\d.]\s*b/.test(s)) { multiplier = 1e9; s = s.replace(/\s*b.*$/, '').trim(); }
    else if (/[\d.]\s*m/.test(s)) { multiplier = 1e6; s = s.replace(/\s*m.*$/, '').trim(); }
    else if (/[\d.]\s*k/.test(s)) { multiplier = 1e3; s = s.replace(/\s*k.*$/, '').trim(); }
    var num = parseFloat(s);
    return isNaN(num) ? 0 : Math.round(num * multiplier);
}

// ============ 子页面选项健康检查 ============
function isSubpageOptionsHealthy(subOptions, mainOptions) {
    if (!subOptions || subOptions.length === 0) return false;

    for (var i = 0; i < subOptions.length; i++) {
        var val = (subOptions[i].value || '').trim();
        if (val.length > 20) return false;
        if (!/\d/.test(val)) return false;
        var digits = val.replace(/[^0-9]/g, '');
        if (digits.length > 8) return false;
    }

    if (mainOptions && mainOptions.length >= 2 && subOptions.length < mainOptions.length) {
        return false;
    }

    return true;
}

// ============ 日志工具 ============
function log(message, type) {
    if (!type) type = 'info';
    var cls = {
        info: 'log-info', warn: 'log-warn', error: 'log-error',
        data: 'log-data', section: 'log-section', dim: 'log-dim'
    }[type] || '';
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

// ============ 标签页管理 ============
function createTab(url, active) {
    if (active === undefined) active = true;
    return new Promise(function (resolve, reject) {
        chrome.tabs.create({ url: url, active: active }, function (tab) {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
            } else {
                resolve(tab);
            }
        });
    });
}

function navigateAndWait(tabId, url, timeoutMs) {
    if (!timeoutMs) timeoutMs = 15000;
    return new Promise(function (resolve, reject) {
        var isDone = false;
        var timeout = setTimeout(function () {
            if (!isDone) {
                isDone = true;
                chrome.tabs.onUpdated.removeListener(listener);
                resolve(false);
            }
        }, timeoutMs);

        function listener(id, info) {
            if (id === tabId && info.status === 'complete') {
                if (!isDone) {
                    isDone = true;
                    chrome.tabs.onUpdated.removeListener(listener);
                    clearTimeout(timeout);
                    resolve(true);
                }
            }
        }

        chrome.tabs.onUpdated.addListener(listener);

        chrome.tabs.update(tabId, { url: url }, function (tab) {
            if (chrome.runtime.lastError) {
                if (!isDone) {
                    isDone = true;
                    chrome.tabs.onUpdated.removeListener(listener);
                    clearTimeout(timeout);
                    reject(new Error(chrome.runtime.lastError.message));
                }
            }
        });
    });
}

async function pollForContent(tabId, maxMs) {
    if (!maxMs) maxMs = 15000; // 增加默认超时时间
    var start = Date.now();
    while (Date.now() - start < maxMs) {
        try {
            var r = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                func: function () {
                    // 检查选项是否渲染
                    var opts = document.querySelectorAll('[class*="typ-body-x30"]');
                    var h1 = document.querySelector('h1');
                    var breadcrumbs = document.querySelectorAll('nav[aria-label="Breadcrumb"] li, ol li');

                    var isBotPage = !!document.getElementById('challenge-form') ||
                        !!document.querySelector('.cf-browser-verification') ||
                        document.title.toLowerCase().includes('just a moment') ||
                        !!document.querySelector('[id*="turnstile"]');

                    // 认为就绪的条件：有标题，且（有选项 或 有面包屑）
                    return {
                        hasContent: !!h1 && (opts.length > 0 || breadcrumbs.length > 0),
                        optionCount: opts.length,
                        isBotPage: isBotPage
                    };
                }
            });
            var c = r && r[0] && r[0].result;
            if (c && c.hasContent) {
                await new Promise(function (res) { setTimeout(res, 1000); }); // 多等一会确保渲染
                return { ready: true, isBotPage: false, elapsed: Date.now() - start, optionCount: c.optionCount };
            }
            if (c && c.isBotPage) {
                await new Promise(function (res) { setTimeout(res, 1500); });
            } else {
                await new Promise(function (res) { setTimeout(res, 500); });
            }
        } catch (e) {
            await new Promise(function (res) { setTimeout(res, 500); });
        }
    }
    return { ready: false, isBotPage: true, elapsed: Date.now() - start, optionCount: 0 };
}

async function pollForMoreOptions(tabId, prevCount, maxMs) {
    if (!maxMs) maxMs = 5000; // 增加超时
    var start = Date.now();
    while (Date.now() - start < maxMs) {
        try {
            var r = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                func: function () {
                    return document.querySelectorAll('[class*="typ-body-x30"]').length;
                }
            });
            var count = r && r[0] && r[0].result;
            if (count && count > prevCount) {
                await new Promise(function (res) { setTimeout(res, 500); });
                return { expanded: true, elapsed: Date.now() - start };
            }
        } catch (e) { }
        await new Promise(function (res) { setTimeout(res, 300); });
    }
    return { expanded: false, elapsed: Date.now() - start };
}

async function pollForCategories(tabId, maxMs) {
    if (!maxMs) maxMs = 3000;
    var start = Date.now();
    while (Date.now() - start < maxMs) {
        try {
            var r = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                func: function () {
                    var nav = document.querySelector('nav[aria-label="Breadcrumb"]');
                    if (nav) return nav.querySelectorAll('li').length;
                    return 0;
                }
            });
            var count = r && r[0] && r[0].result;
            if (count && count > 0) {
                return { found: true, count: count, elapsed: Date.now() - start };
            }
        } catch (e) { }
        await new Promise(function (res) { setTimeout(res, 200); });
    }
    return { found: false, count: 0, elapsed: Date.now() - start };
}

async function forceRenderContent(tabId) {
    try {
        await chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: function () {
                if (!document.getElementById('__cv_override__')) {
                    var s = document.createElement('style');
                    s.id = '__cv_override__';
                    s.textContent = '* { content-visibility: visible !important; contain-intrinsic-size: none !important; }';
                    document.head.appendChild(s);
                }
                window.scrollTo(0, document.body.scrollHeight);
            }
        });
    } catch (e) { }

    await new Promise(function (res) { setTimeout(res, 1000); });

    try {
        await chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: function () { window.scrollTo(0, 0); }
        });
    } catch (e) { }
}

function closeTab(tabId) {
    return new Promise(function (resolve) {
        chrome.tabs.remove(tabId, function () {
            if (chrome.runtime.lastError) { }
            resolve();
        });
    });
}

// ============ 下载工具 ============
function saveJsonFile(data, filename) {
    try {
        var jsonStr = JSON.stringify(data, null, 2);
        var blob = new Blob([jsonStr], { type: 'application/json' });
        var blobUrl = URL.createObjectURL(blob);
        chrome.downloads.download({
            url: blobUrl,
            filename: filename,
            conflictAction: 'overwrite',
            saveAs: false
        }, function (downloadId) {
            if (chrome.runtime.lastError) {
                log('  ⚠️ 保存失败: ' + chrome.runtime.lastError.message, 'warn');
            }
            setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 5000);
        });
    } catch (e) {
        log('  ⚠️ 保存异常: ' + e.message, 'warn');
    }
}

function saveTextFile(text, filename) {
    try {
        var blob = new Blob([text], { type: 'text/plain' });
        var blobUrl = URL.createObjectURL(blob);
        chrome.downloads.download({
            url: blobUrl,
            filename: filename,
            conflictAction: 'overwrite',
            saveAs: false
        }, function (downloadId) {
            if (chrome.runtime.lastError) {
                log('  ⚠️ 保存失败: ' + chrome.runtime.lastError.message, 'warn');
            }
            setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 5000);
        });
    } catch (e) {
        log('  ⚠️ 保存异常: ' + e.message, 'warn');
    }
}

// ============================================================
//  注入函数
// ============================================================

function injectedClickXMore() {
    var d = [];
    var clicked = false;
    var allElements = document.querySelectorAll('*');
    var morePattern = /^\d+\s+more$/i;

    for (var i = 0; i < allElements.length; i++) {
        var text = allElements[i].textContent.trim();
        if (morePattern.test(text)) {
            d.push('Found "' + text + '"');
            var target = allElements[i];
            if (target.tagName === 'BUTTON' ||
                target.getAttribute('role') === 'button' ||
                target.onclick ||
                (target.className && target.className.includes('cursor-pointer'))) {
                target.click();
                d.push('Clicked element directly');
                clicked = true;
                break;
            }
            var parent = target;
            for (var j = 0; j < 10; j++) {
                parent = parent.parentElement;
                if (!parent) break;
                if (parent.tagName === 'BUTTON' ||
                    parent.getAttribute('role') === 'button' ||
                    parent.onclick ||
                    (parent.className && (
                        parent.className.includes('cursor-pointer') ||
                        parent.className.includes('stretched-link')
                    ))) {
                    parent.click();
                    d.push('Clicked parent element');
                    clicked = true;
                    break;
                }
            }
            if (clicked) break;
        }
    }
    if (!clicked) {
        d.push('"X more" button NOT found');
    }
    return { clicked: clicked, debug: d };
}

function injectedScrapeMainPage() {
    var predictions = [];
    function clean(t) { return t.trim().replace(/\s+/g, ' '); }

    var cards = document.querySelectorAll('[data-testid="market-tile"]');
    cards.forEach(function (card) {
        try {
            var h2 = card.querySelector('h2');
            if (!h2) return;
            var name = clean(h2.textContent);

            var subLink = card.querySelector('a[href^="/markets/"]');
            if (!subLink) return;
            var subUrl = subLink.getAttribute('href');

            var volume = '';
            var spans = card.querySelectorAll('span');
            for (var si = 0; si < spans.length; si++) {
                var t = spans[si].textContent;
                if (t.includes('$') && t.toLowerCase().includes('vol')) {
                    volume = clean(t);
                    break;
                }
            }

            var options = [];
            card.querySelectorAll('.col-span-full').forEach(function (row) {
                var nameEl = row.querySelector('[class*="typ-body-x30"]');
                var btn = row.querySelector('button[class*="stretched-link-action"]');
                var valEl = btn ? btn.querySelector('span.tabular-nums') : null;
                if (nameEl && !valEl) {
                    var sb = row.querySelector('button.rounded-x50[class*="stretched-link-action"]');
                    if (sb) valEl = sb.querySelector('span.tabular-nums');
                }
                if (nameEl && valEl) {
                    var optName = clean(nameEl.textContent);
                    var v = clean(valEl.textContent);
                    var optNameLower = optName.toLowerCase().trim();
                    if (optNameLower === 'show less') return;
                    if (optNameLower === 'hide markets') return;
                    var cEl = row.querySelector('[class*="typ-emphasis-x10"]');
                    var change = cEl ? clean(cEl.textContent) : '';
                    options.push({ name: optName, value: v.includes('%') ? v : v + '%', change: change });
                }
            });

            if (options.length > 10) {
                options = options.filter(function (opt) {
                    return opt.value.trim() !== '<1%';
                });
            }

            predictions.push({ name: name, subUrl: subUrl, volume: volume, options: options });
        } catch (e) { }
    });
    return predictions;
}

function injectedClickMore() {
    var d = [];
    var allSpans = document.querySelectorAll('span');
    var morePattern = /more\s*markets/i;

    for (var i = 0; i < allSpans.length; i++) {
        var text = allSpans[i].textContent.trim().replace(/\s+/g, ' ');
        if (morePattern.test(text)) {
            d.push('Found "More markets" span');
            var target = allSpans[i].closest('[role="button"]');
            if (!target) {
                var p = allSpans[i];
                for (var j = 0; j < 10; j++) {
                    p = p.parentElement;
                    if (!p) break;
                    if (p.getAttribute('role') === 'button' ||
                        (p.className && p.className.includes('cursor-pointer')) ||
                        p.tagName === 'BUTTON') {
                        target = p;
                        break;
                    }
                }
            }
            if (target) {
                target.click();
                d.push('Clicked!');
                return { clicked: true, debug: d };
            } else {
                allSpans[i].click();
                d.push('Clicked span directly');
                return { clicked: true, debug: d };
            }
        }
    }
    d.push('"More markets" NOT found');
    return { clicked: false, debug: d };
}

function injectedScrapeSubpage() {
    var d = [];
    var result = { type: '', subtype: '', options: [], usedFallbackStrategy: false };
    var categories = [];

    try {
        // ★ 新策略：直接从 nav[aria-label="Breadcrumb"] 提取
        var breadcrumbNav = document.querySelector('nav[aria-label="Breadcrumb"]');
        if (breadcrumbNav) {
            var listItems = breadcrumbNav.querySelectorAll('li');
            listItems.forEach(function (li) {
                var text = li.textContent.trim().replace(/\s+/g, ' ');
                if (text && text !== '•' && text !== '·' && !text.toUpperCase().includes('REG TIME')) {
                    if (categories.indexOf(text) === -1) {
                        categories.push(text);
                    }
                }
            });
            if (categories.length > 0) {
                d.push('Found breadcrumbs in nav: ' + categories.join(' > '));
            }
        }

        // 如果没有找到，尝试旧的基于链接的策略
        if (categories.length === 0) {
            // ... (保留原有的提取策略作为兜底)
            var h1 = document.querySelector('h1');
            if (h1) {
                var h1Parent = h1.parentElement;
                if (h1Parent) {
                    var h1Siblings = h1Parent.children;
                    for (var i = 0; i < h1Siblings.length; i++) {
                        var sib = h1Siblings[i];
                        if (sib === h1) continue;
                        var links = sib.querySelectorAll('a');
                        for (var j = 0; j < links.length; j++) {
                            var aText = links[j].textContent.trim();
                            if (aText && aText !== '•' && aText !== '·' && categories.indexOf(aText) === -1) {
                                categories.push(aText);
                            }
                        }
                    }
                }
            }
        }

        if (categories.length === 1) {
            result.type = categories[0];
            result.subtype = categories[0];
        } else if (categories.length >= 2) {
            result.type = categories[0];
            result.subtype = categories[1];
        }

        var timeSubtypes = ['hourly', 'weekly', '15 min', '15min', 'annual', 'daily', 'monthly'];
        if (result.subtype && timeSubtypes.indexOf(result.subtype.toLowerCase()) !== -1) {
            result.subtype = result.type;
        }

    } catch (e) {
        d.push('Category extraction error: ' + e.message);
    }

    // ★ 选项抓取
    var seen = {};
    var root = document;

    // 查找所有包含选项名称的 span
    var nameEls = root.querySelectorAll('span[class*="typ-body-x30"], div[class*="typ-body-x30"]');

    nameEls.forEach(function (nameEl) {
        var rawName = nameEl.textContent.trim().replace(/\s+/g, ' ');
        if (!rawName) return;
        if (rawName.toLowerCase().indexOf('more market') !== -1) return;
        if (rawName.toLowerCase().indexOf('fewer market') !== -1) return;
        if (seen[rawName]) return;

        var container = nameEl;
        var valueEl = null;
        for (var i = 0; i < 15; i++) {
            container = container.parentElement;
            if (!container) break;
            valueEl = container.querySelector('h2[class*="typ-headline-x10"]');
            if (valueEl) break;
            valueEl = container.querySelector('[class*="typ-headline-x10"]');
            if (valueEl) break;
        }

        var value = valueEl ? valueEl.textContent.trim() : '';
        var changeEl = container ? container.querySelector('[class*="typ-emphasis-x10"]') : null;
        var change = changeEl ? changeEl.textContent.trim().replace(/\s+/g, ' ') : '';

        if (value) {
            seen[rawName] = true;
            result.options.push({ name: rawName, value: value, change: change });
        }
    });

    result.options = result.options.filter(function (opt) {
        var optName = opt.name.toLowerCase().trim();
        if (optName === 'show less') return false;
        if (optName === 'hide markets') return false;
        return true;
    });

    if (result.options.length > 10) {
        result.options = result.options.filter(function (opt) {
            return opt.value.trim() !== '<1%';
        });
    }

    result.debug = d;
    return result;
}

// ============ 备选数据 ============
function buildFallback(card) {
    var r = {
        name: card.name,
        type: '',
        subtype: '',
        volume: card.volume,
        hide: "1"
    };
    card.options.forEach(function (o, i) {
        r['option' + (i + 1)] = o.name;
        r['value' + (i + 1)] = o.value;
        if (o.change) r['change' + (i + 1)] = o.change;
    });
    return r;
}

// ============================================================
//  Phase 1: 抓取主页面卡片
// ============================================================
async function scrapeMainPage() {
    if (isRunning) return;
    isRunning = true;
    startBtn.disabled = true;
    startBtn.textContent = '正在抓取主页面...';
    debugLogEl.innerHTML = '';
    scrapedCards = null;

    if (chrome.power) chrome.power.requestKeepAwake('display');

    log('════════════════════════════════════════', 'section');
    log('  Kalshi Scraper - Phase 1: 抓取主页面', 'section');
    log('════════════════════════════════════════', 'section');

    try {
        await new Promise(function (res, rej) {
            chrome.tabs.get(mainTabId, function (t) {
                if (chrome.runtime.lastError) rej(new Error(chrome.runtime.lastError.message));
                else res(t);
            });
        });
    } catch (e) {
        log('❌ 主标签页不存在: ' + e.message, 'error');
        setStatus('错误: Kalshi 主标签页已关闭', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '重新抓取主页面';
        isRunning = false;
        if (chrome.power) chrome.power.releaseKeepAwake();
        return;
    }

    setStatus('正在抓取主页面...');

    try {
        var r = await chrome.scripting.executeScript({
            target: { tabId: mainTabId },
            func: injectedScrapeMainPage
        });
        var cards = r && r[0] && r[0].result;
        if (!cards || cards.length === 0) {
            log('❌ 主页面未找到卡片', 'error');
            setStatus('主页面未找到数据', 'error');
            startBtn.disabled = false;
            startBtn.textContent = '重新抓取主页面';
            isRunning = false;
            if (chrome.power) chrome.power.releaseKeepAwake();
            return;
        }

        cards.forEach(function (c) {
            c.volumeNum = parseVolumeStr(c.volume);
            c.volume = String(c.volumeNum);
        });

        var seenUrls = {};
        cards = cards.filter(function (c) {
            if (seenUrls[c.subUrl]) return false;
            seenUrls[c.subUrl] = true;
            return true;
        });

        log('✅ 找到 ' + cards.length + ' 个卡片', 'info');
        scrapedCards = cards;
        setStatus('✅ 主页面抓取完成，共 ' + cards.length + ' 个卡片。', 'success');
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';

    } catch (e) {
        log('❌ 主页面脚本失败: ' + e.message, 'error');
        setStatus('主页面抓取失败', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '重新抓取主页面';
    }

    isRunning = false;
    if (chrome.power) chrome.power.releaseKeepAwake();
}

// ============================================================
//  工作线程
// ============================================================
async function workerLoop(workerId, tabId, queue, results, config) {
    while (queue.length > 0) {
        var item = queue.shift();
        if (!item) break;

        var card = item.card;
        var idx = item.index;
        var short = card.name.length > 35 ? card.name.substring(0, 35) + '...' : card.name;
        var sub = null;

        try {
            var maxAttempts = 3;
            var poll = null;

            for (var attempt = 1; attempt <= maxAttempts; attempt++) {
                if (attempt > 1) {
                    var retryDelay = 2000 * attempt;
                    log('[W' + workerId + '] 🔄 重试#' + (attempt - 1) + ' "' + short + '"', 'warn');
                    await new Promise(function (res) { setTimeout(res, retryDelay); });
                }

                // 强制切到前台，解决 React 渲染问题
                try {
                    await new Promise(function (resolve) {
                        chrome.tabs.update(tabId, { active: true }, resolve);
                    });
                } catch (e) { }

                await navigateAndWait(tabId, 'https://kalshi.com' + card.subUrl, 15000);

                var pollTimeout = attempt === 1 ? 15000 : 20000;
                poll = await pollForContent(tabId, pollTimeout);

                if (!poll.ready) {
                    if (attempt < maxAttempts) continue;
                    log('[W' + workerId + '] ❌ "' + short + '" → 页面加载超时', 'error');
                    results[idx] = buildFallback(card);
                    break;
                }

                await forceRenderContent(tabId);
                await new Promise(function (res) { setTimeout(res, 2000); });

                // 尝试点击 "More markets"
                try {
                    var clickR = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: injectedClickMore
                    });
                    var clickD = (clickR && clickR[0] && clickR[0].result) || { clicked: false };
                    if (clickD.clicked) {
                        log('[W' + workerId + '] 🖱️ 点击了 More markets', 'dim');
                        await pollForMoreOptions(tabId, poll.optionCount, 5000);
                        await forceRenderContent(tabId); // 再次强制渲染
                        await new Promise(function (res) { setTimeout(res, 1500); });
                    }
                } catch (e) { }

                var scrapeR = await chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    func: injectedScrapeSubpage
                });
                sub = (scrapeR && scrapeR[0] && scrapeR[0].result) ||
                    { type: '', subtype: '', options: [], debug: [], usedFallbackStrategy: false };

                if (sub.type || sub.subtype || sub.options.length > 2) {
                    break; // 成功获取到数据
                }
            }

            if (sub !== null) {
                var final = {
                    name: card.name,
                    type: sub.type || '',
                    subtype: sub.subtype || '',
                    volume: card.volume,
                    hide: "1"
                };

                var subHealthy = isSubpageOptionsHealthy(sub.options, card.options);
                var opts = subHealthy ? sub.options : card.options;
                var source = subHealthy ? '子' : '主';

                var hasInvalidValue = false;
                opts.forEach(function (o, j) {
                    final['option' + (j + 1)] = o.name;
                    final['value' + (j + 1)] = o.value;
                    if (o.change) final['change' + (j + 1)] = o.change;

                    if (!/\d/.test(o.value || '')) {
                        hasInvalidValue = true;
                    }
                });

                if (hasInvalidValue) {
                    log('[W' + workerId + '] 🗑️ "' + short + '" 包含异常数据', 'warn');
                    results[idx] = null;
                    config.failures.push({
                        name: card.name,
                        url: 'https://kalshi.com' + card.subUrl,
                        volume: card.volume,
                        debugInfo: ['Invalid value detected']
                    });
                } else {
                    results[idx] = final;
                    log('[W' + workerId + '] ✅ "' + short + '" (' + source + '页' + opts.length + 'opts)', 'info');
                }
            }

        } catch (err) {
            log('[W' + workerId + '] ❌ "' + short + '": ' + err.message, 'error');
            results[idx] = buildFallback(card);
        }

        config.onProgress();
    }
}

// ============================================================
//  Phase 2: 并行子页面抓取
// ============================================================
async function startSubpageScraping() {
    if (isRunning) return;
    isRunning = true;
    startBtn.disabled = true;
    startBtn.textContent = '抓取中...';

    if (chrome.power) chrome.power.requestKeepAwake('display');

    var autoClose = document.getElementById('autoClose').checked;
    var doIncremental = document.getElementById('incrementalSaveToggle').checked;
    var concurrency = parseInt(document.getElementById('concurrencyInput').value, 10) || 4;

    // 强制降低并发，防止页面卡死
    if (concurrency > 4) concurrency = 4;

    var outputFilename = getTimestampedFilename('kalshi');
    var cards = scrapedCards.slice();

    log('🚀 创建 ' + concurrency + ' 个工作标签页...', 'info');
    var workerTabIds = [];
    for (var w = 0; w < concurrency; w++) {
        try {
            var tab = await createTab('about:blank', true); // 强制 active: true
            workerTabIds.push(tab.id);
        } catch (e) {
            log('  ⚠️ 创建第 ' + w + ' 个工作标签失败', 'warn');
        }
    }

    var queue = [];
    for (var i = 0; i < cards.length; i++) {
        queue.push({ card: cards[i], index: i });
    }

    var results = new Array(cards.length);
    var completedCount = 0;
    var failures = [];

    function onProgress() {
        completedCount++;
        var pct = Math.round((completedCount / cards.length) * 100);
        updateProgress(completedCount, cards.length, completedCount + '/' + cards.length + ' (' + pct + '%)');
        setStatus('抓取中: ' + completedCount + '/' + cards.length + ' (' + pct + '%)');
    }

    var workerPromises = workerTabIds.map(async function (tabId, w) {
        if (w > 0) {
            await new Promise(function (res) { setTimeout(res, w * 3000); }); // 增加错峰延迟
        }
        return workerLoop(w, tabId, queue, results, {
            onProgress: onProgress,
            failures: failures
        });
    });

    await Promise.all(workerPromises);

    if (autoClose) {
        for (var w = 0; w < workerTabIds.length; w++) {
            await closeTab(workerTabIds[w]);
        }
    }

    var finalResults = results.filter(function (r) { return r; });
    saveJsonFile(finalResults, outputFilename);

    if (failures.length > 0) {
        var failureLines = failures.map(f => f.name + ' - ' + f.url);
        saveTextFile(failureLines.join('\n'), 'kalshi_failure.txt');
    }

    setStatus('✅ 完成!', 'success');
    startBtn.disabled = false;
    startBtn.textContent = '重新开始';
    isRunning = false;
    if (chrome.power) chrome.power.releaseKeepAwake();
}

startBtn.addEventListener('click', function () {
    if (isRunning) return;
    if (scrapedCards) {
        startSubpageScraping();
    } else {
        scrapeMainPage();
    }
});

clearBtn.addEventListener('click', function () {
    debugLogEl.innerHTML = '';
});

if (mainTabId && !isNaN(mainTabId)) {
    if (autoStart) {
        setTimeout(scrapeMainPage, 500);
    } else {
        setStatus('就绪 — 点击按钮抓取主页面');
        startBtn.disabled = false;
    }
}