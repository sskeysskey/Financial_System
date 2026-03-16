// ============ 配置常量 ============
const POLYMARKET_CLICK_COUNT = 20;
const BUTTON_CHECK_INTERVAL = 500;
const MAX_WAIT_TIME = 30000;
const DEFAULT_KALSHI_SCROLL_COUNT = 5; // ← 唯一需要改的地方

// ============ 工具函数 ============

function downloadJson(data, filename) {
    const jsonData = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);  // ✅ 修正：应该是 blob
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, 100);
}

// ============ 获取 Kalshi 滚动次数 ============
function getKalshiScrollCount() {
    const input = document.getElementById('scrollCountInput');
    const val = parseInt(input.value, 10);
    if (val >= 1 && val <= 50) {
        return val;
    }
    return DEFAULT_KALSHI_SCROLL_COUNT;
}

// ============ 主入口 ============

async function startScraping() {
    const button = document.getElementById('scrapeBtn');
    const statusDiv = document.getElementById('status');
    const titleEl = document.getElementById('title');
    const kalshiConfig = document.getElementById('kalshiConfig');
    const scrollCountInput = document.getElementById('scrollCountInput');

    button.disabled = true;
    statusDiv.textContent = '正在自动检测网站...';
    statusDiv.className = 'info';

    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const url = tab.url;

        if (url.includes('polymarket.com')) {
            titleEl.textContent = 'Polymarket 数据抓取';
            kalshiConfig.style.display = 'none';
            await handlePolymarket(tab, statusDiv, button);
        } else if (url.includes('kalshi.com')) {
            titleEl.textContent = 'Kalshi 数据抓取';
            kalshiConfig.style.display = 'block';
            await handleKalshi(tab, statusDiv, button);
        } else {
            kalshiConfig.style.display = 'none';
            statusDiv.textContent = '请在 Polymarket 或 Kalshi 页面使用此扩展';
            statusDiv.className = 'error';
            button.disabled = false;
        }
    } catch (error) {
        statusDiv.textContent = '错误: ' + error.message;
        statusDiv.className = 'error';
        button.disabled = false;
    }
}

// ============ Polymarket 处理（增强版：持续等待按钮出现） ============

async function handlePolymarket(tab, statusDiv, button) {
    const progressContainer = document.getElementById('progressContainer');
    const progressBarFill = document.getElementById('progressBarFill');
    const progressText = document.getElementById('progressText');

    progressContainer.style.display = 'block';

    try {
        // 第一步：自动点击 "Show more markets" 按钮
        statusDiv.textContent = `正在展开更多市场 (0/${POLYMARKET_CLICK_COUNT})...`;

        for (let i = 0; i < POLYMARKET_CLICK_COUNT; i++) {
            // 持续等待按钮出现
            statusDiv.textContent = `等待按钮出现 (${i + 1}/${POLYMARKET_CLICK_COUNT})...`;

            const buttonFound = await waitForButtonAndClick(tab);

            if (!buttonFound) {
                statusDiv.textContent = `已展开 ${i} 次（等待超时，可能已加载完所有市场）`;
                break;
            }

            // 更新进度
            const progress = ((i + 1) / POLYMARKET_CLICK_COUNT) * 100;
            progressBarFill.style.width = `${progress}%`;
            progressText.textContent = `已展开市场: ${i + 1}/${POLYMARKET_CLICK_COUNT}`;
            statusDiv.textContent = `正在展开更多市场 (${i + 1}/${POLYMARKET_CLICK_COUNT})...`;

            // 滚动到页面底部，确保新内容加载
            await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: () => {
                    window.scrollTo({
                        top: document.body.scrollHeight,
                        behavior: 'smooth'
                    });
                }
            });

            // 短暂等待滚动完成
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        // 第二步：抓取数据
        statusDiv.textContent = '正在抓取 Polymarket 数据...';
        progressText.textContent = '正在抓取数据...';

        const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: scrapePolymarketPageData
        });

        if (results && results[0] && results[0].result) {
            const data = results[0].result;
            chrome.runtime.sendMessage(
                { action: 'saveData', data: data, site: 'polymarket' },
                (response) => {
                    progressContainer.style.display = 'none';
                    if (response && response.success) {
                        statusDiv.textContent = `成功抓取 ${data.length} 条 Polymarket 数据!`;
                        statusDiv.className = 'success';
                    } else {
                        statusDiv.textContent = '保存失败: ' + (response ? response.error : '未知错误');
                        statusDiv.className = 'error';
                    }
                    button.disabled = false;
                    button.textContent = '重新抓取';
                }
            );
        } else {
            progressContainer.style.display = 'none';
            statusDiv.textContent = '未找到 Polymarket 数据';
            statusDiv.className = 'error';
            button.disabled = false;
        }
    } catch (error) {
        progressContainer.style.display = 'none';
        statusDiv.textContent = '展开失败: ' + error.message;
        statusDiv.className = 'error';
        button.disabled = false;
    }
}

// ============ 持续等待按钮出现并点击 ============

async function waitForButtonAndClick(tab) {
    const startTime = Date.now();

    while (Date.now() - startTime < MAX_WAIT_TIME) {
        // 尝试查找并点击按钮
        const clickResult = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: clickShowMoreButton
        });

        const clicked = clickResult && clickResult[0] && clickResult[0].result;

        if (clicked) {
            return true; // 找到并点击了按钮
        }

        // 等待一段时间后再次检查
        await new Promise(resolve => setTimeout(resolve, BUTTON_CHECK_INTERVAL));
    }

    return false; // 超时仍未找到按钮
}

