/* Firstrade 股票标签助手 & 快捷看图 —— content script */
(() => {
  const LOG_PREFIX = '[FT-TAG]';
  const BRIDGE_URL = 'http://127.0.0.1:18888/plot?symbol=';
  let DEBUG = false;
  let stockTagMap = {};
  let maxTags = 2; // 表格内默认显示2个，剩余在悬浮卡片中展示

  const log = (...a) => { if (DEBUG) console.log(LOG_PREFIX, ...a); };

  /* ---------------- 1. 全局悬浮 Popover 管理器 ---------------- */
  let popoverEl = null;
  let popoverTimer = null;

  function initGlobalPopover() {
    if (popoverEl) return;
    popoverEl = document.createElement('div');
    popoverEl.id = 'ft-global-tag-popover';
    document.body.appendChild(popoverEl);

    popoverEl.addEventListener('mouseenter', () => {
      clearTimeout(popoverTimer);
    });
    popoverEl.addEventListener('mouseleave', () => {
      hidePopover();
    });
  }

  function showPopover(anchorEl, symbol, tags) {
    initGlobalPopover();
    clearTimeout(popoverTimer);

    const hasTags = tags && tags.length > 0;
    const tagsHtml = hasTags
      ? tags.map(t => `<span class="ft-popover-fulltag">${t}</span>`).join('')
      : '<span style="color:#94a3b8;font-size:11px;">(无对应标签)</span>';

    // 构建内容：包含股票名、全部标签、以及拉起本地看图的按钮
    popoverEl.innerHTML = `
      <div class="ft-popover-header">
        <span class="ft-popover-symbol">${symbol}</span>
        <span class="ft-popover-openchart-tip" id="ft-popover-btn-launch">📈 打开本机图表</span>
      </div>
      <div class="ft-popover-tags-box">
        ${tagsHtml}
      </div>
    `;

    document.getElementById('ft-popover-btn-launch').addEventListener('click', (e) => {
      e.stopPropagation();
      triggerLocalChart(symbol);
    });

    // 计算精准定位（浮动在 anchor 正下方或正上方）
    const rect = anchorEl.getBoundingClientRect();
    popoverEl.style.display = 'block';
    const popWidth = Math.max(popoverEl.offsetWidth, 180);
    const popHeight = popoverEl.offsetHeight;

    let left = rect.left;
    let top = rect.bottom + 4;

    // 屏幕右侧防溢出
    if (left + popWidth > window.innerWidth - 10) {
      left = window.innerWidth - popWidth - 10;
    }
    // 屏幕底部防溢出（朝上展示）
    if (top + popHeight > window.innerHeight - 10) {
      top = rect.top - popHeight - 4;
    }

    popoverEl.style.left = `${Math.max(10, left)}px`;
    popoverEl.style.top = `${top}px`;

    requestAnimationFrame(() => {
      popoverEl.classList.add('ft-popover-show');
    });
  }

  function hidePopover(delay = 120) {
    if (!popoverEl) return;
    clearTimeout(popoverTimer);
    popoverTimer = setTimeout(() => {
      popoverEl.classList.remove('ft-popover-show');
      setTimeout(() => {
        if (!popoverEl.classList.contains('ft-popover-show')) {
          popoverEl.style.display = 'none';
        }
      }, 150);
    }, delay);
  }

  /* ---------------- 2. 触发本机 Python 图表 ---------------- */
  function triggerLocalChart(symbol) {
    if (!symbol) return;
    log('向本地桥接服务发送请求拉起图表:', symbol);

    fetch(`${BRIDGE_URL}${encodeURIComponent(symbol)}`, { method: 'GET', mode: 'cors' })
      .then(r => r.json())
      .then(res => {
        log('本地图表启动成功:', res);
      })
      .catch(err => {
        console.warn(`${LOG_PREFIX} 无法连接到本地 Python 桥接服务。请确保 chart_bridge_server.py 已在后台运行。`, err);
      });
  }

  /* ---------------- 3. 数据载入与监听 ---------------- */
  function loadTags() {
    chrome.storage.local.get(['stockData', 'maxTags'], (res) => {
      stockTagMap = res.stockData || {};
      maxTags = res.maxTags || 2;
      log('已载入标签数据，标的数量 =', Object.keys(stockTagMap).length);
      clearAllTags();
      scheduleInject();
    });
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (changes.stockData || changes.maxTags) {
      log('检测到配置更新，重新渲染');
      loadTags();
    }
  });

  function clearAllTags() {
    document.querySelectorAll('.ft-custom-tag-container').forEach(el => el.remove());
    document.querySelectorAll('.ft-chart-trigger-btn').forEach(el => el.remove());
  }

  function extractSymbol(el) {
    let t = (el.textContent || '').trim().toUpperCase();
    if (!t) return '';
    t = t.split(/[\s\n\r\t/(]/)[0];
    t = t.replace(/[^A-Z0-9.\-]/g, '');
    return t;
  }

  /* ---------------- 4. 构造 DOM 节点 ---------------- */
  function buildTagContainer(symbol, tags) {
    const box = document.createElement('span');
    box.className = 'ft-custom-tag-container';
    box.dataset.ftSymbol = symbol;

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
      more.textContent = `+${tags.length - shown.length}`;
      box.appendChild(more);
    }

    // tag 容器仅做静态展示，不再绑定悬浮弹窗
    return box;
  }

  /* ---------------- 5. 渲染与注入 ---------------- */
  function injectTags() {
    const cells = document.querySelectorAll('[col-id="symbol"]');
    if (!cells.length) return;

    let added = 0;
    cells.forEach((cell) => {
      const anchor =
        cell.querySelector('button[data-tooltip-trigger]') ||
        cell.querySelector('button') ||
        cell.querySelector('[data-ref="eValue"]');
      if (!anchor) return;

      const symbol = extractSymbol(anchor);
      if (!symbol) return;

      // 更新 anchor 上记录的当前 symbol（防止虚拟滚动 DOM 复用错位）
      anchor.dataset.ftSymbol = symbol;

      // 为股票代码 anchor 绑定事件：悬浮出浮窗、点击拉起本地图表
      if (!anchor.dataset.ftBound) {
        anchor.dataset.ftBound = 'true';

        // 1. 悬停在股票代码上时弹出 Popover
        anchor.addEventListener('mouseenter', () => {
          const curSym = anchor.dataset.ftSymbol;
          if (!curSym) return;
          const tags = stockTagMap[curSym] || [];
          showPopover(anchor, curSym, tags);
        });

        anchor.addEventListener('mouseleave', () => {
          hidePopover();
        });

        // 2. 点击原股票代码依然触发本地画图
        anchor.addEventListener('click', () => {
          const curSym = anchor.dataset.ftSymbol;
          if (curSym) triggerLocalChart(curSym);
        });
      }

      // 移除原有可能残留的小图标
      const existingBtn = cell.querySelector('.ft-chart-trigger-btn');
      if (existingBtn) existingBtn.remove();

      // 检查标签胶囊是否需要更新
      const existingTag = cell.querySelector('.ft-custom-tag-container');
      if (existingTag && existingTag.dataset.ftSymbol === symbol) return;

      if (existingTag) existingTag.remove();

      // 插入 Tag 胶囊（若该股票有 tag）
      const tags = stockTagMap[symbol];
      if (tags && tags.length) {
        const tagBox = buildTagContainer(symbol, tags);
        anchor.insertAdjacentElement('afterend', tagBox);
      }
      added++;
    });

    if (added) log('本次渲染行数 =', added);
  }

  /* ---------------- 6. 监听与轮询调度 ---------------- */
  let timer = null;
  function scheduleInject(delay = 80) {
    if (timer) return;
    timer = setTimeout(() => { timer = null; injectTags(); }, delay);
  }

  function isOurNode(node) {
    if (!node || node.nodeType !== 1) return false;
    return !!(
      node.classList && (
        node.classList.contains('ft-custom-tag-container') ||
        node.id === 'ft-global-tag-popover'
      )
    );
  }

  const observer = new MutationObserver((records) => {
    for (const r of records) {
      if (isOurNode(r.target)) continue;
      scheduleInject();
      return;
    }
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true
  });

  document.addEventListener('scroll', () => scheduleInject(20), true);
  window.addEventListener('resize', () => scheduleInject(100));
  setInterval(() => scheduleInject(0), 1500);

  initGlobalPopover();
  loadTags();
  log('Content Script 初始化成功');
})();