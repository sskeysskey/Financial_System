document.addEventListener('DOMContentLoaded', function () {
    const scrapeButton = document.getElementById('scrapeDataButton');
    const statusDiv = document.getElementById('status');

    if (scrapeButton) {
        scrapeButton.addEventListener('click', () => {
            statusDiv.textContent = '正在请求抓取数据...';
            statusDiv.className = 'info'; // 设置状态为信息

            // 获取当前活动的标签页
            chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                if (tabs.length === 0) {
                    statusDiv.textContent = '错误：没有活动的标签页。';
                    statusDiv.className = 'error';
                    return;
                }
                const tabId = tabs[0].id;

                // 注入 content.js 到当前标签页
                chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    files: ['content.js']
                }, (injectionResults) => {
                    if (chrome.runtime.lastError) {
                        statusDiv.textContent = `注入脚本失败: ${chrome.runtime.lastError.message}`;
                        statusDiv.className = 'error';
                        console.error(`注入脚本失败: ${chrome.runtime.lastError.message}`);
                    } else if (injectionResults && injectionResults.length > 0 && injectionResults[0].result === 'already_injected') {
                        // 如果脚本已注入，可能需要发送消息来重新触发操作
                        // 为简单起见，这里假设每次注入都会执行。或者 content.js 应该设计为可重入。
                        // 目前 content.js 会在注入时自动运行。
                        // statusDiv.textContent = '脚本已注入，尝试重新触发抓取...';
                        // statusDiv.className = 'info';
                        // chrome.tabs.sendMessage(tabId, { action: "scrape" }); // 如果 content.js 监听消息
                    } else {
                        // 脚本成功注入，content.js 会自动执行其主要逻辑
                        // 状态更新将由 content.js 通过消息发送回来
                        // statusDiv.textContent = '脚本注入成功，正在抓取...'; (content.js会覆盖这个)
                    }
                });
            });
        });
    } else {
        console.error("Scrape button not found in popup.html");
        if (statusDiv) {
            statusDiv.textContent = '错误：无法找到按钮。';
            statusDiv.className = 'error';
        }
    }

    // 监听来自 content.js 的消息 (例如状态更新)
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "updateStatus") {
            statusDiv.textContent = request.message;
            statusDiv.className = request.type || 'info'; // 'success', 'error', 'info'
            // 可以在这里决定是否自动关闭popup
            // if (request.type === 'success' || request.type === 'error') {
            //   setTimeout(() => window.close(), 3000); // 3秒后关闭
            // }
        }
        // 保持消息通道开放以进行异步响应 (如果需要)
        // return true;
    });
});