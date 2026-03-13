chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'saveData') {
        const site = request.site || 'polymarket';

        processAndSaveData(request.data, site)
            .then((processedData) => {
                const filename = site === 'kalshi' ? 'kalshi.json' : 'polymarket.json';
                chrome.runtime.sendMessage({
                    type: 'downloadJson',
                    data: processedData,
                    filename: filename
                });
                sendResponse({ success: true });
            })
            .catch(error => sendResponse({ success: false, error: error.message }));

        return true; // 保持消息通道开启
    }
});

// 根据网站分发处理
async function processAndSaveData(predictions, site) {
    if (site === 'kalshi') {
        return processKalshiData(predictions);
    } else {
        return processPolymarketData(predictions);
    }
}

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

// ============ Kalshi 数据处理 ============
async function processKalshiData(predictions) {
    const enrichedData = await Promise.all(
        predictions.map(async (pred) => {
            const subpageData = await fetchKalshiSubpageData(pred.subUrl);

            const result = {
                name: pred.name,
                // 子页面数据优先，主页面卡片数据作为备选
                type: subpageData.type || pred.fallbackType || '',
                subtype: subpageData.subtype || pred.fallbackSubtype || '',
                volume: pred.volume,
                hide: "1"
            };

            // 子页面 options 优先；如果子页面抓不到，则用主页面卡片上可见的 options
            const options = (subpageData.options && subpageData.options.length > 0)
                ? subpageData.options
                : pred.options;

            options.forEach((opt, index) => {
                result[`option${index + 1}`] = opt.name;
                result[`value${index + 1}`] = opt.value;
            });

            return result;
        })
    );
    return enrichedData;
}

async function fetchKalshiSubpageData(subUrl) {
    try {
        const response = await fetch(`https://kalshi.com${subUrl}`);
        const html = await response.text();

        // 提取 type / subtype（面包屑中的 category 链接）
        // 格式: <a ... href="/category/politics"><span ...>Politics</span></a>
        //        <a ... href="/category/politics/us-elections"><span ...>US Elections</span></a>
        const categoryPattern = /href="\/category\/[^"]*"[^>]*>\s*<span[^>]*>([^<]+)<\/span>/g;
        const categoryMatches = [...html.matchAll(categoryPattern)];
        const type = categoryMatches.length > 0 ? categoryMatches[0][1].trim() : '';
        const subtype = categoryMatches.length > 1 ? categoryMatches[1][1].trim() : '';

        // 提取 option 名称
        // 格式: <span class="...typ-body-x30..."><div ...>Gavin Newsom</div></span>
        const optionPattern = /class="[^"]*typ-body-x30[^"]*"[^>]*>\s*<div[^>]*>([^<]+)<\/div>/g;
        const optionMatches = [...html.matchAll(optionPattern)];

        // 提取 option 值
        // 格式: <h2 class="...typ-headline-x10...">27%</h2>
        const valuePattern = /<h2[^>]*class="[^"]*typ-headline-x10[^"]*"[^>]*>\s*([\d]+%)\s*<\/h2>/g;
        const valueMatches = [...html.matchAll(valuePattern)];

        const options = [];
        for (let i = 0; i < optionMatches.length; i++) {
            options.push({
                name: optionMatches[i][1].trim(),
                value: valueMatches[i] ? valueMatches[i][1].trim() : ''
            });
        }

        return { type, subtype, options };
    } catch (error) {
        console.error('Error fetching Kalshi subpage:', error);
        return { type: '', subtype: '', options: [] };
    }
}