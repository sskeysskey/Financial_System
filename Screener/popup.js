document.addEventListener('DOMContentLoaded', function () {
  const startButton = document.getElementById('startScraping');
  const statusDiv = document.getElementById('status');
  const urlsInput = document.getElementById('urlsInput');
  const progressBar = document.getElementById('progressBar');
  const progressContainer = document.querySelector('.progress');

  let allResults = [];

  startButton.addEventListener('click', async function () {
    // Parse input URLs and categories
    try {
      let urls = [];
      const input = urlsInput.value;

      // Try to parse the input with regex
      const regex = /\('([^']+)',\s*'([^']+)'\)/g;
      let match;

      while ((match = regex.exec(input)) !== null) {
        urls.push({
          url: match[1],
          category: match[2]
        });
      }

      if (urls.length === 0) {
        throw new Error("Failed to parse URLs and categories. Please check the format.");
      }

      // Reset status
      allResults = [];
      progressContainer.style.display = 'block';
      progressBar.style.width = '0%';
      startButton.disabled = true;
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
          await new Promise(resolve => setTimeout(resolve, 5000)); // Wait for page to load

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

      startButton.disabled = false;

    } catch (err) {
      console.error("Processing error:", err);
      statusDiv.textContent = "Error: " + err.message;
      startButton.disabled = false;
    }
  });
});