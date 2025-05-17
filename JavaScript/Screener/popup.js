document.addEventListener('DOMContentLoaded', function () {
  const statusDiv = document.getElementById('status');
  const progressBar = document.getElementById('progressBar');

  let allResults = [];

  // 预定义URL和分类
  const urls = [
    { url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=0&count=100', category: 'Technology' },
    { url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=100&count=100', category: 'Technology' },
    { url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=200&count=100', category: 'Technology' },
    { url: 'https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=0&count=100', category: 'Industrials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=100&count=100', category: 'Industrials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=200&count=100', category: 'Industrials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=0&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=100&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=200&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=300&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/e5221069-608f-419e-a3ff-24e61e4a07ac/?start=0&count=100', category: 'Basic_Materials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/90966b0c-2902-425c-870a-f19eb1ffd0b8/?start=0&count=100', category: 'Consumer_Defensive' },
    { url: 'https://finance.yahoo.com/research-hub/screener/84e650e0-3916-4907-ad56-2fba4209fa3f/?start=0&count=100', category: 'Utilities' },
    { url: 'https://finance.yahoo.com/research-hub/screener/1788e450-82cf-449a-b284-b174e8e3f6d6/?start=0&count=100', category: 'Energy' },
    { url: 'https://finance.yahoo.com/research-hub/screener/1788e450-82cf-449a-b284-b174e8e3f6d6/?start=100&count=100', category: 'Energy' },
    { url: 'https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=0&count=100', category: 'Consumer_Cyclical' },
    { url: 'https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=100&count=100', category: 'Consumer_Cyclical' },
    { url: 'https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=200&count=100', category: 'Consumer_Cyclical' },
    { url: 'https://finance.yahoo.com/research-hub/screener/9a217ba3-966a-4340-83b9-edb160f05f8e/?start=0&count=100', category: 'Real_Estate' },
    { url: 'https://finance.yahoo.com/research-hub/screener/9a217ba3-966a-4340-83b9-edb160f05f8e/?start=100&count=100', category: 'Real_Estate' },
    { url: 'https://finance.yahoo.com/research-hub/screener/f99d96f0-a144-48be-b220-0be74c55ebf4/?start=0&count=100', category: 'Healthcare' },
    { url: 'https://finance.yahoo.com/research-hub/screener/f99d96f0-a144-48be-b220-0be74c55ebf4/?start=100&count=100', category: 'Healthcare' },
    { url: 'https://finance.yahoo.com/research-hub/screener/360b16ee-2692-4617-bd1a-a6c715dd0c29/?start=0&count=100', category: 'Communication_Services' }
  ];

  // 自动开始抓取过程
  startScraping();

  async function startScraping() {
    try {
      // Reset status
      allResults = [];
      progressBar.style.width = '0%';
      statusDiv.textContent = `Starting scrape (0/${urls.length})`;

      // Process URLs one by one
      for (let i = 0; i < urls.length; i++) {
        const { url, category } = urls[i];
        statusDiv.textContent = `Scraping ${i + 1}/${urls.length}: ${category}`;
        progressBar.style.width = `${((i + 1) / urls.length) * 100}%`;

        // Create a new tab
        const tab = await chrome.tabs.create({ url, active: false });

        try {
          // 等待页面加载完成 - 使用更可靠的方法
          await waitForPageLoad(tab.id);

          statusDiv.textContent = `Page ${i + 1}/${urls.length} loaded, extracting data...`;

          let results = [];
          try {
            // 发送消息到content脚本开始抓取数据
            results = await new Promise((resolve, reject) => {
              chrome.tabs.sendMessage(tab.id, { action: "scrapeData", category }, response => {
                if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
                else resolve(response || []);
              });

              // 设置超时，防止永久等待
              setTimeout(() => reject(new Error("Scraping timeout")), 60000);
            });
          } catch (err) {
            console.error("Error getting data:", err);
            statusDiv.textContent = `Error on ${i + 1}: ${err.message}`;
            results = [];
          }

          allResults = allResults.concat(results);
          statusDiv.textContent = `Scraped ${i + 1}/${urls.length}: got ${results.length} records`;
        } finally {
          await chrome.tabs.remove(tab.id).catch(() => { });
        }
      }

      // 划分 above/below 并下载
      if (allResults.length === 0) {
        statusDiv.textContent = "Scraping complete, but no data found";
        return;
      }

      const above = allResults.filter(r => r.marketCap >= 5e9);
      const below = allResults.filter(r => r.marketCap < 5e9);

      const dateStr = getDateStr();
      statusDiv.textContent = `准备下载：${above.length} 条 ≥50亿，${below.length} 条 <50亿`;

      if (above.length > 0) {
        downloadFile(`screener_above_${dateStr}.txt`, above, msg => {
          statusDiv.textContent = msg;
        });
      }
      if (below.length > 0) {
        downloadFile(`screener_below_${dateStr}.txt`, below, msg => {
          statusDiv.textContent = msg;
        });
      }

    } catch (err) {
      console.error(err);
      statusDiv.textContent = `Error: ${err.message}`;
    }
  }

  function getDateStr() {
    const now = new Date();
    const yy = String(now.getFullYear() % 100).padStart(2, "0");
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    return `${yy}${mm}${dd}`;
  }

  function downloadFile(filename, data, callback) {
    chrome.runtime.sendMessage(
      { action: "downloadData", data, filename },
      response => {
        if (response && response.success) {
          callback(`Downloaded: ${response.filename}`);
        } else {
          callback(`Download failed: ${response?.error || "unknown"}`);
        }
      }
    );
  }

  // waitForPageLoad 保持原样
  async function waitForPageLoad(tabId) {
    return new Promise((resolve, reject) => {
      let checks = 0, max = 60;
      function check() {
        chrome.scripting.executeScript({
          target: { tabId },
          function: () => {
            const trs = document.querySelectorAll('table tbody tr');
            return { ready: document.readyState, count: trs.length };
          }
        }, res => {
          if (res && res[0]?.result.ready === 'complete' && res[0].result.count > 0) {
            setTimeout(resolve, 2000);
          } else if (++checks >= max) {
            reject(new Error("Page load timeout"));
          } else {
            setTimeout(check, 1000);
          }
        });
      }
      check();
    });
  }
});