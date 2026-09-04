/* Firstrade 股票标签助手 —— content script */
(() => {
  const LOG_PREFIX = '[FT-TAG]';
  let DEBUG = true;                 // 排查完可改成 false
  let stockTagMap = {};
  let maxTags = 4;

  const log = (...a) => { if (DEBUG) console.log(LOG_PREFIX, ...a); };

  /* ---------------- 数据读取 ---------------- */
  function loadTags() {
    chrome.storage.local.get(['stockData', 'maxTags'], (res) => {
      stockTagMap = res.stockData || {};
      maxTags = res.maxTags || 4;
      log('已载入标签数据，标的数量 =', Object.keys(stockTagMap).length);
      clearAllTags();
      scheduleInject();
    });
  }

  // 弹窗写入 storage 后自动刷新（最可靠，不依赖消息通道）
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (changes.stockData || changes.maxTags) {
      log('检测到数据更新，重新渲染');
      loadTags();
    }
  });

  // 兼容弹窗主动发消息
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg && msg.action === 'refreshTags') {
      loadTags();
      sendResponse && sendResponse({ ok: true });
    }
    return true;
  });

  /* ---------------- 工具 ---------------- */
  function clearAllTags() {
    document.querySelectorAll('.ft-custom-tag-container').forEach(el => el.remove());
  }

  // 从单元格里提取股票代码：只取第一段、只保留 A-Z 0-9 . -
  function extractSymbol(el) {
    let t = (el.textContent || '').trim().toUpperCase();
    if (!t) return '';
    t = t.split(/[\s\n\r\t/(]/)[0];
    t = t.replace(/[^A-Z0-9.\-]/g, '');
    return t;
  }

  function buildContainer(symbol, tags) {
    const box = document.createElement('span');
    box.className = 'ft-custom-tag-container';
    box.dataset.ftSymbol = symbol;                 // 关键：记录属于哪个代码
    box.title = symbol + '：' + tags.join(' / ');  // 悬停看全部

    const shown = tags.slice(0, maxTags);
    shown.forEach((txt) => {
      const s = document.createElement('span');
      s.className = 'ft-custom-tag-badge';
      s.textContent = txt;
      box.appendChild(s);
    });
    if (tags.length > shown.length) {
      const more = document.createElement('span');
      more.className = 'ft-custom-tag-badge ft-custom-tag-more';
      more.textContent = '+' + (tags.length - shown.length);
      box.appendChild(more);
    }
    return box;
  }

  /* ---------------- 渲染 ---------------- */
  function injectTags() {
    if (!Object.keys(stockTagMap).length) return;

    // symbol 列的所有单元格（含分组行/普通行）
    const cells = document.querySelectorAll('[col-id="symbol"]');
    if (!cells.length) return;

    let added = 0;
    cells.forEach((cell) => {
      // 优先取股票代码按钮，取不到就退回 ag-group-value
      const anchor =
        cell.querySelector('button[data-tooltip-trigger]') ||
        cell.querySelector('button') ||
        cell.querySelector('[data-ref="eValue"]');
      if (!anchor) return;

      const symbol = extractSymbol(anchor);
      const existing = cell.querySelector('.ft-custom-tag-container');

      // 虚拟滚动会复用 DOM：代码变了就必须重建，避免标签错位
      if (existing && existing.dataset.ftSymbol === symbol) return;
      if (existing) existing.remove();
      if (!symbol) return;

      const tags = stockTagMap[symbol];
      if (!tags || !tags.length) return;

      anchor.insertAdjacentElement('afterend', buildContainer(symbol, tags));
      added++;
    });

    if (added) log('本次渲染标签行数 =', added);
  }

  /* ---------------- 调度：防抖 + 忽略自身变更 ---------------- */
  let timer = null;
  function scheduleInject(delay = 80) {
    if (timer) return;
    timer = setTimeout(() => { timer = null; injectTags(); }, delay);
  }

  function isOurNode(node) {
    if (!node || node.nodeType !== 1) return false;
    return !!(node.classList && node.classList.contains('ft-custom-tag-container')) ||
      !!(node.closest && node.closest('.ft-custom-tag-container'));
  }

  const observer = new MutationObserver((records) => {
    for (const r of records) {
      if (isOurNode(r.target)) continue;
      const addedOurs = Array.from(r.addedNodes).every(isOurNode) && r.addedNodes.length > 0;
      const removedOurs = Array.from(r.removedNodes).every(isOurNode) && r.removedNodes.length > 0;
      if (addedOurs && r.removedNodes.length === 0) continue;
      if (removedOurs && r.addedNodes.length === 0) continue;
      scheduleInject();
      return;
    }
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true
  });

  // 滚动时立即补渲染（ag-Grid 虚拟滚动）
  document.addEventListener('scroll', () => scheduleInject(30), true);
  window.addEventListener('resize', () => scheduleInject(150));

  // 兜底轮询（幂等、开销极小），应对 SPA 路由切换
  setInterval(() => scheduleInject(0), 1500);

  /* ---------------- 调试入口 ---------------- */
  window.__ftTagDebug = () => {
    const cells = document.querySelectorAll('[col-id="symbol"]');
    const syms = [];
    cells.forEach((c) => {
      const a = c.querySelector('button') || c.querySelector('[data-ref="eValue"]');
      if (a) syms.push(extractSymbol(a));
    });
    const info = {
      symbolCells: cells.length,
      pageSymbols: syms,
      jsonSymbols: Object.keys(stockTagMap).length,
      matched: syms.filter(s => stockTagMap[s]),
      injected: document.querySelectorAll('.ft-custom-tag-container').length
    };
    console.log(LOG_PREFIX, info);
    return info;
  };

  log('content script 已注入：', location.href);
  loadTags();
})();