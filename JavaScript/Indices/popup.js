document.addEventListener('DOMContentLoaded', function () {
    // Start the scraping process immediately when popup is opened
    chrome.runtime.sendMessage({ action: "startScraping" });

    // Listen for status updates from background script
    chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
        if (message.type === "status") {
            updateStatus(message.step, message.status, message.message);
        }
    });
});

function updateStatus(step, status, message) {
    const statusContainer = document.getElementById('status-container');

    // Create or update status item
    let statusItem = document.getElementById(`${step}-status`);
    if (!statusItem) {
        statusItem = document.createElement('div');
        statusItem.id = `${step}-status`;
        statusItem.className = 'status-item';
        statusContainer.appendChild(statusItem);
    }

    // Update status class and message
    statusItem.className = `status-item ${status}`;
    statusItem.textContent = message;

    // Scroll to the bottom to show the latest status
    statusContainer.scrollTop = statusContainer.scrollHeight;
}