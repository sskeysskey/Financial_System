// ============ 配置 ============
const DEFAULT_KALSHI_SCROLL_COUNT = 30;
const DEFAULT_POLYMARKET_SCROLL_COUNT = 5;
const POLYMARKET_URL = 'https://polymarket.com/predictions';

// ============ 获取滚动次数 ============
function getKalshiScrollCount() {
    var val = parseInt(document.getElementById('scrollCountInput').value, 10);
    return (val >= 1 && val <= 50) ? val : DEFAULT_KALSHI_SCROLL_COUNT;
}

function getPolymarketScrollCount() {
    var val = parseInt(document.getElementById('polymarketScrollCountInput').value, 10);
    return (val >= 1 && val <= 100) ? val : DEFAULT_POLYMARKET_SCROLL_COUNT;
}

// ============ 通用滚动 ============
async function scrollPage(tab, scrollCount, label, statusDiv, progressBarFill, progressText) {
    statusDiv.textContent = '正在滚动 ' + label + ' (0/' + scrollCount + ')...';
    for (var i = 0; i < scrollCount; i++) {
        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: function () { window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }); }
        });
        var progress = ((i + 1) / scrollCount) * 100;
        progressBarFill.style.width = progress + '%';
        progressText.textContent = '滚动进度: ' + (i + 1) + '/' + scrollCount;
        statusDiv.textContent = '正在滚动 ' + label + ' (' + (i + 1) + '/' + scrollCount + ')...';
        await new Promise(function (r) { setTimeout(r, 1800); });
    }
    // 回顶
    await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: function () { window.scrollTo({ top: 0, behavior: 'smooth' }); }
    });
    await new Promise(function (r) { setTimeout(r, 800); });
}

// ============ 主入口 ============
async function startScraping() {
    var button = document.getElementById('scrapeBtn');
    var statusDiv = document.getElementById('status');
    var titleEl = document.getElementById('title');
    var kalshiConfig = document.getElementById('kalshiConfig');
    var polymarketConfig = document.getElementById('polymarketConfig');

    button.disabled = true;
    statusDiv.textContent = '正在自动检测网站...';
    statusDiv.className = 'info';
    if (chrome.power) chrome.power.requestKeepAwake('display');

    try {
        var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        var tab = tabs[0];
        var url = tab.url || '';

        if (url.includes('polymarket.com')) {
            titleEl.textContent = 'Polymarket 数据抓取';
            kalshiConfig.style.display = 'none';
            polymarketConfig.style.display = 'block';
            await handlePolymarket(tab, statusDiv, button);
        } else if (url.includes('kalshi.com')) {
            titleEl.textContent = 'Kalshi 数据抓取';
            polymarketConfig.style.display = 'none';
            kalshiConfig.style.display = 'block';
            await handleKalshi(tab, statusDiv, button);
        } else {
            kalshiConfig.style.display = 'none';
            polymarketConfig.style.display = 'none';
            statusDiv.textContent = '请在 Polymarket 或 Kalshi 页面使用此扩展';
            statusDiv.className = 'error';
            button.disabled = false;
            if (chrome.power) chrome.power.releaseKeepAwake();
        }
    } catch (e) {
        statusDiv.textContent = '错误: ' + e.message;
        statusDiv.className = 'error';
        button.disabled = false;
        if (chrome.power) chrome.power.releaseKeepAwake();
    }
}

// ============ Polymarket 处理（新流程）============
async function handlePolymarket(tab, statusDiv, button) {
    var progressContainer = document.getElementById('progressContainer');
    var progressBarFill = document.getElementById('progressBarFill');
    var progressText = document.getElementById('progressText');
    progressContainer.style.display = 'block';

    try {
        // 如果不在 /predictions 页面，先跳转
        if (!tab.url.includes('/predictions')) {
            statusDiv.textContent = '正在跳转到 predictions 页面...';
            await chrome.tabs.update(tab.id, { url: POLYMARKET_URL });
            // 等待加载
            await new Promise(function (resolve) {
                function listener(id, info) {
                    if (id === tab.id && info.status === 'complete') {
                        chrome.tabs.onUpdated.removeListener(listener);
                        resolve();
                    }
                }
                chrome.tabs.onUpdated.addListener(listener);
                setTimeout(function () { chrome.tabs.onUpdated.removeListener(listener); resolve(); }, 15000);
            });
            await new Promise(function (r) { setTimeout(r, 2000); });
        }

        var scrollCount = getPolymarketScrollCount();
        await scrollPage(tab, scrollCount, 'Polymarket', statusDiv, progressBarFill, progressText);

        progressContainer.style.display = 'none';
        var dashboardUrl = chrome.runtime.getURL('polymarket_dashboard.html') + '?mainTabId=' + tab.id + '&auto=1';
        chrome.tabs.create({ url: dashboardUrl, active: true });
        statusDiv.textContent = '已完成 ' + scrollCount + ' 次滚动，正在打开调试面板...';
        statusDiv.className = 'success';
        button.disabled = false;
        button.textContent = '重新抓取';
        if (chrome.power) chrome.power.releaseKeepAwake();
    } catch (e) {
        progressContainer.style.display = 'none';
        statusDiv.textContent = '失败: ' + e.message;
        statusDiv.className = 'error';
        button.disabled = false;
        if (chrome.power) chrome.power.releaseKeepAwake();
    }
}

// ============ Kalshi 处理 ============
async function handleKalshi(tab, statusDiv, button) {
    var progressContainer = document.getElementById('progressContainer');
    var progressBarFill = document.getElementById('progressBarFill');
    var progressText = document.getElementById('progressText');
    progressContainer.style.display = 'block';

    try {
        var scrollCount = getKalshiScrollCount();
        await scrollPage(tab, scrollCount, 'Kalshi', statusDiv, progressBarFill, progressText);

        progressContainer.style.display = 'none';
        var dashboardUrl = chrome.runtime.getURL('dashboard.html') + '?mainTabId=' + tab.id + '&auto=1';
        chrome.tabs.create({ url: dashboardUrl, active: true });
        statusDiv.textContent = '已完成 ' + scrollCount + ' 次滚动，正在打开调试面板...';
        statusDiv.className = 'success';
        button.disabled = false;
        button.textContent = '重新抓取';
        if (chrome.power) chrome.power.releaseKeepAwake();
    } catch (e) {
        progressContainer.style.display = 'none';
        statusDiv.textContent = '滚动失败: ' + e.message;
        statusDiv.className = 'error';
        button.disabled = false;
        if (chrome.power) chrome.power.releaseKeepAwake();
    }
}

// ============ 事件 ============
document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('scrollCountInput').value = DEFAULT_KALSHI_SCROLL_COUNT;
    document.getElementById('polymarketScrollCountInput').value = DEFAULT_POLYMARKET_SCROLL_COUNT;
    startScraping();
});

document.getElementById('scrapeBtn').addEventListener('click', startScraping);