// /Users/yanzhang/Coding/Financial_System/JavaScript/Prediction/popup.js

// 将抓取逻辑提取为一个独立的异步函数
async function startScraping() {
    const button = document.getElementById('scrapeBtn');
    const statusDiv = document.getElementById('status');

    button.disabled = true;
    statusDiv.textContent = '正在自动抓取数据...';
    statusDiv.className = 'info';

    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

        // 执行content script中的抓取函数
        const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: scrapePageData
        });

        if (results && results[0] && results[0].result) {
            const data = results[0].result;

            // 发送到background script保存文件
            chrome.runtime.sendMessage({
                action: 'saveData',
                data: data
            }, (response) => {
                if (response && response.success) {
                    statusDiv.textContent = `成功抓取 ${data.length} 条数据!`;
                    statusDiv.className = 'success';
                } else {
                    statusDiv.textContent = '保存失败: ' + (response ? response.error : '未知错误');
                    statusDiv.className = 'error';
                }
                button.disabled = false;
                button.textContent = '重新抓取'; // 抓取完成后修改按钮文字
            });
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

// 按钮点击事件改为调用同一个函数（用于重新抓取）
document.getElementById('scrapeBtn').addEventListener('click', startScraping);

// --- 下面的 scrapePageData 函数保持不变 ---
function scrapePageData() {
    const predictions = [];

    // 辅助函数:清理文本
    function cleanText(text) {
        return text.trim().replace(/\s+/g, ' ');
    }

    // 辅助函数:从URL提取slug
    function getSlugFromUrl(url) {
        const match = url.match(/\/event\/([^/?]+)/);
        return match ? match[1] : null;
    }

    // 辅助函数:异步获取子页面数据
    async function fetchSubpageData(slug) {
        try {
            const response = await fetch(`https://polymarket.com/event/${slug}`);
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            // 抓取type, subtype
            const breadcrumbs = doc.querySelectorAll('a[href*="/dashboards/"], a[href*="/predictions/"]');
            let type = '', subtype = '';
            breadcrumbs.forEach((link, index) => {
                const text = cleanText(link.textContent);
                if (index === 0) type = text;
                if (index === 1) subtype = text;
            });

            // 抓取enddate
            const dateSpan = doc.querySelector('span:not([class])');
            let enddate = '';
            if (dateSpan) {
                const dateText = cleanText(dateSpan.textContent);
                if (/\w+ \d+, \d{4}/.test(dateText)) {
                    enddate = dateText;
                }
            }

            return { type, subtype, enddate };
        } catch (error) {
            console.error('Error fetching subpage:', error);
            return { type: '', subtype: '', enddate: '' };
        }
    }

    // 查找所有卡片
    const cards = document.querySelectorAll('.grid > div > div[class*="flex"][class*="flex-col"][class*="rounded"]');

    cards.forEach(card => {
        try {
            // 获取标题(name)
            const titleElement = card.querySelector('h2');
            if (!titleElement) return;

            const name = cleanText(titleElement.textContent);

            // 获取事件链接
            const eventLink = card.querySelector('a[href^="/event/"]');
            if (!eventLink) return;

            const slug = getSlugFromUrl(eventLink.getAttribute('href'));
            if (!slug) return;

            // 获取volume
            const volumeElement = card.querySelector('span.uppercase');
            const volume = volumeElement ? cleanText(volumeElement.textContent) : '';

            // 检查是否是类型1(有多个选项)
            const optionElements = card.querySelectorAll('p.line-clamp-1[class*="text-body-base"]');

            if (optionElements.length > 0) {
                // 类型1: 多选项预测
                const options = [];
                const valueElements = card.querySelectorAll('p.text-\\[15px\\][class*="font-semibold"]');

                optionElements.forEach((optionEl, index) => {
                    const optionName = cleanText(optionEl.textContent);
                    const value = valueElements[index] ? cleanText(valueElements[index].textContent) : '';
                    options.push({ name: optionName, value: value });
                });

                const prediction = {
                    type: 'multi-option',
                    name: name,
                    slug: slug,
                    volume: volume,
                    options: options
                };

                predictions.push(prediction);
            } else {
                // 类型2: 单一概率预测
                const valueElement = card.querySelector('p[class*="font-medium"][class*="text-heading-lg"]');
                const value = valueElement ? cleanText(valueElement.textContent) : '';

                const prediction = {
                    type: 'single-value',
                    name: name,
                    slug: slug,
                    volume: volume,
                    value: value
                };

                predictions.push(prediction);
            }
        } catch (error) {
            console.error('Error processing card:', error);
        }
    });

    return predictions;
}

// 添加监听器以处理来自 background 的下载请求
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'downloadJson') {
        const jsonData = JSON.stringify(message.data, null, 2);
        const blob = new Blob([jsonData], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'prediction.json';
        document.body.appendChild(a);
        a.click();

        // 清理
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);
    }
});