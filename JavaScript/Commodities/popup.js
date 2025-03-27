document.addEventListener('DOMContentLoaded', function () {
    const statusDiv = document.getElementById('status');
    const progressBar = document.getElementById('progressBar');

    // 定义要爬取的商品列表
    const commodities = [
        "Coal", "Uranium", "Steel", "Lithium", "Wheat", "Palm Oil", "Aluminum",
        "Nickel", "Tin", "Zinc", "Palladium", "Poultry", "Salmon", "Iron Ore", "Orange Juice"
    ];

    // 添加日志到状态面板
    function log(message, type = 'info') {
        const logItem = document.createElement('div');
        logItem.className = `log-item ${type}`;
        logItem.textContent = `${new Date().toLocaleTimeString()}: ${message}`;
        statusDiv.appendChild(logItem);
        statusDiv.scrollTop = statusDiv.scrollHeight;
    }

    // 更新进度条
    function updateProgress(value) {
        progressBar.value = value;
    }

    // 监听来自background的消息
    chrome.runtime.onMessage.addListener((message) => {
        if (message.action === "downloadStatus") {
            if (message.success) {
                log(`成功下载文件`, 'success');
                updateProgress(100);
            } else {
                log(`下载文件失败: ${message.error}`, 'error');
            }
        }
    });

    // 自动开始爬取数据
    async function startScraping() {
        let newTab = null;

        try {
            // 获取当前日期
            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            const dateStr = yesterday.toISOString().split('T')[0]; // 格式 YYYY-MM-DD

            log('开始爬取数据...');

            // 创建一个新的标签页但不激活它
            newTab = await chrome.tabs.create({
                url: 'about:blank',
                active: false
            });

            // 准备CSV数据
            let csvData = [['date', 'name', 'price', 'category']];

            // 首先爬取 Baltic Dry 价格
            log('爬取Baltic Dry价格...');
            updateProgress(10);

            // 更新新创建的标签页导航到Baltic Dry页面
            await chrome.tabs.update(newTab.id, { url: 'https://tradingeconomics.com/commodity/baltic' });

            // 等待页面加载完成
            await new Promise(resolve => setTimeout(resolve, 3000));

            // 执行内容脚本获取价格
            const balticDryResult = await chrome.scripting.executeScript({
                target: { tabId: newTab.id },
                function: () => {
                    try {
                        const priceElement = document.querySelector("div.table-responsive table tr td:nth-child(2)");
                        return priceElement ? priceElement.textContent.trim() : null;
                    } catch (e) {
                        return { error: e.message };
                    }
                }
            });

            const balticDryPrice = balticDryResult[0].result;

            if (balticDryPrice && !balticDryPrice.error) {
                const price = parseFloat(balticDryPrice.replace(',', ''));
                csvData.push([dateStr, 'BalticDry', price, 'Commodities']);
                log(`成功获取Baltic Dry价格: ${price}`, 'success');
            } else {
                log(`获取Baltic Dry价格失败: ${balticDryPrice?.error || 'Unknown error'}`, 'error');
            }

            // 更新进度
            updateProgress(30);

            // 打开商品页面
            log('打开商品页面...');
            await chrome.tabs.update(newTab.id, { url: 'https://tradingeconomics.com/commodities' });

            // 等待页面加载完成
            await new Promise(resolve => setTimeout(resolve, 3000));

            // 爬取所有商品价格
            log('爬取商品价格...');

            // 执行内容脚本获取所有商品价格
            const commoditiesResult = await chrome.scripting.executeScript({
                target: { tabId: newTab.id },
                function: (commoditiesList) => {
                    try {
                        const results = [];

                        for (const commodity of commoditiesList) {
                            try {
                                // 查找商品链接
                                const commodityLink = Array.from(document.querySelectorAll('a')).find(a =>
                                    a.textContent.includes(commodity) && a.href.includes('/commodity/')
                                );

                                if (!commodityLink) {
                                    results.push({ name: commodity, error: 'Commodity link not found' });
                                    continue;
                                }

                                // 获取包含价格的行
                                const row = commodityLink.closest('tr');
                                if (!row) {
                                    results.push({ name: commodity, error: 'Row not found' });
                                    continue;
                                }

                                // 获取价格单元格
                                const priceCell = row.querySelector('td#p');
                                if (!priceCell) {
                                    results.push({ name: commodity, error: 'Price cell not found' });
                                    continue;
                                }

                                const price = priceCell.textContent.trim();
                                results.push({ name: commodity, price });
                            } catch (e) {
                                results.push({ name: commodity, error: e.message });
                            }
                        }

                        return results;
                    } catch (e) {
                        return { error: e.message };
                    }
                },
                args: [commodities]
            });

            const commoditiesData = commoditiesResult[0].result;

            if (Array.isArray(commoditiesData)) {
                for (const item of commoditiesData) {
                    if (item.price) {
                        const price = parseFloat(item.price.replace(',', ''));
                        csvData.push([dateStr, item.name.replace(' ', ''), price, 'Commodities']);
                        log(`成功获取${item.name}价格: ${price}`, 'success');
                    } else {
                        log(`获取${item.name}价格失败: ${item.error || 'Unknown error'}`, 'error');
                    }
                }
            } else {
                log(`爬取商品价格失败: ${commoditiesData?.error || 'Unknown error'}`, 'error');
            }

            // 更新进度
            updateProgress(80);

            // 将数据转换为CSV格式
            const csvContent = csvData.map(row => row.join('\t')).join('\n');

            // 创建Blob并获取URL
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' });
            const dataUrl = URL.createObjectURL(blob);

            // 通过消息发送到background.js处理下载
            chrome.runtime.sendMessage({
                action: "downloadCSV",
                dataUrl: dataUrl
            });

            log('正在下载文件...', 'info');

            // 关闭标签页
            chrome.tabs.remove(newTab.id, () => {
                log('已关闭爬取页面', 'info');
            });

        } catch (error) {
            log(`发生错误: ${error.message}`, 'error');

            // 如果发生错误，尝试关闭已创建的标签页
            try {
                if (newTab && newTab.id) {
                    chrome.tabs.remove(newTab.id);
                }
            } catch (e) {
                log(`关闭标签页时出错: ${e.message}`, 'error');
            }
        }
    }

    // 页面加载后自动开始爬取
    startScraping();
});