// ============ 注入函数：点击 "Show more markets" 按钮 ============

function clickShowMoreButton() {
    // 查找按钮（支持多种可能的文本）
    const buttons = Array.from(document.querySelectorAll('button'));
    const showMoreButton = buttons.find(btn => {
        const text = btn.textContent.trim().toLowerCase();
        return text === 'show more markets' ||
            text.includes('show more') ||
            text.includes('load more');
    });

    if (showMoreButton) {
        showMoreButton.click();
        return true;
    }
    return false;
}

// ============ Kalshi 滚屏函数 ============

async function scrollKalshiPage(tab, scrollCount, statusDiv, progressBarFill, progressText) {
    statusDiv.textContent = `正在滚动 Kalshi 页面 (0/${scrollCount})...`;

    for (let i = 0; i < scrollCount; i++) {
        // 滚动到页面底部
        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
                window.scrollTo({
                    top: document.body.scrollHeight,
                    behavior: 'smooth'
                });
            }
        });

        // 更新进度
        const progress = ((i + 1) / scrollCount) * 100;
        progressBarFill.style.width = `${progress}%`;
        progressText.textContent = `滚动进度: ${i + 1}/${scrollCount}`;
        statusDiv.textContent = `正在滚动 Kalshi 页面 (${i + 1}/${scrollCount})...`;

        // 等待内容加载（每次滚动间隔 1.5 秒）
        await new Promise(resolve => setTimeout(resolve, 1500));
    }

    // 滚动回顶部
    await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        }
    });

    await new Promise(resolve => setTimeout(resolve, 800));
}

// ============ Kalshi 处理（完整版，包含滚屏）============
async function handleKalshi(tab, statusDiv, button) {
    const progressContainer = document.getElementById('progressContainer');
    const progressBarFill = document.getElementById('progressBarFill');
    const progressText = document.getElementById('progressText');

    progressContainer.style.display = 'block';

    try {
        // ← 直接从 input 读取，不再依赖 localStorage
        const scrollCount = getKalshiScrollCount();

        // 第一步：滚动页面
        await scrollKalshiPage(tab, scrollCount, statusDiv, progressBarFill, progressText);

        // 第二步：打开调试面板开始抓取
        progressContainer.style.display = 'none';
        const dashboardUrl = chrome.runtime.getURL('dashboard.html') + '?mainTabId=' + tab.id + '&auto=1';
        chrome.tabs.create({ url: dashboardUrl, active: true });
        statusDiv.textContent = `已完成 ${scrollCount} 次滚动，正在打开调试面板...`;
        statusDiv.className = 'success';
        button.disabled = false;
        button.textContent = '重新抓取';
    } catch (error) {
        progressContainer.style.display = 'none';
        statusDiv.textContent = '滚动失败: ' + error.message;
        statusDiv.className = 'error';
        button.disabled = false;
    }
}

// ============ Polymarket 抓取函数 ============
function scrapePolymarketPageData() {
    const predictions = [];

    function cleanText(text) {
        return text.trim().replace(/\s+/g, ' ');
    }

    function getSlugFromUrl(url) {
        const match = url.match(/\/event\/([^/?]+)/);
        return match ? match[1] : null;
    }

    const cards = document.querySelectorAll('.grid > div > div[class*="flex"][class*="flex-col"][class*="rounded"]');

    cards.forEach(card => {
        try {
            const titleElement = card.querySelector('h2');
            if (!titleElement) return;
            const name = cleanText(titleElement.textContent);

            const eventLink = card.querySelector('a[href^="/event/"]');
            if (!eventLink) return;
            const slug = getSlugFromUrl(eventLink.getAttribute('href'));
            if (!slug) return;

            const volumeElement = card.querySelector('span.uppercase');
            const volume = volumeElement ? cleanText(volumeElement.textContent) : '';

            const optionElements = card.querySelectorAll('p.line-clamp-1[class*="text-body-base"]');

            if (optionElements.length > 0) {
                const options = [];
                const valueElements = card.querySelectorAll('p.text-\\[15px\\][class*="font-semibold"]');

                optionElements.forEach((optionEl, index) => {
                    const optionName = cleanText(optionEl.textContent);
                    const value = valueElements[index] ? cleanText(valueElements[index].textContent) : '';
                    options.push({ name: optionName, value: value });
                });

                predictions.push({
                    type: 'multi-option',
                    name: name,
                    slug: slug,
                    volume: volume,
                    options: options
                });
            } else {
                const valueElement = card.querySelector('p[class*="font-medium"][class*="text-heading-lg"]');
                const value = valueElement ? cleanText(valueElement.textContent) : '';

                predictions.push({
                    type: 'single-value',
                    name: name,
                    slug: slug,
                    volume: volume,
                    value: value
                });
            }
        } catch (error) {
            console.error('Error processing Polymarket card:', error);
        }
    });

    return predictions;
}

// ============ 事件监听 ============

document.addEventListener('DOMContentLoaded', () => {
    // 直接用常量设置默认值，不再从 localStorage 读取
    document.getElementById('scrollCountInput').value = DEFAULT_KALSHI_SCROLL_COUNT;
    startScraping();
});

document.getElementById('scrapeBtn').addEventListener('click', startScraping);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'downloadJson') {
        downloadJson(message.data, message.filename || 'prediction.json');
    }
});