// ============ 状态 ============
let mainTabId = null;
const params = new URLSearchParams(window.location.search);
mainTabId = parseInt(params.get('mainTabId'), 10);
const autoStart = params.get('auto') === '1';

let scrapedCards = null;
let isRunning = false; // ★ 防止并发执行

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

// 创建前台标签页（active:true 是绕过 Cloudflare 的关键）
function createTab(url) {
    return new Promise(function (resolve, reject) {
        chrome.tabs.create({ url: url, active: true }, function (tab) {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
            } else {
                resolve(tab);
            }
        });
    });
}

// 等待标签页 status: complete
function waitForTabComplete(tabId, timeoutMs) {
    if (!timeoutMs) timeoutMs = 30000;
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

// 智能轮询：检测到页面内容后立即返回，不再固定等待
async function pollForContent(tabId, maxMs) {
    if (!maxMs) maxMs = 18000;
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
                // 额外等 300ms 让剩余元素渲染完
                await new Promise(function (res) { setTimeout(res, 300); });
                return { ready: true, isBotPage: false, elapsed: Date.now() - start, optionCount: c.optionCount };
            }
            if (c && c.isBotPage) {
                // 反爬虫页面，慢速轮询
                await new Promise(function (res) { setTimeout(res, 2000); });
            } else {
                // 正常等待渲染，快速轮询
                await new Promise(function (res) { setTimeout(res, 400); });
            }
        } catch (e) {
            await new Promise(function (res) { setTimeout(res, 500); });
        }
    }
    return { ready: false, isBotPage: true, elapsed: Date.now() - start, optionCount: 0 };
}

// 点击 More markets 后轮询等待选项增多
async function pollForMoreOptions(tabId, prevCount, maxMs) {
    if (!maxMs) maxMs = 5000;
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
                await new Promise(function (res) { setTimeout(res, 300); });
                return { expanded: true, elapsed: Date.now() - start };
            }
        } catch (e) { /* ignore */ }
        await new Promise(function (res) { setTimeout(res, 300); });
    }
    return { expanded: false, elapsed: Date.now() - start };
}

function closeTab(tabId) {
    return new Promise(function (resolve) {
        chrome.tabs.remove(tabId, function () {
            if (chrome.runtime.lastError) {
                log('  ⚠️ 关闭标签失败: ' + chrome.runtime.lastError.message, 'warn');
            }
            resolve();
        });
    });
}

// ============ 下载工具 ============

// ★ 统一下载函数：使用 chrome.downloads API，不弹出保存对话框
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

// ---- 注入：点击 "X more" 按钮 ----
function injectedClickXMore() {
    var d = [];
    var clicked = false;

    // 查找所有可能的 "X more" 文本
    var allElements = document.querySelectorAll('*');
    var morePattern = /^\d+\s+more$/i;

    for (var i = 0; i < allElements.length; i++) {
        var text = allElements[i].textContent.trim();

        if (morePattern.test(text)) {
            d.push('Found "' + text + '"');

            // 尝试找到可点击的父元素
            var target = allElements[i];

            // 检查自身是否可点击
            if (target.tagName === 'BUTTON' ||
                target.getAttribute('role') === 'button' ||
                target.onclick ||
                (target.className && target.className.includes('cursor-pointer'))) {
                target.click();
                d.push('Clicked element directly');
                clicked = true;
                break;
            }

            // 向上查找可点击的父元素
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

// ---- 注入：主页面卡片基本信息 ----
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

                    // ★ 过滤 "Show less"
                    var optNameLower = optName.toLowerCase().trim();
                    if (optNameLower === 'show less') {
                        return; // 跳过此 option
                    }

                    // ★ 过滤 "Hide markets"
                    var optNameLower = optName.toLowerCase().trim();
                    if (optNameLower === 'Hide markets') {
                        return; // 跳过此 option
                    }

                    // 抓取 change
                    var cEl = row.querySelector('[class*="typ-emphasis-x10"]');
                    var change = cEl ? clean(cEl.textContent) : '';

                    options.push({
                        name: optName,
                        value: v.includes('%') ? v : v + '%',
                        change: change
                    });
                }
            });

            // ★ 如果 options > 10，过滤 <1%
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

