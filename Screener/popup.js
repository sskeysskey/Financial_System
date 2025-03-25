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

        // Wait for page to load and scrape data
        try {
          // Wait for page to load then inject and execute content script
          await new Promise(resolve => setTimeout(resolve, 8000)); // Wait for page to load

          let results = [];
          try {
            results = await new Promise((resolve) => {
              chrome.tabs.sendMessage(tab.id, {
                action: "scrapeData",
                category
              }, (response) => {
                resolve(response || []);
              });

              // 设置超时，防止无响应
              setTimeout(() => resolve([]), 30000);
            });
          } catch (err) {
            console.error("Error getting response:", err);
            results = [];
          }

          if (results && results.length > 0) {
            allResults = [...allResults, ...results];
            statusDiv.textContent = `Scraped ${i + 1}/${urls.length}: Got ${results.length} records`;
          } else {
            statusDiv.textContent = `Scrape ${i + 1}/${urls.length} failed or no data`;
          }
        } catch (err) {
          console.error("Error scraping data:", err);
          statusDiv.textContent = `Error scraping ${i + 1}/${urls.length}: ${err.message}`;
        } finally {
          // Close the tab
          await chrome.tabs.remove(tab.id);
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
});