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

// ★ 新增：合并导航与等待，彻底避免竞态条件
function navigateAndWait(tabId, url, timeoutMs) {
    if (!timeoutMs) timeoutMs = 15000;
    return new Promise(function (resolve, reject) {
        var isDone = false;
        var timeout = setTimeout(function () {
            if (!isDone) {
                isDone = true;
                chrome.tabs.onUpdated.removeListener(listener);
                resolve(false); // 超时也返回 false，交给后续逻辑处理
            }
        }, timeoutMs);

        function listener(id, info) {
            // 监听到加载完成
            if (id === tabId && info.status === 'complete') {
                if (!isDone) {
                    isDone = true;
                    chrome.tabs.onUpdated.removeListener(listener);
                    clearTimeout(timeout);
                    resolve(true);
                }
            }
        }

        // 关键点：先添加监听器，再发起导航请求！
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
                    var h1 = document.querySelector('h1');
                    // ★ 新增：检测分类链接是否已渲染
                    var catLinks = document.querySelectorAll(
                        'a[href*="/category/"], a[href*="/categories/"], a[href*="/sports/"], a[href*="/browse/"]'
                    );
                    var isBotPage = !!document.getElementById('challenge-form') ||
                        !!document.querySelector('.cf-browser-verification') ||
                        document.title.toLowerCase().includes('just a moment') ||
                        !!document.querySelector('[id*="turnstile"]');
                    return {
                        // ★ 改：h1 存在 且 (选项存在 或 分类链接存在) 即视为就绪
                        hasContent: !!h1 && (opts.length > 0 || catLinks.length > 0),
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

// ★ 新增：保存纯文本文件
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

    // ★ 从面包屑导航中抓取 type 和 subtype
    try {
        var categories = [];

        // ★ 辅助：从 a 元素提取分类文本（优先 span，fallback 到 a.textContent）
        function getCatText(aEl) {
            var span = aEl.querySelector('span[class*="typ-body-x20"]');
            var t = span ? span.textContent : aEl.textContent;
            return t ? t.trim().replace(/\s+/g, ' ') : '';
        }

        // ★ 新增：已知非分类路径（集中管理排除列表）
        function isExcludedPath(href) {
            return /^\/(login|signup|portfolio|profile|settings|trade|help|about|terms|privacy|register|api|docs|notifications|deposit|withdraw|leaderboard|fee|blog|press|referral|search|faq|support|contact|careers|partners|legal|rules|pricing|account|markets)\b/i.test(href);
        }

        // ★ 扩展：更宽泛的分类链接 href 匹配
        function isCategoryHref(href) {
            if (!href) return false;
            if (href.indexOf('/category/') !== -1) return true;
            if (href.indexOf('/categories/') !== -1) return true;
            if (href.indexOf('/sports/') !== -1) return true;
            if (href.indexOf('/browse/') !== -1) return true;
            if (/^\/events\/[a-z]/i.test(href) && href.indexOf('/markets/') === -1) return true;
            // ★ 新增：匹配 1-2 层简洁路径（如 /elections、/politics/elections）
            if (/^\/[a-z][a-z0-9-]+$/i.test(href) && !isExcludedPath(href)) return true;
            if (/^\/[a-z][a-z0-9-]+\/[a-z][a-z0-9-]+$/i.test(href) && !isExcludedPath(href)) return true;
            return false;
        }

        // ★ 改进：精确判断是否在主导航中
        function isInMainNav(aEl) {
            if (aEl.closest('header')) return true;
            if (aEl.closest('[data-testid*="navbar"]')) return true;
            if (aEl.closest('[data-testid*="nav-bar"]')) return true;
            var navEl = aEl.closest('nav');
            if (navEl) {
                if (navEl.closest('header')) return true;
                if (navEl.querySelectorAll('a').length > 10) return true;
            }
            return false;
        }

        var h1 = document.querySelector('h1');

        // ════════════════════════════════════════════════
        // ★ Strategy 0.5 (NEW): 检查 h1 的兄弟节点（解决 Trump's bad year 页面结构）
        // ════════════════════════════════════════════════
        if (h1 && categories.length === 0) {
            var h1Parent = h1.parentElement;
            if (h1Parent) {
                var h1Siblings = h1Parent.children;
                for (var i = 0; i < h1Siblings.length; i++) {
                    var sib = h1Siblings[i];
                    if (sib === h1) continue;
                    var links = sib.querySelectorAll('a');
                    for (var j = 0; j < links.length; j++) {
                        var aHref = links[j].getAttribute('href') || '';
                        if (isCategoryHref(aHref) && !isInMainNav(links[j])) {
                            var aText = getCatText(links[j]);
                            if (aText && aText !== '•' && aText !== '·' && categories.indexOf(aText) === -1) {
                                categories.push(aText);
                            }
                        }
                    }
                }
                if (categories.length > 0) {
                    d.push('S0.5: h1 sibling search (' + categories.length + '): ' + categories.join(' > '));
                }
            }
        }

        // ════════════════════════════════════════════════
        // ★ Strategy 0: 文本分隔符 + 近邻链接检测
        // ════════════════════════════════════════════════
        if (h1 && categories.length === 0) {
            var anc0 = h1.parentElement;
            for (var s0 = 0; s0 < 12 && anc0 && categories.length === 0; s0++) {
                var kids = anc0.children;
                for (var ki = 0; ki < kids.length && categories.length === 0; ki++) {
                    var kid = kids[ki];
                    // 跳过包含 h1 的子树（那是标题/正文区域）
                    if (kid === h1 || kid.contains(h1)) continue;
                    // 跳过页面级 header 标签
                    if (kid.tagName === 'HEADER') continue;

                    var kText = kid.textContent.trim();

                    // ── Case A: 包含分隔符 · 或 • → 按分隔符拆分 ──
                    if ((kText.includes('·') || kText.includes('•')) &&
                        kText.length >= 3 && kText.length < 200) {
                        var parts = kText.split(/[·•]/);
                        var cleaned = [];
                        for (var pi = 0; pi < parts.length; pi++) {
                            var p = parts[pi].trim();
                            if (p.length > 0 && p.length < 50) cleaned.push(p);
                        }
                        if (cleaned.length >= 1 && cleaned.length <= 6) {
                            categories = cleaned;
                            d.push('S0a: separator text (' + cleaned.length + '): ' + cleaned.join(' > '));
                        }
                    }

                    // ── Case B: 不含分隔符，但是一个小元素，内含 1-5 个分类链接 ──
                    if (categories.length === 0 && kText.length > 0 && kText.length < 100) {
                        var kidLinks = kid.querySelectorAll('a');
                        if (kidLinks.length >= 1 && kidLinks.length <= 5) {
                            var catTexts = [];
                            for (var kli = 0; kli < kidLinks.length; kli++) {
                                var kl = kidLinks[kli];
                                var klHref = kl.getAttribute('href') || '';
                                if (!klHref || klHref === '#' || klHref === '/') continue;
                                if (klHref.indexOf('/markets/') !== -1) continue;
                                if (/^https?:/.test(klHref)) continue;
                                if (isInMainNav(kl)) continue;
                                if (isExcludedPath(klHref)) continue;
                                var klText = getCatText(kl);
                                if (klText && klText.length > 0 && klText.length < 40 &&
                                    klText !== '·' && klText !== '•' &&
                                    catTexts.indexOf(klText) === -1) {
                                    catTexts.push(klText);
                                }
                            }
                            if (catTexts.length >= 1 && catTexts.length <= 4) {
                                categories = catTexts;
                                d.push('S0b: link-based (' + catTexts.length + '): ' + catTexts.join(' > '));
                            }
                        }
                    }
                }
                anc0 = anc0.parentElement;
            }
        }

        // ════════════════════════════════════════════════
        // Strategy 1: 从 h1 逐层向上，查找含分类 href 的链接
        // ════════════════════════════════════════════════
        if (categories.length === 0 && h1) {
            var ancestor = h1.parentElement;
            for (var up = 0; up < 8 && ancestor; up++) {
                var bcLinks = ancestor.querySelectorAll('a');
                var foundAny = false;
                for (var bi = 0; bi < bcLinks.length; bi++) {
                    var href = bcLinks[bi].getAttribute('href') || '';
                    if (!isCategoryHref(href)) continue;
                    if (isInMainNav(bcLinks[bi])) continue;

                    var text = getCatText(bcLinks[bi]);
                    if (text && text !== '•' && text !== '·' && categories.indexOf(text) === -1) {
                        categories.push(text);
                        foundAny = true;
                    }
                }
                // 找到即停，避免范围过大抓到无关链接
                if (foundAny) {
                    d.push('S1: href-based (' + categories.length + '): ' + categories.join(' > '));
                    break;
                }
                ancestor = ancestor.parentElement;
            }
        }

        // Strategy 2: 全文档搜索（排除主导航）
        if (categories.length === 0) {
            d.push('S2: document-wide search...');
            var allAs = document.querySelectorAll('a');
            for (var ai = 0; ai < allAs.length; ai++) {
                var aHref = allAs[ai].getAttribute('href') || '';
                if (!isCategoryHref(aHref)) continue;
                if (isInMainNav(allAs[ai])) continue;

                var aText = getCatText(allAs[ai]);
                if (aText && aText !== '•' && aText !== '·' && categories.indexOf(aText) === -1) {
                    categories.push(aText);
                }
            }
            if (categories.length > 0) {
                d.push('S2: found (' + categories.length + '): ' + categories.join(' > '));
            }
        }

        // ★ Strategy 3: 排除法在 h1 附近寻找链接
        if (categories.length === 0 && h1) {
            d.push('S3: exclude-based fallback...');
            var anc3 = h1.parentElement;
            for (var u = 0; u < 5 && anc3; u++) {
                var links = anc3.querySelectorAll('a');
                var cands = [];
                for (var li = 0; li < links.length; li++) {
                    var lHref = links[li].getAttribute('href') || '';
                    if (!lHref || lHref === '#' || lHref === '/') continue;
                    if (isInMainNav(links[li])) continue;
                    // 排除市场/合约链接
                    if (lHref.indexOf('/markets/') !== -1) continue;
                    // 排除外部链接
                    if (/^https?:/.test(lHref)) continue;
                    // 排除已知非分类路径
                    if (isExcludedPath(lHref)) continue;

                    var lText = getCatText(links[li]);
                    if (lText && lText.length > 0 && lText.length < 30 &&
                        lText !== '•' && lText !== '·' &&
                        cands.indexOf(lText) === -1) {
                        cands.push(lText);
                    }
                }
                // 只在候选数合理时接受
                if (cands.length >= 1 && cands.length <= 4) {
                    categories = cands;
                    d.push('S3: fallback (' + cands.length + '): ' + cands.join(' > '));
                    break;
                }
                anc3 = anc3.parentElement;
            }
        }

        // ★ 调试：如果仍未找到，输出 h1 附近结构信息以便后续诊断
        if (categories.length === 0 && h1) {
            d.push('[DEBUG] No categories found. Ancestor children:');
            var dbgAnc = h1.parentElement;
            for (var du = 0; du < 6 && dbgAnc; du++) {
                var dbgKids = dbgAnc.children;
                d.push('  up=' + du + ' <' + dbgAnc.tagName + '> children=' + dbgKids.length);
                for (var dki = 0; dki < dbgKids.length && dki < 10; dki++) {
                    var dk = dbgKids[dki];
                    var dkText = dk.textContent.trim().substring(0, 80);
                    var dkLinkCount = dk.querySelectorAll('a').length;
                    var dkHasH1 = dk.contains(h1) ? ' [has-h1]' : '';
                    var dkInHeader = dk.tagName === 'HEADER' ? ' [HEADER]' : '';
                    d.push('    [' + dki + '] <' + dk.tagName + '> links=' + dkLinkCount + dkHasH1 + dkInHeader + ' "' + dkText + '"');
                    // 显示该子元素中的链接 href（仅链接数 <= 5 时）
                    if (dkLinkCount > 0 && dkLinkCount <= 5 && !dk.contains(h1)) {
                        var dkAs = dk.querySelectorAll('a');
                        for (var dai = 0; dai < dkAs.length; dai++) {
                            var daHref = dkAs[dai].getAttribute('href') || '';
                            var daText = dkAs[dai].textContent.trim().substring(0, 30);
                            var daNav = isInMainNav(dkAs[dai]) ? ' [main-nav]' : '';
                            d.push('      a: "' + daText + '" href=' + daHref + daNav);
                        }
                    }
                }
                // 子元素数量合理时不再向上
                if (dbgKids.length <= 15) break;
                dbgAnc = dbgAnc.parentElement;
            }
        }

        d.push('Final categories (' + categories.length + '): ' + categories.join(' > '));

        // ★ 规则：
        //   1 个分类 → type = subtype = 该分类
        //   2 个分类 → type = 第1个, subtype = 第2个
        //   3 个及以上 → type = 第1个, subtype = 第2个
        if (categories.length === 1) {
            result.type = categories[0];
            result.subtype = categories[0];
            d.push('Single category → type=subtype=' + categories[0]);
        } else if (categories.length >= 2) {
            result.type = categories[0];
            result.subtype = categories[1];
            d.push('type=' + categories[0] + ', subtype=' + categories[1]);
        }
    } catch (e) {
        d.push('Category extraction error: ' + e.message);
    }

    // ★ 选项抓取
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
        type: '',        // ★ 改：fallback 时留空，因为主页面类型不准确
        subtype: '',     // ★ 改：fallback 时留空
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

    // 请求保持屏幕常亮
    if (chrome.power) chrome.power.requestKeepAwake('display');

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
            setStatus('主页面未找到数据，请确认页面已加载', 'error');
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
    if (chrome.power) chrome.power.releaseKeepAwake();
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
        var sub = null; // 提升作用域，方便后续获取 debug 信息

        try {
            // ★ 最多尝试 3 次（首次 + 2 次重试）
            var maxAttempts = 3;
            var poll = null;
            var lastSource = '主';

            for (var attempt = 1; attempt <= maxAttempts; attempt++) {

                // 重试时先等一会儿再重新加载
                if (attempt > 1) {
                    var retryDelay = 1500 * attempt;
                    log('[W' + workerId + '] 🔄 分类为空, 重试#' + (attempt - 1) + ' "' + short + '" (等待' + retryDelay + 'ms)', 'warn');
                    await new Promise(function (res) { setTimeout(res, retryDelay); });
                }

                // 导航到子页面并等待加载
                await navigateAndWait(tabId, 'https://kalshi.com' + card.subUrl, 15000);

                // 轮询等待内容渲染（重试时给更多时间）
                var pollTimeout = attempt === 1 ? 10000 : 14000;
                poll = await pollForContent(tabId, pollTimeout);

                if (!poll.ready) {
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
                        // 页面没加载好，如果还有重试机会就继续
                        if (attempt < maxAttempts) continue;
                        log('[W' + workerId + '] ❌ "' + short + '" → 页面加载超时/被拦截', 'error');
                        results[idx] = buildFallback(card);
                        sub = null;
                        break;
                    }
                }

                // 重试时额外等待让分类区域渲染
                if (attempt > 1) {
                    await new Promise(function (res) { setTimeout(res, 800); });
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
                sub = (scrapeR && scrapeR[0] && scrapeR[0].result) ||
                    { type: '', subtype: '', options: [], debug: [] };

                // ★ 输出子页面分类检测的调试信息
                if (sub.debug && sub.debug.length > 0) {
                    sub.debug.forEach(function (msg) {
                        log('[W' + workerId + ']   → ' + msg, 'dim');
                    });
                }

                if (sub.type || sub.subtype) {
                    if (attempt > 1) {
                        log('[W' + workerId + '] ✅ 重试#' + (attempt - 1) + '成功! type="' + sub.type + '" subtype="' + sub.subtype + '"', 'info');
                    }
                    break;
                }

                // 删除了原先在这里的 config.failures.push，改为在最外层统一拦截
            }

            // 如果 sub 不为 null，说明走完了抓取流程（无论是否抓到分类）
            if (sub !== null) {
                var final = {
                    name: card.name,
                    type: sub.type || '',
                    subtype: sub.subtype || '',
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
                log('[W' + workerId + '] ✅ "' + short + '" (' + source + '页' + opts.length + 'opts) type=' + (sub.type || '(空)') + ' subtype=' + (sub.subtype || '(空)'), 'info');
            }

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
                // 标签页崩溃时也要记录失败
                config.failures.push({
                    name: card.name,
                    url: 'https://kalshi.com' + card.subUrl,
                    volume: card.volume,
                    debugInfo: ['Tab crashed or closed: ' + err.message]
                });
                config.onProgress();
                break;
            }
        }

        // ★ 核心修复：统一在这里做最终检查！
        // 无论是因为超时、报错、还是抓取到了但分类为空，只要最终结果里 type 和 subtype 都是空，就记录到 txt
        var finalData = results[idx];
        if (finalData && !finalData.type && !finalData.subtype) {
            config.failures.push({
                name: card.name,
                url: 'https://kalshi.com' + card.subUrl,
                volume: card.volume,
                debugInfo: (sub && sub.debug && sub.debug.length > 0) ? sub.debug : ['Page load failed, timeout, or exception thrown']
            });
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

    // 请求保持屏幕常亮
    if (chrome.power) chrome.power.requestKeepAwake('display');

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

    // ★ 修改：如果输入框为空，则默认 100000；如果有输入，则解析为整数
    var minVolumeRaw = document.getElementById('minVolume').value.trim();
    var minVolumeInput = minVolumeRaw === '' ? 100000 : parseInt(minVolumeRaw, 10);
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
        if (chrome.power) chrome.power.releaseKeepAwake();
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
        if (chrome.power) chrome.power.releaseKeepAwake();
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
    var failures = [];

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

    // ★ 启动所有工作线程（加入错峰机制，避免瞬间并发触发反爬虫）
    var workerPromises = workerTabIds.map(async function (tabId, w) {
        if (w > 0) {
            // 第 0 个线程立即启动，后续线程每个延迟 2000ms (2秒) 启动。
            // 这样 4 个线程的请求会分布在 0s, 2s, 4s, 6s，彻底避免 Cloudflare 并发拦截和前台抢夺。
            await new Promise(function (res) { setTimeout(res, w * 2000); });
        }
        return workerLoop(w, tabId, queue, results, {
            onProgress: onProgress,
            failures: failures    // ★ 新增：传入共享失败数组
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

    // ★ 新增：保存失败记录到 kalshi_failure.txt
    if (failures.length > 0) {
        log('', 'dim');
        log('⚠️ 共 ' + failures.length + ' 个项目在3次尝试后仍未获取到分类:', 'warn');
        var failureLines = [];
        failureLines.push('Kalshi Scraper - 分类抓取失败记录');
        failureLines.push('生成时间: ' + new Date().toLocaleString());
        failureLines.push('共 ' + failures.length + ' 个项目');
        failureLines.push('');
        failureLines.push('========================================');
        failures.forEach(function (f, fi) {
            failureLines.push('');
            failureLines.push('[' + (fi + 1) + '] ' + f.name);
            failureLines.push('    URL: ' + f.url);
            failureLines.push('    Volume: ' + f.volume);
            if (f.debugInfo && f.debugInfo.length > 0) {
                failureLines.push('    Debug: ' + f.debugInfo.join(' | '));
            }
            log('  ❌ "' + f.name + '" → ' + f.url, 'error');
        });
        failureLines.push('');
        failureLines.push('========================================');
        failureLines.push('请将上述 URL 在浏览器中打开，右键「检查」查看页面结构，');
        failureLines.push('特别关注分类链接的 href 是否包含 /category/ 或 /sports/');

        saveTextFile(failureLines.join('\n'), 'kalshi_failure.txt');
        log('📄 失败记录已保存到 kalshi_failure.txt', 'warn');
    } else {
        log('🎉 所有项目的分类均抓取成功，无失败记录!', 'info');
    }

    // ★ 新增：下载一个标志文件，通知 AppleScript 抓取已完成
    try {
        var doneBlob = new Blob(['done'], { type: 'text/plain' });
        var doneUrl = URL.createObjectURL(doneBlob);
        chrome.downloads.download({
            url: doneUrl,
            filename: 'kalshi_scraping_done.txt',
            conflictAction: 'overwrite',
            saveAs: false
        }, function (downloadId) {
            setTimeout(function () { URL.revokeObjectURL(doneUrl); }, 5000);
        });
    } catch (e) {
        log('  ⚠️ 标志文件保存异常: ' + e.message, 'warn');
    }

    progressContainer.style.display = 'none';
    var statusMsg = '✅ 完成! ' + finalResults.length + ' 条, 耗时 ' + elapsed + 's, 平均 ' +
        (finalResults.length > 0 ? (elapsed / finalResults.length).toFixed(1) : '0') + 's/条 → ' + outputFilename;
    if (failures.length > 0) {
        statusMsg += '  ⚠️ ' + failures.length + '个分类缺失(见kalshi_failure.txt)';
    }
    setStatus(statusMsg, 'success');

    scrapedCards = null;
    startBtn.disabled = false;
    startBtn.textContent = '重新开始';
    isRunning = false;

    // 释放屏幕常亮
    if (chrome.power) chrome.power.releaseKeepAwake();
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