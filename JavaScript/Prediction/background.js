// 新流程不再依赖 background 做 Polymarket 数据处理。
// 保留文件只是为了 manifest 中的 service_worker 注册。
chrome.runtime.onInstalled.addListener(function () {
    console.log('Prediction Market Scraper installed/updated');
});