document.addEventListener('DOMContentLoaded', function () {
  const statusDiv = document.getElementById('status');
  const progressBar = document.getElementById('progressBar');
  const logContainer = document.getElementById('logContainer'); // 获取日志容器

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

  // 重试配置
  const MAX_RETRIES = 3; // 每个页面最多重试3次

  /**
   * 向日志容器中添加一条消息
   */
  function logMessage(text, type = 'info') {
    const p = document.createElement('p');
    p.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
    p.className = `log-message log-${type}`; // 应用CSS样式
    logContainer.appendChild(p);
    logContainer.scrollTop = logContainer.scrollHeight; // 自动滚动到底部
  }

  // 自动开始抓取过程
  startScraping();

  async function startScraping() {
    try {
      // 重置状态
      allResults = [];
      progressBar.style.width = '0%';
      logContainer.innerHTML = ''; // 清空旧日志
      statusDiv.textContent = `Starting scrape... (0/${urls.length})`;
      logMessage(`初始化... 准备抓取 ${urls.length} 个页面。`);

      // 按顺序处理所有URL
      for (let i = 0; i < urls.length; i++) {
        const { url, category } = urls[i];
        const progress = i + 1;

        // 更新主状态和进度条
        statusDiv.textContent = `Processing ${progress}/${urls.length}: ${category}`;
        progressBar.style.width = `${(progress / urls.length) * 100}%`;
        logMessage(`[${progress}/${urls.length}] 正在处理: ${category}...`);

        // 使用重试机制抓取单个页面
        const pageResults = await scrapePageWithRetry(url, category, MAX_RETRIES);

        if (pageResults && pageResults.length > 0) {
          allResults = allResults.concat(pageResults);
          logMessage(`[${category}] 成功获取 ${pageResults.length} 条数据`, 'success');
        } else {
          logMessage(`[${category}] 重试 ${MAX_RETRIES} 次后仍未获取到数据`, 'warning');
        }
      }

      // 所有页面处理完毕，开始处理数据和下载
      statusDiv.textContent = "Scraping complete. Processing data...";
      logMessage("所有页面抓取完毕。", 'final');

      if (allResults.length === 0) {
        logMessage("抓取完成，但未收集到任何有效数据。请检查日志中的错误信息。", 'warning');
        statusDiv.textContent = "Finished. No data found.";
        return;
      }

      const above = allResults.filter(r => r.marketCap >= 5e9);
      const below = allResults.filter(r => r.marketCap < 5e9);

      const dateStr = getDateStr();
      const summaryMsg = `数据处理完成：${above.length} 条 (市值≥50亿)，${below.length} 条 (市值<50亿)。准备下载...`;
      logMessage(summaryMsg, 'final');
      statusDiv.textContent = "Ready to download...";

      if (above.length > 0) {
        await downloadFile(`screener_above_${dateStr}.txt`, above);
      }
      if (below.length > 0) {
        await downloadFile(`screener_below_${dateStr}.txt`, below);
      }

      statusDiv.textContent = "All tasks completed!";

    } catch (err) {
      console.error(err);
      logMessage(`发生严重错误: ${err.message}`, 'error');
      statusDiv.textContent = `Error: ${err.message}`;
    }
  }

  /**
   * 带重试机制的页面抓取函数
   */
  async function scrapePageWithRetry(url, category, maxRetries) {
    let attempt = 0;

    while (attempt < maxRetries) {
      attempt++;

      if (attempt > 1) {
        logMessage(`[${category}] 第 ${attempt} 次尝试 (共 ${maxRetries} 次)`, 'warning');
      }

      let tab = null;

      try {
        // 打开页面
        logMessage(`[${category}] 正在打开页面...`);
        tab = await chrome.tabs.create({ url, active: false });

        // 等待页面加载
        await waitForPageLoad(tab.id);
        logMessage(`[${category}] 页面加载完成，开始提取数据...`);

        // 发送消息到 content.js 抓取数据
        const response = await new Promise((resolve, reject) => {
          chrome.tabs.sendMessage(tab.id, { action: "scrapeData", category }, res => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else if (res) {
              resolve(res);
            } else {
              reject(new Error("Content script did not send a response."));
            }
          });
          // 设置60秒超时
          setTimeout(() => reject(new Error("抓取超时 (60秒)")), 60000);
        });

        // 检查响应结果
        if (response.success && response.data && response.data.length > 0) {
          // 成功获取到数据
          logMessage(`[${category}] ${response.message}`, 'success');
          return response.data;
        } else {
          // 没有获取到有效数据
          const errorMsg = response.message || "未获取到有效数据";
          logMessage(`[${category}] ${errorMsg}`, 'warning');

          if (attempt < maxRetries) {
            logMessage(`[${category}] 将在2秒后重试...`, 'warning');
            await sleep(2000); // 等待2秒后重试
          }
        }

      } catch (err) {
        logMessage(`[${category}] 尝试 ${attempt} 失败: ${err.message}`, 'error');

        if (attempt < maxRetries) {
          logMessage(`[${category}] 将在2秒后重试...`, 'warning');
          await sleep(2000);
        }

      } finally {
        // 确保标签页被关闭
        if (tab && tab.id) {
          await chrome.tabs.remove(tab.id).catch(e => console.warn("Could not remove tab:", e));
        }
      }
    }

    // 所有重试都失败
    logMessage(`[${category}] 达到最大重试次数 (${maxRetries})，放弃该页面`, 'error');
    return [];
  }

  /**
   * 睡眠函数
   */
  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function getDateStr() {
    const now = new Date();
    const yy = String(now.getFullYear() % 100).padStart(2, "0");
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    return `${yy}${mm}${dd}`;
  }

  function downloadFile(filename, data) {
    return new Promise((resolve) => {
      logMessage(`请求下载文件: ${filename} (${data.length}条记录)`);
      chrome.runtime.sendMessage(
        { action: "downloadData", data, filename },
        response => {
          if (response && response.success) {
            logMessage(`下载成功: ${response.filename}`, 'success');
          } else {
            logMessage(`下载失败: ${response?.error || "未知错误"}`, 'error');
          }
          resolve(); // 无论成功失败都继续
        }
      );
    });
  }

  // waitForPageLoad 保持原样
  async function waitForPageLoad(tabId) {
    return new Promise((resolve, reject) => {
      let checks = 0, maxChecks = 30; // 最多检查60次 (60秒)
      function check() {
        // 检查标签页是否还存在
        chrome.tabs.get(tabId, (tab) => {
          if (chrome.runtime.lastError || !tab) {
            return reject(new Error("Tab was closed before loading completed."));
          }

          // 注入脚本检查页面状态和表格行数
          chrome.scripting.executeScript({
            target: { tabId },
            func: () => {
              const tableRows = document.querySelectorAll('div[data-testid="screener-table"] tbody tr');
              return { readyState: document.readyState, rowCount: tableRows.length };
            }
          }, (results) => {
            if (chrome.runtime.lastError) {
              // 忽略注入错误，可能页面正在跳转
            } else if (results && results[0] && results[0].result) {
              const { readyState, rowCount } = results[0].result;
              // 当页面加载完成并且表格中出现了至少一行数据时，认为加载成功
              if (readyState === 'complete' && rowCount > 0) {
                // 等待一小段时间，确保动态内容渲染完毕
                setTimeout(resolve, 1500);
                return;
              }
            }

            if (++checks >= maxChecks) {
              reject(new Error("页面加载或数据出现超时 (60秒)"));
            } else {
              setTimeout(check, 1000);
            }
          });
        });
      }
      check();
    });
  }
});