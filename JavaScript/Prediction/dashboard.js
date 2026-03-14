// ============ 状态 ============
let mainTabId = null;

const params = new URLSearchParams(window.location.search);
mainTabId = parseInt(params.get('mainTabId'), 10);

// ============ DOM 引用 ============
const statusEl = document.getElementById('status');
const debugLogEl = document.getElementById('debugLog');
const progressContainer = document.getElementById('progressContainer');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const startBtn = document.getElementById('startBtn');
const clearBtn = document.getElementById('clearBtn');

// ============ 日志工具 ============
function log(message, type = 'info') {
    const cls = {
        info: 'log-info', warn: 'log-warn', error: 'log-error',
        data: 'log-data', section: 'log-section', dim: 'log-dim'
    }[type] || '';
    const time = new Date().toLocaleTimeString();
    const span = document.createElement('span');
    span.className = cls;
    span.textContent = `[${time}] ${message}\n`;
    debugLogEl.appendChild(span);
    debugLogEl.scrollTop = debugLogEl.scrollHeight;
}

function setStatus(text, type = 'info') {
    statusEl.textContent = text;
    statusEl.className = `status-box status-${type}`;
}

function updateProgress(current, total, name) {
    progressContainer.style.display = 'block';
    progressFill.style.width = Math.round((current / total) * 100) + '%';
    progressText.textContent = `(${current}/${total}) ${name}`;
}

// ============ 标签页管理 ============
function openTabVisible(url, waitMs) {
    return new Promise((resolve, reject) => {
        chrome.tabs.create({ url, active: true }, (tab) => {
            if (chrome.runtime.lastError) {
                return reject(new Error(chrome.runtime.lastError.message));
            }
            log(`  📄 标签已创建 (id:${tab.id})`, 'dim');

            const maxTimeout = setTimeout(() => {
                chrome.tabs.onUpdated.removeListener(onUpdate);
                log(`  ⏱️ 加载超时(30s)，强制继续`, 'warn');
                setTimeout(() => resolve(tab), waitMs);
            }, 30000);

            function onUpdate(id, info) {
                if (id === tab.id && info.status === 'complete') {
                    chrome.tabs.onUpdated.removeListener(onUpdate);
                    clearTimeout(maxTimeout);
                    log(`  ✅ status=complete`, 'dim');
                    log(`  ⏳ 等待 ${waitMs / 1000}s 渲染+安全检查...`, 'dim');
                    setTimeout(() => resolve(tab), waitMs);
                }
            }
            chrome.tabs.onUpdated.addListener(onUpdate);
        });
    });
}

function closeTab(tabId) {
    return new Promise(resolve => {
        chrome.tabs.remove(tabId, () => {
            if (chrome.runtime.lastError) {
                log(`  ⚠️ 关闭标签失败: ${chrome.runtime.lastError.message}`, 'warn');
            }
            resolve();
        });
    });
}

// ============ JSON 下载 ============
function downloadJson(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 200);
}

// ============================================================
//  以下函数都是注入到目标页面执行的（完全独立，不能引用外部变量）
// ============================================================

