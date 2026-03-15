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

// ★ 改：支持 active 参数
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

// ★ 新增：导航已有标签到新 URL（复用标签，避免反复创建/关闭）
function navigateTab(tabId, url) {
    return new Promise(function (resolve, reject) {
        chrome.tabs.update(tabId, { url: url }, function (tab) {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
            else resolve(tab);
        });
    });
}

// ★ 改：默认超时 30s → 15s
function waitForTabComplete(tabId, timeoutMs) {
    if (!timeoutMs) timeoutMs = 15000;
    return new Promise(function (resolve) {
        var timeout = setTimeout(function () {
            chrome.tabs.onUpdated.removeListener(listener);
            resolve(false);
        }, timeoutMs);

        function listener(id, info) {
            if (id === tabId && info.status === 'complete') {
                chrome.tabs.onUpdated.removeListener(listener);
                clearTimeout(timeout);
                resolve(true);
            }
        }
        chrome.tabs.onUpdated.addListener(listener);
    });
}

// ★ 改：默认 18s → 10s，轮询 400ms → 200ms，内容就绪后等待 300ms → 100ms
async function pollForContent(tabId, maxMs) {
    if (!maxMs) maxMs = 10000;
    var start = Date.now();
    while (Date.now() - start < maxMs) {
        try {
            var r = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                func: function () {
                    var opts = document.querySelectorAll('[class*="typ-body-x30"]');
                    var isBotPage = !!document.getElementById('challenge-form') ||
                        !!document.querySelector('.cf-browser-verification') ||
                        document.title.toLowerCase().includes('just a moment') ||
                        !!document.querySelector('[id*="turnstile"]');
                    return {
                        hasContent: opts.length > 0,
                        optionCount: opts.length,
                        isBotPage: isBotPage
                    };
                }
            });
            var c = r && r[0] && r[0].result;
            if (c && c.hasContent) {
                await new Promise(function (res) { setTimeout(res, 100); });
                return { ready: true, isBotPage: false, elapsed: Date.now() - start, optionCount: c.optionCount };
            }
            if (c && c.isBotPage) {
                await new Promise(function (res) { setTimeout(res, 1500); });
            } else {
                await new Promise(function (res) { setTimeout(res, 200); });
            }
        } catch (e) {
            await new Promise(function (res) { setTimeout(res, 300); });
        }
    }
    return { ready: false, isBotPage: true, elapsed: Date.now() - start, optionCount: 0 };
}

// ★ 改：默认 5s → 3s，轮询 300ms → 200ms
async function pollForMoreOptions(tabId, prevCount, maxMs) {
    if (!maxMs) maxMs = 3000;
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
                await new Promise(function (res) { setTimeout(res, 200); });
                return { expanded: true, elapsed: Date.now() - start };
            }
        } catch (e) { /* ignore */ }
        await new Promise(function (res) { setTimeout(res, 200); });
    }
    return { expanded: false, elapsed: Date.now() - start };
}