// ---- 注入：点击 More markets ----
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

// ---- 注入：抓取子页面 options ----
function injectedScrapeSubpage() {
    var d = [];
    var result = { type: '', subtype: '', options: [] };

    // 1. Categories
    var catLinks = document.querySelectorAll('a[href^="/category/"]');
    var cats = [];
    catLinks.forEach(function (a) {
        var t = a.textContent.trim().replace(/\s+/g, ' ');
        if (t && cats.indexOf(t) === -1) cats.push(t);
    });
    d.push('Categories: ' + JSON.stringify(cats));
    if (cats.length > 0) result.type = cats[0];
    if (cats.length > 1) result.subtype = cats[1];

    // 2. Options — Approach A: typ-body-x30 + traverse up for typ-headline-x10
    var seen = {};
    var section = document.querySelector('section');
    var root = section || document;

    var nameEls = root.querySelectorAll('[class*="typ-body-x30"]');
    d.push('typ-body-x30 count: ' + nameEls.length);

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

        // 抓取 change
        var changeEl = container ? container.querySelector('[class*="typ-emphasis-x10"]') : null;
        var change = changeEl ? changeEl.textContent.trim().replace(/\s+/g, ' ') : '';

        seen[rawName] = true;
        result.options.push({ name: rawName, value: value, change: change });
    });

    // 3. Approach B fallback
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

    d.push('Options count before filtering: ' + result.options.length);

    // ★★★ 新增：过滤逻辑 ★★★
    result.options = result.options.filter(function (opt) {
        var optName = opt.name.toLowerCase().trim();

        // 需求1: 过滤 "Show less"
        if (optName === 'show less') {
            d.push('Filtered out: "' + opt.name + '"');
            return false;
        }
        // 需求2: 过滤 "Hide markets"
        if (optName === 'hide markets') {
            d.push('Filtered out: "' + opt.name + '"');
            return false;
        }
        return true;
    });

    // 需求2: 如果超过10个option，过滤掉所有 <1%
    if (result.options.length > 10) {
        d.push('Options > 10, filtering <1% values...');
        var beforeFilter = result.options.length;
        result.options = result.options.filter(function (opt) {
            if (opt.value.trim() === '<1%') {
                d.push('Filtered out <1%: "' + opt.name + '"');
                return false;
            }
            return true;
        });
        d.push('Filtered ' + (beforeFilter - result.options.length) + ' options with <1%');
    }

    d.push('Options count after filtering: ' + result.options.length);
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
//  Phase 1: 抓取主页面卡片（自动执行，完成后暂停等待用户操作）
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

    // 验证主标签页
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

        // 清洗 volume → 纯数字
        cards.forEach(function (c) {
            c.volumeNum = parseVolumeStr(c.volume);
            c.volume = String(c.volumeNum);
        });

        // ★ 按 subUrl 去重，防止同一市场被重复抓取
        var seenUrls = {};
        var beforeDedup = cards.length;
        cards = cards.filter(function (c) {
            if (seenUrls[c.subUrl]) return false;
            seenUrls[c.subUrl] = true;
            return true;
        });
        if (cards.length < beforeDedup) {
            log('⚠️ 去重: ' + beforeDedup + ' → ' + cards.length + ' 个 (移除 ' + (beforeDedup - cards.length) + ' 个重复)', 'warn');
        }

        log('✅ 找到 ' + cards.length + ' 个卡片', 'info');
        log('', 'dim');
        cards.forEach(function (c, i) {
            log('  [' + i + '] "' + c.name + '"  |  volume: ' + c.volume, 'data');
            log('       subUrl: ' + c.subUrl + '  主页面options: ' + c.options.length + '个', 'dim');
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
//  Phase 2: 逐个抓取子页面（用户点击按钮后执行）
// ============================================================
async function startSubpageScraping() {
    if (isRunning) return;
    isRunning = true;
    startBtn.disabled = true;
    startBtn.textContent = '抓取中...';

    var autoClose = document.getElementById('autoClose').checked;
    var doIncremental = document.getElementById('incrementalSaveToggle').checked;

    // ★ 新增：解析范围输入
    var rangeInput = document.getElementById('rangeInput').value.trim();
    var startIndex = 0;  // 默认从第一个开始
    var endIndex = -1;   // -1 表示到最后
    var hasRange = false;

    if (rangeInput) {
        if (rangeInput.includes('-')) {
            // 范围格式: "5-10"
            var parts = rangeInput.split('-').map(function (p) { return parseInt(p.trim(), 10); });
            if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1]) && parts[0] > 0 && parts[1] >= parts[0]) {
                startIndex = parts[0] - 1;  // 转为 0-based index
                endIndex = parts[1];        // endIndex 保持为实际数字（用于 slice）
                hasRange = true;
            } else {
                log('⚠️ 范围格式错误，将抓取全部。正确格式: "起始-结束" (如 5-10)', 'warn');
            }
        } else {
            // 单个数字: "5" 表示只抓第5个
            var single = parseInt(rangeInput, 10);
            if (!isNaN(single) && single > 0) {
                startIndex = single - 1;
                endIndex = single;
                hasRange = true;
            } else {
                log('⚠️ 输入格式错误，将抓取全部。正确格式: 单个数字或范围 (如 "5" 或 "5-10")', 'warn');
            }
        }
    }

    var minVolumeInput = parseInt(document.getElementById('minVolume').value, 10);
    var hasMinVolume = !isNaN(minVolumeInput) && minVolumeInput > 0;

    // ★ 生成带日期戳的文件名
    var outputFilename = getTimestampedFilename('kalshi');

    var cards = scrapedCards.slice();

    log('', 'dim');
    log('════════════════════════════════════════', 'section');
    log('  Phase 2: 开始子页面抓取', 'section');
    log('════════════════════════════════════════', 'section');

    // ★ 更新日志输出
    var rangeDesc = hasRange ?
        (startIndex + 1) + '-' + endIndex + ' (共 ' + (endIndex - startIndex) + ' 个)' :
        '全部';
    log('autoClose=' + autoClose + '  增量保存=' + doIncremental +
        '  抓取范围=' + rangeDesc +
        (hasMinVolume ? '  最小volume=' + minVolumeInput : '  最小volume=不限'));
    log('📁 输出文件: ' + outputFilename, 'info');

    // 根据 minVolume 过滤
    if (hasMinVolume) {
        var beforeCount = cards.length;
        cards = cards.filter(function (c) {
            return c.volumeNum >= minVolumeInput;
        });
        var removedCount = beforeCount - cards.length;
        log('📊 Volume 过滤: ' + beforeCount + ' → ' + cards.length + ' 个 (移除 ' + removedCount + ' 个, 阈值: $' + minVolumeInput + ')', 'warn');
    }

    // ★ 应用范围过滤（在 volume 过滤之后）
    if (hasRange) {
        var beforeRangeCount = cards.length;
        if (endIndex === -1 || endIndex > cards.length) {
            endIndex = cards.length;
        }
        if (startIndex >= cards.length) {
            log('⚠️ 起始位置超出范围 (总共 ' + cards.length + ' 个)', 'warn');
            cards = [];
        } else {
            cards = cards.slice(startIndex, endIndex);
            log('📊 范围过滤: 从第 ' + (startIndex + 1) + ' 个到第 ' + endIndex + ' 个 (取 ' + cards.length + ' 个, 跳过前 ' + startIndex + ' 个)', 'warn');
        }
    }

    if (cards.length === 0) {
        log('⚠️ 过滤后没有需要抓取的卡片', 'warn');
        setStatus('过滤后没有需要抓取的项目，请调整参数', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';
        isRunning = false;
        return;
    }

    log('📋 最终抓取 ' + cards.length + ' 个卡片', 'info');

    // 记住 dashboard 标签页 id，抓完子页面后切回来
    var dashboardTabId = null;
    try {
        var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tabs && tabs[0]) dashboardTabId = tabs[0].id;
    } catch (e) { /* ignore */ }

    // ---- STEP 2: 逐个子页面（智能轮询） ----
    var results = [];
    var scrapeStartTime = Date.now();

    for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        var short = card.name.length > 40 ? card.name.substring(0, 40) + '...' : card.name;

        log('', 'dim');
        log('─── CARD ' + (i + 1) + '/' + cards.length + ': "' + short + '" ───', 'section');
        setStatus('(' + (i + 1) + '/' + cards.length + ') ' + short);
        updateProgress(i + 1, cards.length, short);

        var subTab = null;
        try {
            var url = 'https://kalshi.com' + card.subUrl;
            log('  打开: ' + url, 'dim');

            subTab = await createTab(url);
            log('  📄 标签已创建 (id:' + subTab.id + ')', 'dim');

            // 等待页面初始加载
            var loadOk = await waitForTabComplete(subTab.id, 30000);
            log('  ' + (loadOk ? '✅' : '⏱️') + ' status=complete', 'dim');

            // 智能轮询内容（核心加速点：有内容立即返回）
            log('  ⏳ 轮询等待内容...', 'dim');
            var poll = await pollForContent(subTab.id, 18000);

            if (!poll.ready) {
                if (poll.isBotPage) {
                    log('  ⚠️ 反爬虫页面检测! 额外等待 12s...', 'warn');
                    await new Promise(function (res) { setTimeout(res, 12000); });
                    poll = await pollForContent(subTab.id, 10000);
                }
                if (!poll.ready) {
                    log('  ❌ 内容未出现 → 使用主页面备选数据', 'error');
                    results.push(buildFallback(card));
                    // ★ 不在这里 closeTab，由 finally 统一处理
                    // ★ 增量保存：仅在非最后一张卡片时保存
                    if (doIncremental && i < cards.length - 1) {
                        saveJsonFile(results, outputFilename);
                        log('  💾 增量已保存 (' + results.length + '条)', 'data');
                    }
                    if (i < cards.length - 1) await new Promise(function (res) { setTimeout(res, 300); });
                    continue;
                }
            }

            log('  ✅ 内容就绪 (' + poll.elapsed + 'ms, ' + poll.optionCount + '个元素)', 'info');

            // 点击 "More markets"
            log('  🖱️ 查找 "More markets"...', 'dim');
            var clickR = await chrome.scripting.executeScript({
                target: { tabId: subTab.id },
                func: injectedClickMore
            });
            var clickD = (clickR && clickR[0] && clickR[0].result) || { clicked: false, debug: [] };

            if (clickD.clicked) {
                log('  ✅ 已点击 "More markets"，轮询等待新选项...', 'info');
                var moreResult = await pollForMoreOptions(subTab.id, poll.optionCount, 5000);
                log('  ' + (moreResult.expanded ? '✅ 选项已展开' : '⚠️ 展开超时') +
                    ' (' + moreResult.elapsed + 'ms)', moreResult.expanded ? 'info' : 'warn');
            } else {
                log('  ℹ️ 无 "More markets" 按钮', 'dim');
            }

            // ★ 新增：点击 "X more" 按钮
            log('  🖱️ 查找 "X more" 按钮...', 'dim');
            var xMoreClickR = await chrome.scripting.executeScript({
                target: { tabId: subTab.id },
                func: injectedClickXMore
            });
            var xMoreClickD = (xMoreClickR && xMoreClickR[0] && xMoreClickR[0].result) || { clicked: false, debug: [] };

            if (xMoreClickD.clicked) {
                log('  ✅ 已点击 "X more"，轮询等待新选项...', 'info');

                // 重新获取当前选项数量
                var currentCountR = await chrome.scripting.executeScript({
                    target: { tabId: subTab.id },
                    func: function () {
                        return document.querySelectorAll('[class*="typ-body-x30"]').length;
                    }
                });
                var currentCount = (currentCountR && currentCountR[0] && currentCountR[0].result) || 0;

                var xMoreResult = await pollForMoreOptions(subTab.id, currentCount, 5000);
                log('  ' + (xMoreResult.expanded ? '✅ 选项已展开' : '⚠️ 展开超时') +
                    ' (' + xMoreResult.elapsed + 'ms)', xMoreResult.expanded ? 'info' : 'warn');
            } else {
                log('  ℹ️ 无 "X more" 按钮', 'dim');
            }

            // 抓取子页面数据
            log('  📊 抓取 options...', 'dim');
            var scrapeR = await chrome.scripting.executeScript({
                target: { tabId: subTab.id },
                func: injectedScrapeSubpage
            });
            var sub = (scrapeR && scrapeR[0] && scrapeR[0].result) ||
                { type: '', subtype: '', options: [], debug: [] };
            sub.debug.forEach(function (l) { log('    ' + l, 'dim'); });

            // 组装最终数据
            var final = {
                name: card.name,
                type: sub.type || card.fallbackType || '',
                subtype: sub.subtype || card.fallbackSubtype || '',
                volume: card.volume,
                hide: "1"
            };

            var opts = (sub.options && sub.options.length > 0) ? sub.options : card.options;
            var source = (sub.options && sub.options.length > 0) ? '子页面' : '主页面(备选)';
            log('  📋 Options 来源: ' + source + ' (' + opts.length + '个)',
                source === '子页面' ? 'info' : 'warn');

            opts.forEach(function (o, j) {
                final['option' + (j + 1)] = o.name;
                final['value' + (j + 1)] = o.value;
                if (o.change) final['change' + (j + 1)] = o.change; // ★ 写入 change 数据

                var changeText = o.change ? ' (' + o.change + ')' : '';
                log('    option' + (j + 1) + ': "' + o.name + '" = ' + o.value + changeText, 'data');
            });

            results.push(final);
            log('  ✅ 完成', 'info');

        } catch (err) {
            log('  ❌ 错误: ' + err.message, 'error');
            log('  使用主页面备选数据', 'warn');
            results.push(buildFallback(card));
        } finally {
            if (subTab && autoClose) {
                await closeTab(subTab.id);
            } else if (subTab) {
                log('  📌 子页面保持打开 (id:' + subTab.id + ')', 'dim');
            }
        }

        // ★ 增量保存：仅在非最后一张卡片时保存（最终保存统一在循环后执行）
        if (doIncremental && i < cards.length - 1) {
            saveJsonFile(results, outputFilename);
            log('  💾 增量已保存 (' + results.length + '条)', 'data');
        }

        // 切回 dashboard 标签页，减少用户干扰
        if (dashboardTabId && autoClose) {
            try {
                chrome.tabs.update(dashboardTabId, { active: true });
            } catch (e) { /* ignore */ }
        }

        // 短暂间隔
        if (i < cards.length - 1) {
            await new Promise(function (res) { setTimeout(res, 300); });
        }
    }

    // ---- 最终保存（唯一的一次或最后一次） ----
    var elapsed = Math.round((Date.now() - scrapeStartTime) / 1000);

    log('', 'dim');
    log('════════════════════════════════════════', 'section');
    log('  完成! 共 ' + results.length + ' 条数据, 耗时 ' + elapsed + '秒', 'section');
    log('════════════════════════════════════════', 'section');

    // ★ 统一使用 saveJsonFile（chrome.downloads API），不弹出对话框
    saveJsonFile(results, outputFilename);
    log('💾 最终保存: ' + outputFilename, 'data');

    progressContainer.style.display = 'none';
    setStatus('✅ 成功! ' + results.length + ' 条数据, 耗时 ' + elapsed + 's → ' + outputFilename, 'success');

    // 重置，下次点击将重新抓取主页面
    scrapedCards = null;
    startBtn.disabled = false;
    startBtn.textContent = '重新开始';
    isRunning = false;
}

// ============ 事件 ============
startBtn.addEventListener('click', function () {
    if (isRunning) return; // ★ 防止重复点击
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