// ---- 注入：主页面卡片基本信息 ----
function injectedScrapeMainPage() {
    const predictions = [];
    function clean(t) { return t.trim().replace(/\s+/g, ' '); }
    function cap(s) { return s.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '); }

    const cards = document.querySelectorAll('[data-testid="market-tile"]');
    cards.forEach(card => {
        try {
            const h2 = card.querySelector('h2');
            if (!h2) return;
            const name = clean(h2.textContent);

            const subLink = card.querySelector('a[href^="/markets/"]');
            if (!subLink) return;
            const subUrl = subLink.getAttribute('href');

            const catLink = card.querySelector('a[href^="/category/"]');
            let fallbackType = '', fallbackSubtype = '';
            if (catLink) {
                fallbackSubtype = clean(catLink.textContent);
                const parts = (catLink.getAttribute('href') || '').replace('/category/', '').split('/');
                if (parts[0]) fallbackType = cap(parts[0]);
            }

            let volume = '';
            for (const span of card.querySelectorAll('span')) {
                const t = span.textContent;
                if (t.includes('$') && t.toLowerCase().includes('vol')) {
                    volume = clean(t);
                    break;
                }
            }

            const options = [];
            card.querySelectorAll('.col-span-full').forEach(row => {
                const nameEl = row.querySelector('[class*="typ-body-x30"]');
                const btn = row.querySelector('button[class*="stretched-link-action"]');
                let valEl = btn ? btn.querySelector('span.tabular-nums') : null;
                if (nameEl && !valEl) {
                    const sb = row.querySelector('button.rounded-x50[class*="stretched-link-action"]');
                    if (sb) valEl = sb.querySelector('span.tabular-nums');
                }
                if (nameEl && valEl) {
                    const v = clean(valEl.textContent);
                    options.push({ name: clean(nameEl.textContent), value: v.includes('%') ? v : v + '%' });
                }
            });

            predictions.push({ name, subUrl, volume, options, fallbackType, fallbackSubtype });
        } catch (e) { /* skip */ }
    });
    return predictions;
}

// ---- 注入：诊断子页面状态 ----
function injectedDiagnoseSubpage() {
    const d = [];
    d.push('URL: ' + location.href);
    d.push('Title: ' + document.title);
    d.push('Body HTML length: ' + document.body.innerHTML.length);

    var bodyPreview = document.body.innerText.substring(0, 500).replace(/\n+/g, ' | ');
    d.push('Body text preview: ' + bodyPreview);

    // Bot detection
    var cf1 = !!document.getElementById('challenge-form');
    var cf2 = !!document.querySelector('.cf-browser-verification');
    var cf3 = document.title.toLowerCase().includes('just a moment');
    var cf4 = !!document.querySelector('[id*="turnstile"]');
    var cf5 = !!document.querySelector('.ray-id');
    d.push('--- Bot Detection ---');
    d.push('  challenge-form: ' + cf1);
    d.push('  cf-browser-verification: ' + cf2);
    d.push('  title "Just a moment": ' + cf3);
    d.push('  turnstile: ' + cf4);
    d.push('  ray-id: ' + cf5);
    var isBotPage = cf1 || cf2 || cf3;
    d.push('  => ' + (isBotPage ? '⚠️ BOT 检测页面!' : '✅ 正常内容页面'));

    // Content
    d.push('--- Content ---');
    var sections = document.querySelectorAll('section');
    d.push('  <section>: ' + sections.length);

    var cats = document.querySelectorAll('a[href^="/category/"]');
    d.push('  category links: ' + cats.length);
    cats.forEach(function (a, i) {
        d.push('    [' + i + '] "' + a.textContent.trim() + '" -> ' + a.getAttribute('href'));
    });

    var bodyX30 = document.querySelectorAll('[class*="typ-body-x30"]');
    d.push('  typ-body-x30: ' + bodyX30.length);
    bodyX30.forEach(function (el, i) {
        d.push('    [' + i + '] "' + el.textContent.trim().substring(0, 80) + '"');
    });

    var headX10 = document.querySelectorAll('[class*="typ-headline-x10"]');
    d.push('  typ-headline-x10: ' + headX10.length);
    headX10.forEach(function (el, i) {
        d.push('    [' + i + '] "' + el.textContent.trim() + '"');
    });

    var moreFound = false;
    var allSpans = document.querySelectorAll('span');
    for (var si = 0; si < allSpans.length; si++) {
        if (allSpans[si].textContent.trim().replace(/\s+/g, ' ') === 'More markets') {
            moreFound = true;
            break;
        }
    }
    d.push('  "More markets" button: ' + moreFound);

    return { isBotPage: isBotPage, moreMarketsFound: moreFound, debug: d };
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
                d.push('Clickable ancestor: <' + target.tagName + '> class="' + (target.className || '').substring(0, 100) + '"');
                target.click();
                d.push('✅ Clicked!');
                return { clicked: true, debug: d };
            } else {
                d.push('No clickable ancestor, trying span.click()...');
                allSpans[i].click();
                d.push('Clicked span directly');
                return { clicked: true, debug: d };
            }
        }
    }
    d.push('"More markets" NOT found on page');
    return { clicked: false, debug: d };
}