function closeTab(tabId) {
    return new Promise(function (resolve) {
        chrome.tabs.remove(tabId, function () {
            if (chrome.runtime.lastError) { /* ignore */ }
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

// ============================================================
//  注入函数（在目标页面执行，完全独立，不引用外部变量）
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
    function cap(s) { return s.split('-').map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(' '); }

    var cards = document.querySelectorAll('[data-testid="market-tile"]');
    cards.forEach(function (card) {
        try {
            var h2 = card.querySelector('h2');
            if (!h2) return;
            var name = clean(h2.textContent);

            var subLink = card.querySelector('a[href^="/markets/"]');
            if (!subLink) return;
            var subUrl = subLink.getAttribute('href');

            var catLink = card.querySelector('a[href^="/category/"]');
            var fallbackType = '', fallbackSubtype = '';
            if (catLink) {
                fallbackSubtype = clean(catLink.textContent);
                var parts = (catLink.getAttribute('href') || '').replace('/category/', '').split('/');
                if (parts[0]) fallbackType = cap(parts[0]);
            }

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

            predictions.push({ name: name, subUrl: subUrl, volume: volume, options: options, fallbackType: fallbackType, fallbackSubtype: fallbackSubtype });
        } catch (e) { /* skip */ }
    });
    return predictions;
}

function injectedClickMore() {
    var d = [];
    var allSpans = document.querySelectorAll('span');
    for (var i = 0; i < allSpans.length; i++) {
        var text = allSpans[i].textContent.trim().replace(/\s+/g, ' ');
        if (text === 'More markets') {
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
    var result = { type: '', subtype: '', options: [] };

    var catLinks = document.querySelectorAll('a[href^="/category/"]');
    var cats = [];
    catLinks.forEach(function (a) {
        var t = a.textContent.trim().replace(/\s+/g, ' ');
        if (t && cats.indexOf(t) === -1) cats.push(t);
    });
    if (cats.length > 0) result.type = cats[0];
    if (cats.length > 1) result.subtype = cats[1];

    var seen = {};
    var section = document.querySelector('section');
    var root = section || document;

    var nameEls = root.querySelectorAll('[class*="typ-body-x30"]');

    nameEls.forEach(function (nameEl, idx) {
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

        seen[rawName] = true;
        result.options.push({ name: rawName, value: value, change: change });
    });

    if (result.options.length === 0) {
        var flexDivs = root.querySelectorAll('div[style*="flex: 1 1"]');
        flexDivs.forEach(function (div) {
            var nEl = div.querySelector('[class*="typ-body-x30"]');
            var vEl = div.querySelector('[class*="typ-headline-x10"]');
            var cEl = div.querySelector('[class*="typ-emphasis-x10"]');
            if (nEl && vEl) {
                var name = nEl.textContent.trim().replace(/\s+/g, ' ');
                var val = vEl.textContent.trim();
                var change = cEl ? cEl.textContent.trim().replace(/\s+/g, ' ') : '';
                if (name && name.toLowerCase().indexOf('more market') === -1 &&
                    name.toLowerCase().indexOf('fewer market') === -1 && !seen[name]) {
                    seen[name] = true;
                    result.options.push({ name: name, value: val, change: change });
                }
            }
        });
    }

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
        type: card.fallbackType || '',
        subtype: card.fallbackSubtype || '',
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
//  Phase 1: 抓取主页面卡片（与原来相同）
// ============================================================
async function scrapeMainPage() {
    if (isRunning) return;
    isRunning = true;
    startBtn.disabled = true;
    startBtn.textContent = '正在抓取主页面...';
    debugLogEl.innerHTML = '';
    scrapedCards = null;

    log('════════════════════════════════════════', 'section');
    log('  Kalshi Scraper - Phase 1: 抓取主页面', 'section');
    log('════════════════════════════════════════', 'section');
    log('mainTabId=' + mainTabId);

    try {
        await new Promise(function (res, rej) {
            chrome.tabs.get(mainTabId, function (t) {
                if (chrome.runtime.lastError) rej(new Error(chrome.runtime.lastError.message));
                else res(t);
            });
        });
        log('✅ 主标签页存在', 'info');
    } catch (e) {
        log('❌ 主标签页不存在: ' + e.message, 'error');
        setStatus('错误: Kalshi 主标签页已关闭，请回到 Kalshi 页面重新启动', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '重新抓取主页面';
        isRunning = false;
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
            setStatus('主页面未找到数据，请确认页面已加载', 'error');
            startBtn.disabled = false;
            startBtn.textContent = '重新抓取主页面';
            isRunning = false;
            return;
        }

        cards.forEach(function (c) {
            c.volumeNum = parseVolumeStr(c.volume);
            c.volume = String(c.volumeNum);
        });

        var seenUrls = {};
        var beforeDedup = cards.length;
        cards = cards.filter(function (c) {
            if (seenUrls[c.subUrl]) return false;
            seenUrls[c.subUrl] = true;
            return true;
        });
        if (cards.length < beforeDedup) {
            log('⚠️ 去重: ' + beforeDedup + ' → ' + cards.length + ' 个', 'warn');
        }

        log('✅ 找到 ' + cards.length + ' 个卡片', 'info');
        cards.forEach(function (c, i) {
            log('  [' + i + '] "' + c.name + '"  vol:' + c.volume + '  opts:' + c.options.length, 'data');
        });

        scrapedCards = cards;
        setStatus('✅ 主页面抓取完成，共 ' + cards.length + ' 个卡片。请配置参数后点击「开始抓取」', 'success');
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';

    } catch (e) {
        log('❌ 主页面脚本失败: ' + e.message, 'error');
        setStatus('主页面抓取失败', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '重新抓取主页面';
    }

    isRunning = false;
}

// ============================================================
//  ★ 并行工作线程：每个 worker 独立消费队列中的任务
// ============================================================
async function workerLoop(workerId, tabId, queue, results, config) {
    while (queue.length > 0) {
        var item = queue.shift();
        if (!item) break;

        var card = item.card;
        var idx = item.index;
        var short = card.name.length > 35 ? card.name.substring(0, 35) + '...' : card.name;

        try {
            // 导航到子页面（复用标签页，不创建新的）
            await navigateTab(tabId, 'https://kalshi.com' + card.subUrl);

            // 等待页面加载
            await waitForTabComplete(tabId, 15000);

            // 轮询等待内容渲染
            var poll = await pollForContent(tabId, 10000);

            if (!poll.ready) {
                // 反爬虫检测 → 切换为前台标签，等待通过
                if (poll.isBotPage) {
                    log('[W' + workerId + '] 🛡️ "' + short + '" 反爬虫页面，切换前台...', 'warn');
                    try {
                        await new Promise(function (resolve) {
                            chrome.tabs.update(tabId, { active: true }, resolve);
                        });
                    } catch (e) { }
                    await new Promise(function (res) { setTimeout(res, 8000); });
                    poll = await pollForContent(tabId, 8000);
                }

                if (!poll.ready) {
                    log('[W' + workerId + '] ❌ "' + short + '" → 备选数据', 'error');
                    results[idx] = buildFallback(card);
                    config.onProgress();
                    continue;
                }
            }

            // 尝试点击 "More markets"
            try {
                var clickR = await chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    func: injectedClickMore
                });
                var clickD = (clickR && clickR[0] && clickR[0].result) || { clicked: false };
                if (clickD.clicked) {
                    await pollForMoreOptions(tabId, poll.optionCount, 3000);
                }
            } catch (e) { }

            // 尝试点击 "X more"
            try {
                var xMoreR = await chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    func: injectedClickXMore
                });
                var xMoreD = (xMoreR && xMoreR[0] && xMoreR[0].result) || { clicked: false };
                if (xMoreD.clicked) {
                    var curR = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: function () { return document.querySelectorAll('[class*="typ-body-x30"]').length; }
                    });
                    var curCount = (curR && curR[0] && curR[0].result) || 0;
                    await pollForMoreOptions(tabId, curCount, 3000);
                }
            } catch (e) { }

            // 抓取子页面数据
            var scrapeR = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                func: injectedScrapeSubpage
            });
            var sub = (scrapeR && scrapeR[0] && scrapeR[0].result) ||
                { type: '', subtype: '', options: [], debug: [] };

            // 组装最终数据
            var final = {
                name: card.name,
                type: sub.type || card.fallbackType || '',
                subtype: sub.subtype || card.fallbackSubtype || '',
                volume: card.volume,
                hide: "1"
            };

            var opts = (sub.options && sub.options.length > 0) ? sub.options : card.options;
            var source = (sub.options && sub.options.length > 0) ? '子' : '主';
            opts.forEach(function (o, j) {
                final['option' + (j + 1)] = o.name;
                final['value' + (j + 1)] = o.value;
                if (o.change) final['change' + (j + 1)] = o.change;
            });

            results[idx] = final;
            log('[W' + workerId + '] ✅ "' + short + '" (' + source + '页' + opts.length + 'opts ' + poll.elapsed + 'ms)', 'info');

        } catch (err) {
            log('[W' + workerId + '] ❌ "' + short + '": ' + err.message, 'error');
            results[idx] = buildFallback(card);

            // 检查标签页是否还存在
            try {
                await new Promise(function (resolve, reject) {
                    chrome.tabs.get(tabId, function (t) {
                        if (chrome.runtime.lastError) reject(new Error('gone'));
                        else resolve(t);
                    });
                });
            } catch (e) {
                log('[W' + workerId + '] ⚠️ 标签页已关闭，工作线程退出', 'error');
                config.onProgress();
                break;
            }
        }

        config.onProgress();
    }

    log('[W' + workerId + '] 🏁 工作线程完成', 'dim');
}

