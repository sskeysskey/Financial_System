document.addEventListener('DOMContentLoaded', function () {
    const statusDiv = document.getElementById('status');
    const startButton = document.getElementById('startScrapeButton');

    function addLogMessage(message, type = 'info') {
        const logItem = document.createElement('div');
        logItem.className = `log-item ${type}`;
        logItem.textContent = message;
        statusDiv.appendChild(logItem);
        statusDiv.scrollTop = statusDiv.scrollHeight; // Auto-scroll to the latest message
    }

    startButton.addEventListener('click', function () {
        addLogMessage('Scraping process initiated by user.', 'info');
        startButton.disabled = true; // Disable button after clicking
        startButton.textContent = 'Scraping...';

        chrome.runtime.sendMessage({ action: 'startYahooScraping' }, function (response) {
            if (chrome.runtime.lastError) {
                addLogMessage(`Error starting scraping: ${chrome.runtime.lastError.message}`, 'error');
                startButton.disabled = false;
                startButton.textContent = 'Start Scraping ETFs';
            } else if (response && response.status === 'started') {
                addLogMessage('Background process for Yahoo ETFs initiated.', 'info');
            } else {
                addLogMessage('Failed to start background process or no response.', 'error');
                startButton.disabled = false;
                startButton.textContent = 'Start Scraping ETFs';
            }
        });
    });

    // Listen for status updates and CSV download requests
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.type === 'statusUpdate') { // Changed from 'status' to avoid conflict
            addLogMessage(message.text, message.logType || 'info');
            if (message.completed) {
                startButton.disabled = false;
                startButton.textContent = 'Start Scraping ETFs';
            }
        } else if (message.type === 'csvData') {
            // This part handles the download triggered by background.js
            const blob = new Blob([message.data], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);

            // Create a temporary link to trigger download
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = message.filename;
            document.body.appendChild(a);
            a.click();

            // Clean up
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                addLogMessage(`Download initiated for "${message.filename}". Check your downloads folder.`, 'success');
            }, 100);
        }
        // It's important to return true if you intend to send a response asynchronously
        // However, in this specific listener, we are mostly receiving, so it might not be strictly necessary
        // unless a specific message type expects a direct response from the popup.
        // For safety and good practice, especially if any message type might need it:
        sendResponse({ received: true });
        return true;
    });
});