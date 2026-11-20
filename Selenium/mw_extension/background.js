'use strict';
// 只负责：接收桥接 /start 页面的触发 → 打开（或复用）控制台 runner.html
const RUNNER = chrome.runtime.getURL('runner.html');

async function openRunner({ port, token, auto }, senderTab) {
  const url = `${RUNNER}?port=${encodeURIComponent(port)}&token=${encodeURIComponent(token)}&auto=${auto ? 1 : 0}`;
  const tabs = await chrome.tabs.query({});
  const existing = tabs.find((t) => t.url && t.url.startsWith(RUNNER));
  if (existing) {
    // 同一次运行（同令牌）→ 只聚焦，控制台继续；新的运行 → 用新参数重新加载
    if (existing.url !== url) await chrome.tabs.update(existing.id, { url });
    await chrome.tabs.update(existing.id, { active: true });
  } else {
    await chrome.tabs.create({ url, active: true, windowId: senderTab ? senderTab.windowId : undefined });
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === 'mw_trigger') {
    openRunner(msg, sender.tab)
      .then(() => {
        sendResponse({ ok: true });
        if (sender.tab) setTimeout(() => chrome.tabs.remove(sender.tab.id).catch(() => { }), 800);
      })
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  return false;
});