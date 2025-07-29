// This script runs in the context of the web page
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'scrapeBonds') {
        try {
            const results = [];

            // Check which page we're on and scrape accordingly
            if (window.location.href.includes('united-states/government-bond-yield')) {
                // Scraping US bonds
                const usBonds = ["US 2Y"];

                for (const bondName of usBonds) {
                    const linkElement = Array.from(document.querySelectorAll('a')).find(
                        el => el.textContent.trim() === bondName
                    );

                    if (linkElement) {
                        const row = linkElement.closest('tr');
                        const priceElement = row.querySelector('#p');

                        if (priceElement) {
                            results.push({
                                name: bondName.replace(" ", ""),
                                price: priceElement.textContent.trim()
                            });
                        }
                    }
                }
            }
            else if (window.location.href.includes('bonds')) {
                // Scraping other country bonds
                const otherBonds = {
                    "United Kingdom": "UK10Y",
                    "Japan": "JP10Y",
                    "Brazil": "BR10Y",
                    "India": "IND10Y",
                    "Turkey": "TUR10Y"
                };

                for (const [bondName, mappedName] of Object.entries(otherBonds)) {
                    const linkElement = Array.from(document.querySelectorAll('a b')).find(
                        el => el.textContent.trim() === bondName
                    );

                    if (linkElement) {
                        const row = linkElement.closest('tr');
                        const priceElement = row.querySelector('#p');

                        if (priceElement) {
                            results.push({
                                name: mappedName,
                                price: priceElement.textContent.trim()
                            });
                        }
                    }
                }
            }

            sendResponse({ success: true, data: results });
        } catch (error) {
            sendResponse({ success: false, error: error.message });
        }
        return true;
    }
});