// Global variables to store the scraped data
let scrapedData = [];
let currentSection = 0;
const totalSections = 4;

// Define the indicator mappings
const economicsSections = [
    {
        indicators: {
            "GDP Growth Rate": "USGDP",
            "Non Farm Payrolls": "USNonFarm",
            "Inflation Rate": "USCPI",
            "Interest Rate": "USInterest",
            "Balance of Trade": "USTrade",
            "Consumer Confidence": "USConfidence",
            "Retail Sales MoM": "USRetailM",
            "Unemployment Rate": "USUnemploy",
            "Non Manufacturing PMI": "USNonPMI"
        },
        nextSection: 'a[data-bs-target="#labour"]',
        nextSectionLinkText: "Manufacturing Payrolls",
        category: "Economics"
    },
    {
        indicators: {
            "Initial Jobless Claims": "USInitial",
            "ADP Employment Change": "USNonFarmA"
        },
        nextSection: 'a[data-bs-target="#prices"]',
        nextSectionLinkText: "Core Consumer Prices",
        category: "Economics"
    },
    {
        indicators: {
            "Core PCE Price Index Annual Change": "CorePCEY",
            "Core PCE Price Index MoM": "CorePCEM",
            "Core Inflation Rate": "CoreCPI",
            "Producer Prices Change": "USPPI",
            "Core Producer Prices YoY": "CorePPI",
            "PCE Price Index Annual Change": "PCEY",
            "Import Prices MoM": "ImportPriceM",
            "Import Prices YoY": "ImportPriceY"
        },
        nextSection: 'a[data-bs-target="#gdp"]',
        nextSectionLinkText: "GDP Constant Prices",
        category: "Economics"
    },
    {
        indicators: {
            "Real Consumer Spending": "USConspending"
        },
        nextSection: null,
        nextSectionLinkText: null,
        category: "Economics"  // 添加category属性
    }
];

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "startScraping") {
        startScraping();
    }
    return true;
});

// Main scraping function
async function startScraping() {
    try {
        updateProgress("Starting to scrape section 1", 25);
        scrapedData = [];
        currentSection = 0;

        // Get yesterday's date
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const dateStr = yesterday.toISOString().split('T')[0];

        // Process each section
        await processCurrentSection(dateStr);

    } catch (error) {
        console.error("Error during scraping:", error);
        chrome.runtime.sendMessage({
            action: "scrapingError",
            error: error.message
        });
    }
}

// Process the current section, then move to the next
async function processCurrentSection(dateStr) {
    try {
        // Wait for the page to be fully loaded
        await waitForElement("table");

        // Get the indicators for the current section
        const sectionData = economicsSections[currentSection];
        const indicators = sectionData.indicators;
        const category = sectionData.category; // 获取当前section的category

        // Scrape data from current section
        await fetchDataFromSection(indicators, dateStr, category); // 传入category参数

        // Update progress
        updateProgress(`Completed section ${currentSection + 1}`, 25 + (currentSection * 25));

        // Move to next section or finish
        if (currentSection < totalSections - 1) {
            currentSection++;

            // Navigate to the next section
            const nextSection = economicsSections[currentSection - 1].nextSection;
            const nextSectionLinkText = economicsSections[currentSection - 1].nextSectionLinkText;

            if (nextSection && nextSectionLinkText) {
                await navigateToSection(nextSection, nextSectionLinkText);
                updateProgress(`Scraping section ${currentSection + 1}`, 25 + (currentSection * 25));

                // Process the next section after navigation
                setTimeout(() => {
                    processCurrentSection(dateStr);
                }, 1000);
            }
        } else {
            // All sections processed, convert to CSV and download
            const csvContent = convertToCSV(scrapedData);
            downloadCSV(csvContent);
        }
    } catch (error) {
        console.error("Error processing section:", error);
        chrome.runtime.sendMessage({
            action: "scrapingError",
            error: `Error in section ${currentSection + 1}: ${error.message}`
        });
    }
}

