// 根据当前页面自动检测网站并抓取
async function startScraping() {
    const button = document.getElementById('scrapeBtn');
    const statusDiv = document.getElementById('status');
    const titleEl = document.getElementById('title');

    button.disabled = true;
    statusDiv.textContent = '正在自动抓取数据...';
    statusDiv.className = 'info';

    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const url = tab.url;

        let site, scrapeFunc;

        if (url.includes('polymarket.com')) {
            site = 'polymarket';
            scrapeFunc = scrapePolymarketPageData;
            titleEl.textContent = 'Polymarket 数据抓取';
        } else if (url.includes('kalshi.com')) {
            site = 'kalshi';
            scrapeFunc = scrapeKalshiPageData;
            titleEl.textContent = 'Kalshi 数据抓取';
        } else {
            statusDiv.textContent = '请在 Polymarket 或 Kalshi 页面使用此扩展';
            statusDiv.className = 'error';
            button.disabled = false;
            return;
        }

        const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: scrapeFunc
        });

        if (results && results[0] && results[0].result) {
            const data = results[0].result;

            chrome.runtime.sendMessage(
                { action: 'saveData', data: data, site: site },
                (response) => {
                    if (response && response.success) {
                        statusDiv.textContent = `成功抓取 ${data.length} 条 ${site} 数据!`;
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
            statusDiv.textContent = '未找到数据';
            statusDiv.className = 'error';
            button.disabled = false;
        }
    } catch (error) {
        statusDiv.textContent = '错误: ' + error.message;
        statusDiv.className = 'error';
        button.disabled = false;
    }
}

// 页面加载完成时自动执行
document.addEventListener('DOMContentLoaded', () => {
    startScraping();
});

// 按钮点击事件（重新抓取）
document.getElementById('scrapeBtn').addEventListener('click', startScraping);

// ============ Polymarket 主页面抓取函数（保持原逻辑） ============
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

// ============ Kalshi 主页面抓取函数 ============
function scrapeKalshiPageData() {
    const predictions = [];

    function cleanText(text) {
        return text.trim().replace(/\s+/g, ' ');
    }

    // 将 URL 路径片段转为首字母大写的单词（如 politics → Politics）
    function capitalizeWords(str) {
        return str.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    }

    const cards = document.querySelectorAll('[data-testid="market-tile"]');

    cards.forEach(card => {
        try {
            // 获取 name
            const h2 = card.querySelector('h2');
            if (!h2) return;
            const name = cleanText(h2.textContent);

            // 获取子页面 URL
            const subLink = card.querySelector('a[href^="/markets/"]');
            if (!subLink) return;
            const subUrl = subLink.getAttribute('href');

            // 获取 category 信息（作为 type/subtype 的备选来源）
            const categoryLink = card.querySelector('a[href^="/category/"]');
            let fallbackType = '';
            let fallbackSubtype = '';
            if (categoryLink) {
                const href = categoryLink.getAttribute('href') || '';
                fallbackSubtype = cleanText(categoryLink.textContent);
                // 从 /category/politics/us-elections 中解析 type
                const parts = href.replace('/category/', '').split('/');
                if (parts.length > 0 && parts[0]) {
                    fallbackType = capitalizeWords(parts[0]);
                }
            }

            // 获取 volume（寻找包含 "$" 和 "vol" 的 span）
            let volume = '';
            const allSpans = card.querySelectorAll('span');
            for (const span of allSpans) {
                const t = span.textContent;
                if (t.includes('$') && t.toLowerCase().includes('vol')) {
                    volume = cleanText(t);
                    break;
                }
            }

            // 🔧 修改这里：改进 options 抓取逻辑
            const options = [];
            const optionRows = card.querySelectorAll('.col-span-full');
            optionRows.forEach(row => {
                const nameEl = row.querySelector('[class*="typ-body-x30"]');
                // 改为直接在 button 中查找 tabular-nums
                const button = row.querySelector('button[class*="stretched-link-action"]');
                const valueEl = button ? button.querySelector('span.tabular-nums') : null;

                if (nameEl && valueEl) {
                    options.push({
                        name: cleanText(nameEl.textContent),
                        value: cleanText(valueEl.textContent) + '%'
                    });
                }
            });

            predictions.push({
                type: 'multi-option',
                name: name,
                subUrl: subUrl,
                volume: volume,
                options: options,
                fallbackType: fallbackType,
                fallbackSubtype: fallbackSubtype
            });
        } catch (error) {
            console.error('Error processing Kalshi card:', error);
        }
    });

    return predictions;
}

// ============ 下载处理 ============
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'downloadJson') {
        const jsonData = JSON.stringify(message.data, null, 2);
        const blob = new Blob([jsonData], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = message.filename || 'prediction.json';
        document.body.appendChild(a);
        a.click();

        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);
    }
});