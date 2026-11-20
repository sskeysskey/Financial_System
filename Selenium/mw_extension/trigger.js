// 注入 http://127.0.0.1:*/ 页面；只在 MW_Bridge 的 /start 页面上生效
(() => {
  const m = document.querySelector('meta[name="mw-bridge-token"]');
  if (!m || !m.content) return;
  const autoMeta = document.querySelector('meta[name="mw-bridge-auto"]');
  chrome.runtime.sendMessage(
    { type: 'mw_trigger', port: location.port || '80', token: m.content, auto: !!(autoMeta && autoMeta.content === '1') },
    (resp) => {
      const el = document.getElementById('status');
      if (!el) return;
      el.textContent = resp && resp.ok ? '已交给扩展控制台，此页会自动关闭。' : `扩展未响应：${(resp && resp.error) || chrome.runtime.lastError?.message || ''}`;
    }
  );
})();