// ---- 注入：抓取子页面 options ----
function injectedScrapeSubpage() {
    var d = [];
    var result = { type: '', subtype: '', options: [] };

    // 1. Categories
    d.push('--- Categories ---');
    var catLinks = document.querySelectorAll('a[href^="/category/"]');
    var cats = [];
    catLinks.forEach(function (a) {
        var t = a.textContent.trim().replace(/\s+/g, ' ');
        if (t && cats.indexOf(t) === -1) cats.push(t);
    });
    d.push('  Unique categories: ' + JSON.stringify(cats));
    if (cats.length > 0) result.type = cats[0];
    if (cats.length > 1) result.subtype = cats[1];

    // 2. Options — Approach A: typ-body-x30 + traverse up for typ-headline-x10
    d.push('--- Options (Approach A: typ-body-x30) ---');
    var seen = {};
    var section = document.querySelector('section');
    var root = section || document;
    d.push('  Search root: ' + (section ? '<section>' : '<document>'));

    var nameEls = root.querySelectorAll('[class*="typ-body-x30"]');
    d.push('  Found ' + nameEls.length + ' typ-body-x30 elements');

    nameEls.forEach(function (nameEl, idx) {
        var rawName = nameEl.textContent.trim().replace(/\s+/g, ' ');
        d.push('  [' + idx + '] text: "' + rawName + '"');

        if (!rawName) { d.push('    -> skip (empty)'); return; }
        if (rawName.toLowerCase().indexOf('more market') !== -1) { d.push('    -> skip (More markets)'); return; }
        if (rawName.toLowerCase().indexOf('fewer market') !== -1) { d.push('    -> skip (Fewer markets)'); return; }
        if (seen[rawName]) { d.push('    -> skip (dup)'); return; }

        var container = nameEl;
        var valueEl = null;
        var steps = 0;
        for (var i = 0; i < 15; i++) {
            container = container.parentElement;
            if (!container) break;
            steps++;
            valueEl = container.querySelector('h2[class*="typ-headline-x10"]');
            if (valueEl) break;
            valueEl = container.querySelector('[class*="typ-headline-x10"]');
            if (valueEl) break;
        }

        var value = valueEl ? valueEl.textContent.trim() : '';
        d.push('    -> value: "' + value + '" (↑' + steps + ' levels, tag: ' + (valueEl ? valueEl.tagName : 'none') + ')');

        seen[rawName] = true;
        result.options.push({ name: rawName, value: value });
    });

    // 3. If Approach A found nothing, try Approach B
    if (result.options.length === 0) {
        d.push('--- Options (Approach B: flex containers) ---');
        var flexDivs = root.querySelectorAll('div[style*="flex: 1 1"]');
        d.push('  Found ' + flexDivs.length + ' flex-1-1 containers');

        flexDivs.forEach(function (div, i) {
            var nEl = div.querySelector('[class*="typ-body-x30"]');
            var vEl = div.querySelector('[class*="typ-headline-x10"]');
            if (nEl && vEl) {
                var name = nEl.textContent.trim().replace(/\s+/g, ' ');
                var val = vEl.textContent.trim();
                if (name && name.toLowerCase().indexOf('more market') === -1 &&
                    name.toLowerCase().indexOf('fewer market') === -1 && !seen[name]) {
                    d.push('  [' + i + '] "' + name + '" = "' + val + '"');
                    seen[name] = true;
                    result.options.push({ name: name, value: val });
                }
            }
        });
    }

    d.push('--- Final ---');
    d.push('  type: "' + result.type + '"');
    d.push('  subtype: "' + result.subtype + '"');
    d.push('  options count: ' + result.options.length);
    result.options.forEach(function (o, i) {
        d.push('    [' + i + '] "' + o.name + '" = "' + o.value + '"');
    });

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
    });
    return r;
}

