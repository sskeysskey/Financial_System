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
                // ★ 单选项类型也加入 type 和 subtype
                return {
                    name: pred.name,
                    type: subpageData.type,
                    subtype: subpageData.subtype,
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

// ★ 重写：从子页面 HTML 中正确提取 type、subtype、enddate
async function fetchPolymarketSubpageData(slug) {
    try {
        const response = await fetch(`https://polymarket.com/event/${slug}`);
        const html = await response.text();

        var type = '';
        var subtype = '';
        var enddate = '';

        // ══════════════════════════════════════════════
        // 提取 type 和 subtype: 匹配面包屑导航
        // 目标结构: <a href="...">Type</a> <span>•</span> <a href="/predictions/...">Subtype</a>
        // ══════════════════════════════════════════════
        var breadcrumbRegex = /<a[^>]*href="\/[^"]*"[^>]*>\s*([^<]+?)\s*<\/a>\s*<span[^>]*>[•·]<\/span>\s*<a[^>]*href="\/predictions\/[^"]*"[^>]*>\s*([^<]+?)\s*<\/a>/i;
        var breadcrumbMatch = html.match(breadcrumbRegex);

        if (breadcrumbMatch) {
            // 成功匹配到完整的面包屑
            type = breadcrumbMatch[1].trim();
            subtype = breadcrumbMatch[2].trim();
        } else {
            // 降级方案：如果页面结构变化没匹配到完整的面包屑，尝试只抓取 subtype
            var subtypeMatch = html.match(/<a[^>]*href="\/predictions\/[^"]*"[^>]*>\s*([^<]+?)\s*<\/a>/i);
            if (subtypeMatch) {
                subtype = subtypeMatch[1].trim();
            }
        }

        // 如果只找到一个，另一个也设为相同值兜底
        if (type && !subtype) subtype = type;
        if (subtype && !type) type = subtype;

        // ══════════════════════════════════════════════
        // 提取 enddate: 匹配页面中的日期格式
        // ══════════════════════════════════════════════
        var dateMatch = html.match(
            /(\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b)/i
        );
        if (dateMatch) {
            enddate = dateMatch[1].trim();
        }

        return { type: type, subtype: subtype, enddate: enddate };
    } catch (error) {
        console.error('Error fetching Polymarket subpage (' + slug + '):', error);
        return { type: '', subtype: '', enddate: '' };
    }
}