// ============ Volume 解析工具 ============
function parseVolumeStr(v) {
    if (!v) return 0;
    var s = v.trim().toLowerCase()
        .replace(/\$/g, '')
        .replace(/vol\.?/gi, '')
        .replace(/,/g, '')
        .trim();
    var multiplier = 1;
    if (/[\d.]\s*b/.test(s)) { multiplier = 1e9; s = s.replace(/\s*b.*$/, '').trim(); }
    else if (/[\d.]\s*m/.test(s)) { multiplier = 1e6; s = s.replace(/\s*m.*$/, '').trim(); }
    else if (/[\d.]\s*k/.test(s)) { multiplier = 1e3; s = s.replace(/\s*k.*$/, '').trim(); }
    var num = parseFloat(s);
    return isNaN(num) ? 0 : Math.round(num * multiplier);
}

// 在文件顶部 parseVolumeStr 函数附近加上：
function getTimestampedFilename(base) {
    var d = new Date();
    var yy = String(d.getFullYear()).slice(-2);
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    var dd = String(d.getDate()).padStart(2, '0');
    return base + '_' + yy + mm + dd + '.json';
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'saveData') {
        const site = request.site || 'polymarket';

        if (site === 'polymarket') {
            processPolymarketData(request.data)
                .then((processedData) => {
                    chrome.runtime.sendMessage({
                        type: 'downloadJson',
                        data: processedData,
                        filename: getTimestampedFilename('polymarket')
                    });
                    sendResponse({ success: true });
                })
                .catch(error => sendResponse({ success: false, error: error.message }));
            return true;
        }
    }
});

// ============ Polymarket 数据处理 ============
async function processPolymarketData(predictions) {
    const enrichedData = await Promise.all(
        predictions.map(async (pred) => {
            const subpageData = await fetchPolymarketSubpageData(pred.slug);
            const cleanVolume = String(parseVolumeStr(pred.volume));

            if (pred.type === 'multi-option') {
                const result = {
                    name: pred.name,
                    type: subpageData.type,
                    subtype: subpageData.subtype,
                    volume: cleanVolume,
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
                    volume: cleanVolume,
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