// ============================================================
//  Phase 2: ★ 并行子页面抓取（核心改造）
// ============================================================
async function startSubpageScraping() {
    if (isRunning) return;
    isRunning = true;
    startBtn.disabled = true;
    startBtn.textContent = '抓取中...';

    var autoClose = document.getElementById('autoClose').checked;
    var doIncremental = document.getElementById('incrementalSaveToggle').checked;
    var concurrency = parseInt(document.getElementById('concurrencyInput').value, 10) || 4;
    if (concurrency < 1) concurrency = 1;
    if (concurrency > 8) concurrency = 8;

    // 解析范围输入
    var rangeInput = document.getElementById('rangeInput').value.trim();
    var startIndex = 0;
    var endIndex = -1;
    var hasRange = false;

    if (rangeInput) {
        if (rangeInput.includes('-')) {
            var parts = rangeInput.split('-').map(function (p) { return parseInt(p.trim(), 10); });
            if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1]) && parts[0] > 0 && parts[1] >= parts[0]) {
                startIndex = parts[0] - 1;
                endIndex = parts[1];
                hasRange = true;
            } else {
                log('⚠️ 范围格式错误，将抓取全部', 'warn');
            }
        } else {
            var single = parseInt(rangeInput, 10);
            if (!isNaN(single) && single > 0) {
                startIndex = single - 1;
                endIndex = single;
                hasRange = true;
            } else {
                log('⚠️ 输入格式错误，将抓取全部', 'warn');
            }
        }
    }

    var minVolumeInput = parseInt(document.getElementById('minVolume').value, 10);
    var hasMinVolume = !isNaN(minVolumeInput) && minVolumeInput > 0;

    var outputFilename = getTimestampedFilename('kalshi');
    var cards = scrapedCards.slice();

    log('', 'dim');
    log('════════════════════════════════════════', 'section');
    log('  Phase 2: 并行子页面抓取', 'section');
    log('════════════════════════════════════════', 'section');

    var rangeDesc = hasRange ?
        (startIndex + 1) + '-' + endIndex + ' (共 ' + (endIndex - startIndex) + ' 个)' : '全部';
    log('并行度=' + concurrency + '  autoClose=' + autoClose + '  增量=' + doIncremental +
        '  范围=' + rangeDesc +
        (hasMinVolume ? '  minVol=' + minVolumeInput : '  minVol=不限'));
    log('📁 输出: ' + outputFilename, 'info');

    // Volume 过滤
    if (hasMinVolume) {
        var beforeCount = cards.length;
        cards = cards.filter(function (c) { return c.volumeNum >= minVolumeInput; });
        log('📊 Volume 过滤: ' + beforeCount + ' → ' + cards.length + ' 个', 'warn');
    }

    // 范围过滤
    if (hasRange) {
        if (endIndex === -1 || endIndex > cards.length) endIndex = cards.length;
        if (startIndex >= cards.length) {
            log('⚠️ 起始位置超出范围', 'warn');
            cards = [];
        } else {
            cards = cards.slice(startIndex, endIndex);
            log('📊 范围过滤: 取第 ' + (startIndex + 1) + '-' + endIndex + ' 个 (' + cards.length + ' 个)', 'warn');
        }
    }

    if (cards.length === 0) {
        log('⚠️ 过滤后没有需要抓取的卡片', 'warn');
        setStatus('过滤后没有需要抓取的项目', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';
        isRunning = false;
        return;
    }

    // 调整并行度（不超过卡片数）
    if (concurrency > cards.length) concurrency = cards.length;
    log('📋 最终抓取 ' + cards.length + ' 个卡片，' + concurrency + ' 个并行工作线程', 'info');

    // ★ 创建工作标签页池（后台创建，不抢焦点）
    log('🚀 创建 ' + concurrency + ' 个工作标签页...', 'info');
    var workerTabIds = [];
    for (var w = 0; w < concurrency; w++) {
        try {
            var tab = await createTab('about:blank', false);
            workerTabIds.push(tab.id);
            log('  标签 W' + w + ' id=' + tab.id, 'dim');
        } catch (e) {
            log('  ⚠️ 创建第 ' + w + ' 个工作标签失败: ' + e.message, 'warn');
        }
    }

    if (workerTabIds.length === 0) {
        log('❌ 无法创建任何工作标签页', 'error');
        setStatus('错误: 无法创建标签页', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';
        isRunning = false;
        return;
    }

    // 构建共享任务队列
    var queue = [];
    for (var i = 0; i < cards.length; i++) {
        queue.push({ card: cards[i], index: i });
    }

    // 稀疏结果数组（按索引填充）
    var results = new Array(cards.length);
    var completedCount = 0;
    var lastSaveCount = 0;
    var scrapeStartTime = Date.now();

    function onProgress() {
        completedCount++;
        var pct = Math.round((completedCount / cards.length) * 100);
        updateProgress(completedCount, cards.length, completedCount + '/' + cards.length + ' (' + pct + '%)');
        setStatus('抓取中: ' + completedCount + '/' + cards.length + ' (' + pct + '%)');

        // 每完成 10 个增量保存一次
        if (doIncremental && completedCount - lastSaveCount >= 10) {
            var partial = results.filter(function (r) { return r; });
            saveJsonFile(partial, outputFilename);
            log('💾 增量保存 (' + partial.length + '条)', 'data');
            lastSaveCount = completedCount;
        }
    }

    // ★ 启动所有工作线程（并行执行）
    var workerPromises = workerTabIds.map(function (tabId, w) {
        return workerLoop(w, tabId, queue, results, {
            onProgress: onProgress
        });
    });

    await Promise.all(workerPromises);

    // 关闭工作标签页
    if (autoClose) {
        log('🧹 关闭 ' + workerTabIds.length + ' 个工作标签页...', 'dim');
        for (var w = 0; w < workerTabIds.length; w++) {
            await closeTab(workerTabIds[w]);
        }
    }

    // 切回 dashboard 标签页
    try {
        var dashTab = await new Promise(function (resolve) {
            chrome.tabs.getCurrent(function (t) { resolve(t); });
        });
        if (dashTab) {
            chrome.tabs.update(dashTab.id, { active: true });
        }
    } catch (e) { }

    // 最终保存
    var finalResults = results.filter(function (r) { return r; });
    var elapsed = Math.round((Date.now() - scrapeStartTime) / 1000);

    log('', 'dim');
    log('════════════════════════════════════════', 'section');
    log('  完成! ' + finalResults.length + '条, 耗时 ' + elapsed + 's', 'section');
    log('  并行度: ' + workerTabIds.length + '  平均: ' +
        (finalResults.length > 0 ? (elapsed / finalResults.length).toFixed(1) : '0') + 's/条', 'section');
    log('════════════════════════════════════════', 'section');

    saveJsonFile(finalResults, outputFilename);
    log('💾 最终保存: ' + outputFilename + ' (' + finalResults.length + '条)', 'data');

    progressContainer.style.display = 'none';
    setStatus('✅ 完成! ' + finalResults.length + ' 条, 耗时 ' + elapsed + 's, 平均 ' +
        (finalResults.length > 0 ? (elapsed / finalResults.length).toFixed(1) : '0') + 's/条 → ' + outputFilename, 'success');

    scrapedCards = null;
    startBtn.disabled = false;
    startBtn.textContent = '重新开始';
    isRunning = false;
}

// ============ 事件 ============
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
    log('日志已清空');
});

// ============ 初始化 ============
if (mainTabId && !isNaN(mainTabId)) {
    log('Dashboard 就绪. mainTabId = ' + mainTabId);
    if (autoStart) {
        setStatus('正在自动抓取主页面...');
        log('🚀 自动抓取主页面（完成后请配置参数再点击按钮）', 'info');
        setTimeout(scrapeMainPage, 500);
    } else {
        setStatus('就绪 — 点击按钮抓取主页面');
        startBtn.disabled = false;
        startBtn.textContent = '抓取主页面';
    }
} else {
    log('⚠️ 缺少 mainTabId 参数', 'warn');
    setStatus('错误: 请从 Kalshi 页面点击扩展图标启动', 'error');
    startBtn.disabled = true;
}