// ============ 主流程 ============
async function startScraping() {
    startBtn.disabled = true;
    debugLogEl.innerHTML = '';

    const autoClose = document.getElementById('autoClose').checked;
    const waitSec = parseInt(document.getElementById('waitTime').value, 10) || 8;
    const waitMs = waitSec * 1000;

    // ★ 读取数量限制：留空或0表示抓全部
    const limitInput = parseInt(document.getElementById('limitCount').value, 10);
    const hasLimit = !isNaN(limitInput) && limitInput > 0;

    log('════════════════════════════════════════', 'section');
    log('  Kalshi Scraper 开始', 'section');
    log('════════════════════════════════════════', 'section');
    log('mainTabId=' + mainTabId + '  autoClose=' + autoClose + '  wait=' + waitSec + 's' +
        (hasLimit ? '  限制=' + limitInput + '个' : '  限制=全部'));

    // 验证主标签页
    try {
        await new Promise((res, rej) => {
            chrome.tabs.get(mainTabId, t =>
                chrome.runtime.lastError ? rej(new Error(chrome.runtime.lastError.message)) : res(t)
            );
        });
        log('✅ 主标签页存在', 'info');
    } catch (e) {
        log('❌ 主标签页不存在: ' + e.message, 'error');
        setStatus('错误: Kalshi 主标签页已关闭，请回到 Kalshi 页面重新启动', 'error');
        startBtn.disabled = false;
        return;
    }

    // STEP 1: 主页面
    log('', 'dim');
    log('─── STEP 1: 抓取主页面卡片 ───', 'section');
    setStatus('正在抓取主页面...');

    let cards;
    try {
        const r = await chrome.scripting.executeScript({
            target: { tabId: mainTabId },
            func: injectedScrapeMainPage
        });
        cards = r && r[0] && r[0].result;
        if (!cards || cards.length === 0) {
            log('❌ 主页面未找到卡片', 'error');
            setStatus('主页面未找到数据，请确认页面已加载', 'error');
            startBtn.disabled = false;
            return;
        }

        // ★ 根据限制截取需要处理的卡片
        const totalCards = cards.length;
        if (hasLimit && limitInput < totalCards) {
            cards = cards.slice(0, limitInput);
            log('✅ 主页面共 ' + totalCards + ' 个卡片，本次限制抓取前 ' + limitInput + ' 个', 'warn');
        } else {
            log('✅ 找到 ' + totalCards + ' 个卡片，全部抓取', 'info');
        }

        cards.forEach(function (c, i) {
            log('  [' + i + '] "' + c.name + '"', 'data');
            log('       subUrl: ' + c.subUrl, 'dim');
            log('       主页options: ' + c.options.length + '个  volume: ' + c.volume, 'dim');
        });
    } catch (e) {
        log('❌ 主页面脚本失败: ' + e.message, 'error');
        setStatus('主页面抓取失败', 'error');
        startBtn.disabled = false;
        return;
    }

    // STEP 2: 逐个子页面
    const results = [];

    for (let i = 0; i < cards.length; i++) {
        const card = cards[i];
        const short = card.name.length > 40 ? card.name.substring(0, 40) + '...' : card.name;

        log('', 'dim');
        log('─── CARD ' + (i + 1) + '/' + cards.length + ': "' + short + '" ───', 'section');
        setStatus('(' + (i + 1) + '/' + cards.length + ') ' + short);
        updateProgress(i + 1, cards.length, short);

        let subTab = null;
        try {
            const url = 'https://kalshi.com' + card.subUrl;
            log('  打开: ' + url);
            subTab = await openTabVisible(url, waitMs);

            // 2a: 诊断
            log('  🔍 诊断页面状态...', 'info');
            const diagR = await chrome.scripting.executeScript({
                target: { tabId: subTab.id },
                func: injectedDiagnoseSubpage
            });
            const diag = (diagR && diagR[0] && diagR[0].result) || { isBotPage: true, debug: ['诊断返回空'] };
            diag.debug.forEach(function (l) { log('    ' + l, 'dim'); });

            if (diag.isBotPage) {
                log('  ⚠️ 检测到反爬虫页面! 额外等待 12s...', 'warn');
                await new Promise(function (r) { setTimeout(r, 12000); });

                log('  🔍 重新诊断...', 'info');
                const diagR2 = await chrome.scripting.executeScript({
                    target: { tabId: subTab.id },
                    func: injectedDiagnoseSubpage
                });
                const diag2 = (diagR2 && diagR2[0] && diagR2[0].result) || { isBotPage: true, debug: [] };
                diag2.debug.forEach(function (l) { log('    ' + l, 'dim'); });

                if (diag2.isBotPage) {
                    log('  ❌ 反爬虫页面未消除 → 使用主页面备选数据', 'error');
                    results.push(buildFallback(card));
                    if (autoClose && subTab) await closeTab(subTab.id);
                    continue;
                }
            }

            // 2b: 点击 More markets
            log('  🖱️ 查找 "More markets"...', 'info');
            const clickR = await chrome.scripting.executeScript({
                target: { tabId: subTab.id },
                func: injectedClickMore
            });
            const clickD = (clickR && clickR[0] && clickR[0].result) || { clicked: false, debug: [] };
            clickD.debug.forEach(function (l) { log('    ' + l, 'dim'); });

            if (clickD.clicked) {
                log('  ✅ 已点击展开，等 3s...', 'info');
                await new Promise(function (r) { setTimeout(r, 3000); });
            } else {
                log('  ℹ️ 无需展开（按钮不存在 = 选项已全部显示）', 'dim');
            }

            // 2c: 抓取
            log('  📊 抓取 options...', 'info');
            const scrapeR = await chrome.scripting.executeScript({
                target: { tabId: subTab.id },
                func: injectedScrapeSubpage
            });
            const sub = (scrapeR && scrapeR[0] && scrapeR[0].result) ||
                { type: '', subtype: '', options: [], debug: [] };
            sub.debug.forEach(function (l) { log('    ' + l, 'dim'); });

            // 2d: 组装
            const final = {
                name: card.name,
                type: sub.type || card.fallbackType || '',
                subtype: sub.subtype || card.fallbackSubtype || '',
                volume: card.volume,
                hide: "1"
            };

            const opts = (sub.options && sub.options.length > 0) ? sub.options : card.options;
            const source = (sub.options && sub.options.length > 0) ? '子页面' : '主页面(备选)';
            log('  📋 Options 来源: ' + source + ' (' + opts.length + '个)',
                source === '子页面' ? 'info' : 'warn');

            opts.forEach(function (o, j) {
                final['option' + (j + 1)] = o.name;
                final['value' + (j + 1)] = o.value;
                log('    option' + (j + 1) + ': "' + o.name + '" = ' + o.value, 'data');
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

        // 间隔
        if (i < cards.length - 1) {
            await new Promise(function (r) { setTimeout(r, 1000); });
        }
    }

    // STEP 3: 下载
    log('', 'dim');
    log('════════════════════════════════════════', 'section');
    log('  完成! 共 ' + results.length + ' 条数据' + (hasLimit ? '（已按限制提前终止）' : ''), 'section');
    log('════════════════════════════════════════', 'section');

    downloadJson(results, 'kalshi.json');
    setStatus('✅ 成功! ' + results.length + ' 条数据已下载' + (hasLimit ? '（限制模式）' : ''), 'success');
    progressContainer.style.display = 'none';
    startBtn.disabled = false;
    startBtn.textContent = '重新抓取';
}

// ============ 事件 ============
startBtn.addEventListener('click', startScraping);
clearBtn.addEventListener('click', function () {
    debugLogEl.innerHTML = '';
    log('日志已清空');
});

// ============ 初始化 ============
if (mainTabId && !isNaN(mainTabId)) {
    log('Dashboard 就绪. mainTabId = ' + mainTabId);
    setStatus('就绪 — 点击「开始抓取」');
} else {
    log('⚠️ 缺少 mainTabId 参数', 'warn');
    setStatus('错误: 请从 Kalshi 页面点击扩展图标启动', 'error');
    startBtn.disabled = true;
}