// content.js
// 备注

// --- 主要逻辑封装在一个函数中，以便在注入时执行 ---
function mainScrapeAndDownload() {
    // 向popup发送状态更新的辅助函数
    function updateStatus(message, type = 'info', keepOpen = false) {
        // 先打印到控制台
        console.log(`[updateStatus] type=${type}  message="${message}"`);
        // 再继续原有逻辑
        chrome.runtime.sendMessage({
            action: "updateStatus",
            message: message,
            type: type, // 'success', 'error', 'info'
            keepOpen: keepOpen
        });
    }

    updateStatus('开始在页面上查找数据...', 'info');

    // 1. 数据抓取和格式化
    const scrapedData = [];
    // 定位到包含历史数据的表格的<tbody>元素
    // 根据您提供的HTML，表格有 class "table yf-1jecxey noDl hideOnPrint"
    // 行有 class "yf-1jecxey"
    // 单元格有 class "yf-1jecxey"
    const table = document.querySelector('table.table.yf-1jecxey');

    if (!table) {
        updateStatus('错误：未在页面上找到目标表格。', 'error', true);
        console.error('Error: Target table not found.');
        return;
    }

    const tableBody = table.querySelector('tbody');
    if (!tableBody) {
        updateStatus('错误：表格中未找到 tbody 元素。', 'error', true);
        console.error('Error: tbody element not found in the table.');
        return;
    }

    const rows = tableBody.querySelectorAll('tr.yf-1jecxey');
    if (rows.length === 0) {
        updateStatus('未在表格中找到任何数据行。', 'info', true);
        console.log('No data rows found in the table.');
        return;
    }

    updateStatus(`找到 ${rows.length} 行数据，正在处理...`, 'info');

    rows.forEach((row, index) => {
        const cells = row.querySelectorAll('td.yf-1jecxey');
        // 确保有足够的单元格来提取数据
        // 根据您的示例，日期是第1个td，价格是第5个td，成交量是第7个td
        if (cells.length >= 7) {
            try {
                // 提取日期 (第一个td)
                let rawDate = cells[0].textContent.trim();
                // 移除可能存在的 "::after" 和引号
                rawDate = rawDate.split('::')[0].trim().replace(/"/g, '');
                const dateObj = new Date(rawDate);
                const year = dateObj.getFullYear();
                const month = String(dateObj.getMonth() + 1).padStart(2, '0'); // 月份从0开始，所以+1
                const day = String(dateObj.getDate()).padStart(2, '0');
                const formattedDate = `${year}-${month}-${day}`;

                // 提取价格 (第五个td, cells[4])
                const rawPrice = cells[4].textContent.trim();
                const price = parseFloat(rawPrice.replace(/,/g, '')); // 移除逗号并转为数字

                // 提取成交量 (第七个td, cells[6])
                const rawVolume = cells[6].textContent.trim();
                const volume = parseInt(rawVolume.replace(/,/g, ''), 10); // 移除逗号并转为整数

                if (formattedDate !== "NaN-NaN-NaN" && !isNaN(price) && !isNaN(volume)) {
                    scrapedData.push({
                        date: formattedDate,
                        price: price,
                        volume: volume
                    });
                } else {
                    console.warn(`Skipping row ${index + 1} due to invalid data:`, { rawDate, rawPrice, rawVolume });
                    updateStatus(`警告：第 ${index + 1} 行数据解析失败，已跳过。`, 'info');
                }
            } catch (e) {
                console.error(`Error processing row ${index + 1}:`, e, row.innerHTML);
                updateStatus(`错误：处理第 ${index + 1} 行时出错，已跳过。`, 'error');
            }
        } else {
            console.warn(`Skipping row ${index + 1} due to insufficient cells:`, cells.length);
            updateStatus(`警告：第 ${index + 1} 行单元格数量不足，已跳过。`, 'info');
        }
    });

    if (scrapedData.length === 0) {
        updateStatus('未能抓取到任何有效数据。', 'error', true);
        return;
    }

    updateStatus(`成功抓取 ${scrapedData.length} 条有效数据。正在生成CSV...`, 'info');

    // **打印原始数据结构：**
    console.log('【ScrapedData】', scrapedData);

    // **打印最终生成的 CSV 文本：**
    let csvContent = "date,price,volume\n"; // CSV header
    scrapedData.forEach(item => {
        csvContent += `${item.date},${item.price},${item.volume}\n`;
    });
    console.log('【CSVContent】\n' + csvContent);

    // 3. 自动下载到本地 (使用您提供的函数)
    // saveCSV(csvContent);
}

// --- 确保脚本只在被注入时执行一次，或者根据消息执行 ---
// 简单起见，这里假设每次注入都应该执行抓取。
// 如果需要更复杂的控制（例如，通过消息从popup.js触发），则需要添加消息监听器。
if (typeof window.hasRunScraper === 'undefined') {
    mainScrapeAndDownload();
    window.hasRunScraper = true; // 标记已运行，防止重复执行（如果脚本被意外多次注入）
} else {
    // 如果脚本已存在，并且您希望通过消息重新触发，可以这样做：
    // chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    //   if (request.action === "scrape") {
    //     mainScrapeAndDownload();
    //     sendResponse({status: "Scraping initiated"});
    //   }
    //   return true; // Keep message channel open for async response
    // });
    // 对于当前设计，popup.js每次点击都会重新注入content.js，所以上面的标记是基础的防止意外重入。
    // 如果希望点击按钮时，若content.js已注入则发消息，否则注入，会更复杂。
    // 当前：每次点击按钮都重新注入并执行。
    mainScrapeAndDownload(); // 允许再次运行
}