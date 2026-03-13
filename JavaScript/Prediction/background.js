// /Users/yanzhang/Coding/Financial_System/JavaScript/Prediction/background.js

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'saveData') {
        // 处理数据
        processAndSaveData(request.data)
            .then((processedData) => {
                // 将处理后的数据发送回 popup 进行下载
                chrome.runtime.sendMessage({
                    type: 'downloadJson',
                    data: processedData
                });
                sendResponse({ success: true });
            })
            .catch(error => sendResponse({ success: false, error: error.message }));
        return true; // 保持消息通道开启
    }
});

async function processAndSaveData(predictions) {
    // 保持你原有的逻辑，只需返回 enrichedData 而不是下载
    const enrichedData = await Promise.all(
        predictions.map(async (pred) => {
            const subpageData = await fetchSubpageData(pred.slug);

            if (pred.type === 'multi-option') {
                // 类型1: 转换为所需格式
                const result = {
                    name: pred.name,
                    type: subpageData.type,
                    subtype: subpageData.subtype,
                    volume: pred.volume,
                    enddate: subpageData.enddate,
                    hide: "1" // <--- 在这里添加
                };

                pred.options.forEach((opt, index) => {
                    result[`option${index + 1}`] = opt.name;
                    result[`value${index + 1}`] = opt.value;
                });

                return result;
            } else {
                // 类型2
                return {
                    name: pred.name,
                    value: pred.value,
                    volume: pred.volume,
                    enddate: subpageData.enddate,
                    hide: "1" // <--- 在这里添加
                };
            }
        })
    );
    return enrichedData;
}

async function fetchSubpageData(slug) {
    try {
        const response = await fetch(`https://polymarket.com/event/${slug}`);
        const html = await response.text();

        // 使用正则表达式提取数据
        const typeMatch = html.match(/href="\/dashboards\/[^"]*">([^<]+)<\/a>/);
        const subtypeMatch = html.match(/href="\/predictions\/[^"]*">([^<]+)<\/a>/);
        const dateMatch = html.match(/<span[^>]*>(\w+ \d+, \d{4})<\/span>/);

        return {
            type: typeMatch ? typeMatch[1].trim() : '',
            subtype: subtypeMatch ? subtypeMatch[1].trim() : '',
            enddate: dateMatch ? dateMatch[1].trim() : ''
        };
    } catch (error) {
        console.error('Error fetching subpage:', error);
        return { type: '', subtype: '', enddate: '' };
    }
}