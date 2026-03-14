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

// ============ Polymarket 处理（保持原逻辑） ============

async function handlePolymarket(tab, statusDiv, button) {
    statusDiv.textContent = '正在抓取 Polymarket 数据...';

    const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: scrapePolymarketPageData
    });

    if (results && results[0] && results[0].result) {
        const data = results[0].result;
        chrome.runtime.sendMessage(
            { action: 'saveData', data: data, site: 'polymarket' },
            (response) => {
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
        statusDiv.textContent = '未找到 Polymarket 数据';
        statusDiv.className = 'error';
        button.disabled = false;
    }
}

// ============ Kalshi 处理 → 打开调试面板 ============

async function handleKalshi(tab, statusDiv, button) {
    const dashboardUrl = chrome.runtime.getURL('dashboard.html') + '?mainTabId=' + tab.id;
    chrome.tabs.create({ url: dashboardUrl, active: true });
    statusDiv.textContent = '已打开 Kalshi 调试面板（新标签页）';
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