// ============ 配置常量 ============
const POLYMARKET_CLICK_COUNT = 10; // 配置点击 "Show more markets" 的次数
const CLICK_INTERVAL = 1500; // 每次点击后的等待时间（毫秒）

// ============ 工具函数 ============

function downloadJson(data, filename) {
    const jsonData = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
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

// ============ 主入口 ============

async function startScraping() {
    const button = document.getElementById('scrapeBtn');
    const statusDiv = document.getElementById('status');
    const titleEl = document.getElementById('title');

    button.disabled = true;
    statusDiv.textContent = '正在自动检测网站...';
    statusDiv.className = 'info';

    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const url = tab.url;

        if (url.includes('polymarket.com')) {
            titleEl.textContent = 'Polymarket 数据抓取';
            await handlePolymarket(tab, statusDiv, button);
        } else if (url.includes('kalshi.com')) {
            titleEl.textContent = 'Kalshi 数据抓取';
            await handleKalshi(tab, statusDiv, button);
        } else {
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

// ============ Polymarket 处理（增强版：自动点击展开） ============

async function handlePolymarket(tab, statusDiv, button) {
    const progressContainer = document.getElementById('progressContainer');
    const progressBarFill = document.getElementById('progressBarFill');
    const progressText = document.getElementById('progressText');

    progressContainer.style.display = 'block';

    try {
        // 第一步：自动点击 "Show more markets" 按钮
        statusDiv.textContent = `正在展开更多市场 (0/${POLYMARKET_CLICK_COUNT})...`;

        for (let i = 0; i < POLYMARKET_CLICK_COUNT; i++) {
            const clickResult = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: clickShowMoreButton
            });

            const clicked = clickResult && clickResult[0] && clickResult[0].result;

            if (!clicked) {
                statusDiv.textContent = `已展开 ${i} 次（未找到更多按钮）`;
                break;
            }

            // 更新进度
            const progress = ((i + 1) / POLYMARKET_CLICK_COUNT) * 100;
            progressBarFill.style.width = `${progress}%`;
            progressText.textContent = `正在展开市场: ${i + 1}/${POLYMARKET_CLICK_COUNT}`;
            statusDiv.textContent = `正在展开更多市场 (${i + 1}/${POLYMARKET_CLICK_COUNT})...`;

            // 等待页面加载新内容
            await new Promise(resolve => setTimeout(resolve, CLICK_INTERVAL));

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

            // 额外等待滚动和渲染
            await new Promise(resolve => setTimeout(resolve, 1000));
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

// ============ Kalshi 处理 → 打开调试面板（自动开始） ============

async function handleKalshi(tab, statusDiv, button) {
    const dashboardUrl = chrome.runtime.getURL('dashboard.html') + '?mainTabId=' + tab.id + '&auto=1';
    chrome.tabs.create({ url: dashboardUrl, active: true });
    statusDiv.textContent = '已打开 Kalshi 调试面板（自动抓取中）';
    statusDiv.className = 'info';
    button.disabled = false;
}

// ============ Polymarket 主页面抓取函数（保持原逻辑不变） ============

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
    startScraping();
});

document.getElementById('scrapeBtn').addEventListener('click', startScraping);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'downloadJson') {
        downloadJson(message.data, message.filename || 'prediction.json');
    }
});