// Fetch data from the current section
async function fetchDataFromSection(indicators, dateStr, category) {
    for (const [key, value] of Object.entries(indicators)) {
        try {
            // Try to find the element using XPath
            const elements = document.evaluate(
                `//td[normalize-space(.)="${key}"]/following-sibling::td`,
                document,
                null,
                XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                null
            );

            if (elements.snapshotLength > 0) {
                const element = elements.snapshotItem(0);
                const priceStr = element.textContent.trim();

                if (!priceStr) {
                    console.log(`Indicator ${key} has no data, skipping.`);
                    continue;
                }

                // Try to convert to float by removing commas
                try {
                    const price = parseFloat(priceStr.replace(',', ''));
                    if (!isNaN(price)) {
                        scrapedData.push([dateStr, value, price, category]);
                        console.log(`Successfully scraped ${key}: ${price} (${category})`);
                    } else {
                        console.log(`Failed to convert ${key} value '${priceStr}' to number, skipping.`);
                    }
                } catch (e) {
                    console.log(`Error converting ${key} value '${priceStr}' to float: ${e}`);
                }
            } else {
                console.log(`Indicator ${key} not found on page.`);
            }
        } catch (e) {
            console.error(`Error getting data for ${key}: ${e}`);
        }
    }
}

// Helper function to navigate to a section
async function navigateToSection(sectionSelector, linkText) {
    return new Promise((resolve, reject) => {
        try {
            const sectionLink = document.querySelector(sectionSelector);
            if (sectionLink) {
                sectionLink.click();

                // Wait for the section to load
                waitForElement(`a:contains("${linkText}")`)
                    .then(() => {
                        console.log(`Successfully switched to ${sectionSelector} and found '${linkText}' link.`);
                        resolve();
                    })
                    .catch(error => {
                        reject(`Failed to find '${linkText}' link after clicking section. Error: ${error}`);
                    });
            } else {
                reject(`Could not find section selector: ${sectionSelector}`);
            }
        } catch (error) {
            reject(`Error navigating to section: ${error}`);
        }
    });
}

// Helper function to wait for an element to appear
function waitForElement(selector, timeout = 10000) {
    return new Promise((resolve, reject) => {
        // If element already exists, resolve immediately
        if (document.querySelector(selector)) {
            return resolve(document.querySelector(selector));
        }

        const observer = new MutationObserver((mutations) => {
            if (document.querySelector(selector)) {
                observer.disconnect();
                resolve(document.querySelector(selector));
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        // Set timeout
        setTimeout(() => {
            observer.disconnect();
            reject(new Error(`Timeout waiting for element: ${selector}`));
        }, timeout);
    });
}

// Convert the data to CSV format
function convertToCSV(data) {
    const header = 'date,name,price,category\n';
    const rows = data.map(row => row.join(',')).join('\n');
    return header + rows;
}

// Download the CSV file
function downloadCSV(csvContent) {
    // Create a data URL from the CSV content
    const dataUrl = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvContent);

    // Send message to background script to download the file
    chrome.runtime.sendMessage({
        action: "scrapingComplete",
        dataUrl: dataUrl
    });
}

// Update progress in the popup
function updateProgress(status, progress) {
    chrome.runtime.sendMessage({
        action: "updateProgress",
        status: status,
        progress: progress
    });
}

// Add a jQuery-like :contains selector functionality
Element.prototype.matches = Element.prototype.matches || Element.prototype.msMatchesSelector;
Document.prototype.querySelector = (function (querySelector) {
    return function (selector) {
        if (selector.includes(':contains(')) {
            const parts = selector.match(/(.*):contains\("(.*)"\)(.*)/);
            if (parts) {
                const [_, before, text, after] = parts;
                const elements = Array.from(this.querySelectorAll(before || '*'));
                for (const el of elements) {
                    if (el.textContent.includes(text) && (!after || el.matches(after))) {
                        return el;
                    }
                }
                return null;
            }
        }
        return querySelector.call(this, selector);
    };
})(Document.prototype.querySelector);