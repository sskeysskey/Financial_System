document.addEventListener('DOMContentLoaded', function () {
  const statusDiv = document.getElementById('status');
  const progressBar = document.getElementById('progressBar');

  let allResults = [];

  // 预定义URL和分类
  const urls = [
    {
      url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=0&count=100',
      category: 'Technology'
    },
    {
      url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=100&count=100',
      category: 'Technology'
    },
    {
      url: 'https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=200&count=100',
      category: 'Technology'
    },
    {
      url: 'https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=0&count=100',
      category: 'Industrials'
    },
    {
      url: 'https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=100&count=100',
      category: 'Industrials'
    },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=0&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=100&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=200&count=100', category: 'Financial_Services' },
    { url: 'https://finance.yahoo.com/research-hub/screener/e5221069-608f-419e-a3ff-24e61e4a07ac/?start=0&count=100', category: 'Basic_Materials' },
    { url: 'https://finance.yahoo.com/research-hub/screener/90966b0c-2902-425c-870a-f19eb1ffd0b8/?start=0&count=100', category: 'Consumer_Defensive' },
    { url: 'https://finance.yahoo.com/research-hub/screener/84e650e0-3916-4907-ad56-2fba4209fa3f/?start=0&count=100', category: 'Utilities' },
    { url: 'https://finance.yahoo.com/research-hub/screener/1788e450-82cf-449a-b284-b174e8e3f6d6/?start=0&count=100', category: 'Energy' },
    { url: 'https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=0&count=100', category: 'Consumer_Cyclical' },
    { url: 'https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=100&count=100', category: 'Consumer_Cyclical' },
    { url: 'https://finance.yahoo.com/research-hub/screener/9a217ba3-966a-4340-83b9-edb160f05f8e/?start=0&count=100', category: 'Real_Estate' },
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
              chrome.tabs.sendMessage(tab.id, {
                action: "scrapeData",
                category
              }, (response) => {
                if (chrome.runtime.lastError) {
                  reject(new Error(chrome.runtime.lastError.message));
                } else {
                  resolve(response || []);
                }
              });

              // 设置超时，防止永久等待
              setTimeout(() => reject(new Error("Scraping timeout")), 60000);
            });
          } catch (err) {
            console.error("Error getting data:", err);
            statusDiv.textContent = `Error extracting data from page ${i + 1}: ${err.message}`;
            results = [];
          }

          if (results && results.length > 0) {
            allResults = [...allResults, ...results];
            statusDiv.textContent = `Scraped ${i + 1}/${urls.length}: Got ${results.length} records`;
          } else {
            statusDiv.textContent = `Scrape ${i + 1}/${urls.length} complete, but no matching data found`;
          }
        } catch (err) {
          console.error(`Error processing ${url}:`, err);
          statusDiv.textContent = `Error on page ${i + 1}/${urls.length}: ${err.message}`;
        } finally {
          // Close the tab
          try {
            await chrome.tabs.remove(tab.id);
          } catch (err) {
            console.error("Error closing tab:", err);
          }
        }
      }

      // After all URLs are processed, download the data
      if (allResults.length > 0) {
        statusDiv.textContent = `Scraping complete, got ${allResults.length} records, preparing download...`;

        // Send data to background.js to handle download
        chrome.runtime.sendMessage({
          action: "downloadData",
          data: allResults
        }, function (response) {
          if (response && response.success) {
            statusDiv.textContent = `Data saved to: ${response.filename}`;
          } else {
            statusDiv.textContent = "Download failed: " + (response ? response.error : "Unknown error");
          }
        });
      } else {
        statusDiv.textContent = "Scraping complete, but no data matching criteria found";
      }

    } catch (err) {
      console.error("Processing error:", err);
      statusDiv.textContent = "Error: " + err.message;
    }
  }

  // 等待页面加载完成的函数
  async function waitForPageLoad(tabId) {
    return new Promise((resolve, reject) => {
      let checkCount = 0;
      const maxChecks = 60; // 最多检查60次（相当于60秒）

      // 检查页面是否加载完成的函数
      function checkPageLoad() {
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          function: () => {
            // 检查页面是否有表格数据
            const tableRows = document.querySelectorAll('table tbody tr');
            // 检查加载状态和表格存在性
            return {
              readyState: document.readyState,
              hasTable: tableRows && tableRows.length > 0,
              rowCount: tableRows ? tableRows.length : 0
            };
          }
        }, (results) => {
          if (chrome.runtime.lastError) {
            // 如果页面还没准备好，继续等待
            checkCount++;
            if (checkCount >= maxChecks) {
              reject(new Error("Page load timeout after 60 seconds"));
            } else {
              setTimeout(checkPageLoad, 1000); // 1秒后再次检查
            }
            return;
          }

          if (!results || results.length === 0) {
            checkCount++;
            if (checkCount >= maxChecks) {
              reject(new Error("Script execution failed"));
            } else {
              setTimeout(checkPageLoad, 1000);
            }
            return;
          }

          const pageStatus = results[0].result;

          // 如果文档已完成加载，并且找到了表格数据，则认为页面已准备好
          if (pageStatus.readyState === 'complete' && pageStatus.hasTable && pageStatus.rowCount > 0) {
            // 表格已加载，再等待2秒确保所有数据都渲染完成
            setTimeout(resolve, 2000);
          } else if (pageStatus.readyState === 'complete' && checkCount >= 15) {
            // 如果页面加载完成但15秒后仍未找到表格，可能是页面结构问题
            if (pageStatus.hasTable) {
              // 找到表格但行数为0，可能需要更多等待时间
              setTimeout(checkPageLoad, 1000);
            } else {
              reject(new Error("Table not found in the page after 15 seconds"));
            }
          } else {
            // 继续等待页面加载
            checkCount++;
            if (checkCount >= maxChecks) {
              reject(new Error("Page load timeout"));
            } else {
              setTimeout(checkPageLoad, 1000);
            }
          }
        });
      }

      // 开始检查页面加载状态
      checkPageLoad();
    });
  }
});