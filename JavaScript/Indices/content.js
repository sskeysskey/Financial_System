// This script runs in the context of the webpage
(function () {
    console.log("Content script running on Trading Economics page");

    // Start scraping after the page is fully loaded
    window.addEventListener('load', function () {
        setTimeout(scrapeData, 2000); // Wait a bit for any dynamic content to load
    });

    function scrapeData() {
        console.log("Starting to scrape data");

        try {
            const nameMapping = {
                "MOEX": "Russia"
            };

            const allData = [];

            // Get yesterday's date for the data
            const now = new Date();
            const yesterday = new Date(now);
            yesterday.setDate(now.getDate() - 1);
            const todayStr = formatDate(yesterday);

            // Find and process data
            for (const [indice, mappedName] of Object.entries(nameMapping)) {
                try {
                    // Find the link with the index name
                    const links = document.querySelectorAll('a');
                    let targetRow = null;

                    for (const link of links) {
                        if (link.textContent.trim() === indice) {
                            // Found the link, now find the containing row
                            targetRow = link.closest('tr');
                            break;
                        }
                    }

                    if (targetRow) {
                        // Find the price element in the row
                        const priceElement = targetRow.querySelector('[id="p"]');

                        if (priceElement) {
                            const price = priceElement.textContent.trim();

                            // Add data to our collection
                            allData.push({
                                date: todayStr,
                                name: mappedName,
                                price: price,
                                category: "Indices"
                            });

                            console.log(`Scraped data for ${mappedName}: ${price}`);
                        } else {
                            console.error(`Price element not found for ${indice}`);
                        }
                    } else {
                        console.error(`Row not found for ${indice}`);
                    }
                } catch (e) {
                    console.error(`Error scraping data for ${indice}: ${e.message}`);
                }
            }

            // Send the scraped data back to the background script
            chrome.runtime.sendMessage({
                action: "dataScraped",
                data: allData
            });
        } catch (error) {
            console.error("Error in scraping:", error);
            chrome.runtime.sendMessage({
                action: "dataScraped",
                data: [],
                error: error.message
            });
        }
    }

    function formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }
})();