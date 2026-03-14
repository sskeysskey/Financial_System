chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'saveData') {
        const site = request.site || 'polymarket';

        if (site === 'polymarket') {
            processPolymarketData(request.data)
                .then((processedData) => {
                    chrome.runtime.sendMessage({
                        type: 'downloadJson',
                        data: processedData,
                        filename: 'polymarket.json'
                    });
                    sendResponse({ success: true });
                })
                .catch(error => sendResponse({ success: false, error: error.message }));
            return true;
        }
    }
});

// ============ Polymarket 数据处理（保持原逻辑） ============
async function processPolymarketData(predictions) {
    const enrichedData = await Promise.all(
        predictions.map(async (pred) => {
            const subpageData = await fetchPolymarketSubpageData(pred.slug);

            if (pred.type === 'multi-option') {
                const result = {
                    name: pred.name,
                    type: subpageData.type,
                    subtype: subpageData.subtype,
                    volume: pred.volume,
                    enddate: subpageData.enddate,
                    hide: "1"
                };

                pred.options.forEach((opt, index) => {
                    result[`option${index + 1}`] = opt.name;
                    result[`value${index + 1}`] = opt.value;
                });

                return result;
            } else {
                return {
                    name: pred.name,
                    value: pred.value,
                    volume: pred.volume,
                    enddate: subpageData.enddate,
                    hide: "1"
                };
            }
        })
    );
    return enrichedData;
}

async function fetchPolymarketSubpageData(slug) {
    try {
        const response = await fetch(`https://polymarket.com/event/${slug}`);
        const html = await response.text();

        const typeMatch = html.match(/href="\/dashboards\/[^"]*">([^<]+)<\/a>/);
        const subtypeMatch = html.match(/href="\/predictions\/[^"]*">([^<]+)<\/a>/);
        const dateMatch = html.match(/<span[^>]*>(\w+ \d+, \d{4})<\/span>/);

        return {
            type: typeMatch ? typeMatch[1].trim() : '',
            subtype: subtypeMatch ? subtypeMatch[1].trim() : '',
            enddate: dateMatch ? dateMatch[1].trim() : ''
        };
    } catch (error) {
        console.error('Error fetching Polymarket subpage:', error);
        return { type: '', subtype: '', enddate: '' };
    }
}