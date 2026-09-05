/* Firstrade 股票标签助手 & 快捷看图 & 持仓数据回传 —— content script v3 */
(() => {
  if (window.__FT_TAG_HELPER_V3__) return;
  window.__FT_TAG_HELPER_V3__ = true;

  const LOG_PREFIX = '[FT-TAG]';
  let DEBUG = false;
  let stockTagMap = {};
  let maxTags = 2;

  /* ---------------- 持仓抓取缓存 ---------------- */
  const positionCache = Object.create(null); // { SYMBOL: {...} }
  let lastSentSig = '';
  let syncTimer = null;

  const log = (...a) => { if (DEBUG) console.log(LOG_PREFIX, ...a); };

  /* 列名 -> Python 端友好字段名 */
  const COL_ALIAS = {
    quantity: 'quantity',
    changePercent: 'day_change',
    gainlossPercent: 'gainloss',
    totalCost: 'cost',
    allocationPercent: 'allocation',
    marketValue: 'market_value',
    price: 'last_price',
    lastPrice: 'last_price',
    averageCost: 'avg_cost',
    avgCost: 'avg_cost',
    gainloss: 'gainloss_amount',
    change: 'day_change_amount'
  };

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  function safeSendMessage(msg) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, error: chrome.runtime.lastError.message });
            return;
          }
          resolve(resp || { ok: false, error: 'no response' });
        });
      } catch (e) {
        resolve({ ok: false, error: String(e) });
      }
    });
  }

  /* ---------------- 1. 全局悬浮 Popover ---------------- */
  let popoverEl = null;
  let popoverTimer = null;

  function initGlobalPopover() {
    if (popoverEl && document.body.contains(popoverEl)) return;
    popoverEl = document.createElement('div');
    popoverEl.id = 'ft-global-tag-popover';
    document.body.appendChild(popoverEl);
    popoverEl.addEventListener('mouseenter', () => clearTimeout(popoverTimer));
    popoverEl.addEventListener('mouseleave', () => hidePopover());
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function showPopover(anchorEl, symbol, tags) {
    initGlobalPopover();
    clearTimeout(popoverTimer);

    const hasTags = tags && tags.length > 0;
    const tagsHtml = hasTags
      ? tags.map(t => `<span class="ft-popover-fulltag">${escapeHtml(t)}</span>`).join('')
      : '<span style="color:#94a3b8;font-size:11px;">(无对应标签)</span>';

    // 顺带把抓到的持仓数据显示出来，方便你确认抓取是否成功
    const p = positionCache[symbol];
    let posHtml = '';
    if (p) {
      const bits = [];
      if (p.cost) bits.push(`成本 ${escapeHtml(p.cost)}`);
      if (p.day_change) bits.push(`今日 ${escapeHtml(p.day_change)}`);
      if (p.gainloss) bits.push(`盈亏 ${escapeHtml(p.gainloss)}`);
      if (p.quantity) bits.push(`数量 ${escapeHtml(p.quantity)}`);
      if (bits.length) {
        posHtml = `<div class="ft-popover-position">${bits.join(' · ')}</div>`;
      }
    } else {
      posHtml = `<div class="ft-popover-position" style="color:#bf616a;">⚠ 未抓到该行持仓数据</div>`;
    }

    popoverEl.innerHTML = `
      <div class="ft-popover-header">
        <span class="ft-popover-symbol">${escapeHtml(symbol)}</span>
        <span class="ft-popover-openchart-tip" id="ft-popover-btn-launch">📈 打开本机图表</span>
      </div>
      ${posHtml}
      <div class="ft-popover-tags-box">${tagsHtml}</div>
    `;

    const btn = popoverEl.querySelector('#ft-popover-btn-launch');
    if (btn) {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        triggerLocalChart(symbol);
      });
    }

    const rect = anchorEl.getBoundingClientRect();
    popoverEl.style.display = 'block';
    const popWidth = Math.max(popoverEl.offsetWidth, 180);
    const popHeight = popoverEl.offsetHeight;

    let left = rect.left;
    let top = rect.bottom + 4;
    if (left + popWidth > window.innerWidth - 10) left = window.innerWidth - popWidth - 10;
    if (top + popHeight > window.innerHeight - 10) top = rect.top - popHeight - 4;

    popoverEl.style.left = `${Math.max(10, left)}px`;
    popoverEl.style.top = `${top}px`;
    requestAnimationFrame(() => popoverEl.classList.add('ft-popover-show'));
  }

  function hidePopover(delay = 120) {
    if (!popoverEl) return;
    clearTimeout(popoverTimer);
    popoverTimer = setTimeout(() => {
      popoverEl.classList.remove('ft-popover-show');
      setTimeout(() => {
        if (popoverEl && !popoverEl.classList.contains('ft-popover-show')) {
          popoverEl.style.display = 'none';
        }
      }, 150);
    }, delay);
  }

  /* ---------------- 2. 拉起本机 Python 图表（先落盘再启动） ---------------- */
  async function triggerLocalChart(symbol) {
    if (!symbol) return;
    scrapeGridData();                     // 点击瞬间再抓一次，拿到最新数字
    const payload = buildPayload(symbol);
    log('请求画图:', symbol, '携带持仓条数:', Object.keys(payload).length);

    const resp = await safeSendMessage({ action: 'FT_PLOT', symbol, payload });
    if (!resp.ok) {
      console.warn(`${LOG_PREFIX} 无法连接本地桥接服务(bridge_server.py 是否在运行?)：`, resp.error);
      flashToast(`❌ 桥接失败: ${resp.error}`);
    } else {
      log('图表已启动:', resp.data);
      lastSentSig = signature();
      flashToast(`📈 ${symbol} 已发送（持仓 ${Object.keys(payload).length} 条）`);
    }
  }

  function flashToast(text) {
    let el = document.getElementById('ft-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'ft-toast';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.classList.add('ft-toast-show');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('ft-toast-show'), 2200);
  }

  /* ---------------- 3. 抓取网页真实持仓数据 ---------------- */
  function cleanText(el) {
    let t = (el.innerText || el.textContent || '');
    return t.replace(/\u00a0/g, ' ')
      .replace(/\s+/g, ' ')
      .replace(/(\d),\s+(\d)/g, '$1,$2')   // "70, 000.00" -> "70,000.00"
      .trim();
  }

  function symbolFromRowId(rowId) {
    if (!rowId) return '';
    const raw = String(rowId).split('|')[0].trim().toUpperCase();
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(raw)) return '';
    return raw;
  }

  function scrapeGridData() {
    // ★ 关键：row-id 形如 "AAPL|223.34859"，本身就带股票代码，
    //   左右两个容器（pinned-left / center-cols）共用同一个 row-id，按 symbol 聚合即可。
    const rows = document.querySelectorAll('[row-id]');
    if (!rows.length) return 0;

    const buf = Object.create(null);

    rows.forEach((row) => {
      // 排除顶部/底部的汇总浮动行
      if (row.closest('.ag-floating-top, .ag-floating-bottom')) return;

      const sym = symbolFromRowId(row.getAttribute('row-id'));
      if (!sym) return;

      const rec = buf[sym] || (buf[sym] = { symbol: sym, raw: {} });

      row.querySelectorAll('[col-id]').forEach((cell) => {
        const col = cell.getAttribute('col-id');
        if (!col || col === 'symbol') return;
        const txt = cleanText(cell);
        if (!txt) return;
        rec.raw[col] = txt;
        const alias = COL_ALIAS[col];
        if (alias) rec[alias] = txt;
      });
    });

    let changed = 0;
    Object.keys(buf).forEach((sym) => {
      const rec = buf[sym];
      // 至少要有一项有意义的数据才写缓存
      if (!(rec.cost || rec.day_change || rec.gainloss || rec.quantity)) return;
      const old = positionCache[sym];
      const merged = Object.assign({}, old || {}, rec, {
        raw: Object.assign({}, (old && old.raw) || {}, rec.raw),
        updated_at: Date.now()
      });
      const oldSig = old ? [old.cost, old.day_change, old.gainloss, old.quantity].join('|') : '';
      const newSig = [merged.cost, merged.day_change, merged.gainloss, merged.quantity].join('|');
      positionCache[sym] = merged;
      if (oldSig !== newSig) changed++;
    });

    if (changed > 0) {
      log('抓取更新', changed, '条，累计', Object.keys(positionCache).length, '条');
      debounceSync();
    }
    return Object.keys(buf).length;
  }

  function signature() {
    return Object.keys(positionCache).sort().map(k => {
      const p = positionCache[k];
      return `${k}:${p.cost}|${p.day_change}|${p.gainloss}|${p.quantity}`;
    }).join(';');
  }

  function buildPayload() {
    const out = {};
    Object.keys(positionCache).forEach(k => { out[k] = positionCache[k]; });
    return out;
  }

  function debounceSync(delay = 1200) {
    clearTimeout(syncTimer);
    syncTimer = setTimeout(() => { flushPositions(); }, delay);
  }

  async function flushPositions(force = false) {
    const payload = buildPayload();
    if (!Object.keys(payload).length) return { ok: false, error: 'cache empty' };
    const sig = signature();
    if (!force && sig === lastSentSig) return { ok: true, data: { status: 'unchanged' } };

    const resp = await safeSendMessage({ action: 'FT_SYNC', payload });
    if (resp.ok) {
      lastSentSig = sig;
      log('已同步到本机:', resp.data);
    } else {
      log('同步失败:', resp.error);
    }
    return resp;
  }

  /* 自动滚动整张表格，把所有（含虚拟滚动未渲染的）持仓都抓一遍 */
  async function fullScan() {
    const vp = document.querySelector('.ag-body-viewport');
    scrapeGridData();
    if (!vp) return flushPositions(true);

    const original = vp.scrollTop;
    const step = Math.max(150, vp.clientHeight - 60);
    let guard = 0;
    vp.scrollTop = 0;
    await sleep(250);
    scrapeGridData();

    while (guard++ < 400) {
      const atBottom = vp.scrollTop + vp.clientHeight >= vp.scrollHeight - 2;
      if (atBottom) break;
      vp.scrollTop = vp.scrollTop + step;
      await sleep(200);
      scrapeGridData();
    }
    await sleep(250);
    scrapeGridData();
    vp.scrollTop = original;
    await sleep(150);
    const r = await flushPositions(true);
    flashToast(`✅ 已抓取 ${Object.keys(positionCache).length} 只标的持仓`);
    return r;
  }

  /* ---------------- 4. 标签匹配 ---------------- */
  function getTagsForSymbol(symbol) {
    if (!symbol) return [];
    if (stockTagMap[symbol]) return stockTagMap[symbol];
    if (symbol.includes('.')) {
      const alt = symbol.replace(/\./g, '-');
      if (stockTagMap[alt]) return stockTagMap[alt];
    }
    if (symbol.includes('-')) {
      const alt = symbol.replace(/-/g, '.');
      if (stockTagMap[alt]) return stockTagMap[alt];
    }
    return [];
  }

  function loadTags() {
    chrome.storage.local.get(['stockData', 'maxTags', 'ftDebug'], (res) => {
      stockTagMap = res.stockData || {};
      maxTags = res.maxTags || 2;
      DEBUG = !!res.ftDebug;
      clearAllTags();
      scheduleInject();
    });
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (changes.stockData || changes.maxTags || changes.ftDebug) loadTags();
  });

  function clearAllTags() {
    document.querySelectorAll('.ft-custom-tag-container').forEach(el => el.remove());
  }

  function extractSymbol(el) {
    let t = (el.textContent || '').trim().toUpperCase();
    if (!t) return '';
    t = t.split(/[\s\n\r\t/(]/)[0];
    return t.replace(/[^A-Z0-9.\-]/g, '');
  }

  /* ---------------- 5. 构造徽章 ---------------- */
  function buildTagContainer(symbol, tags) {
    const box = document.createElement('span');
    box.className = 'ft-custom-tag-container';
    box.dataset.ftSymbol = symbol;

    if (tags && tags.length) {
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
    } else {
      // 没有 tag 的股票也要能一键看图
      const only = document.createElement('span');
      only.className = 'ft-custom-tag-badge ft-custom-tag-chart';
      only.textContent = '📈';
      box.appendChild(only);
    }

    box.addEventListener('mouseenter', () => showPopover(box, symbol, tags));
    box.addEventListener('mouseleave', () => hidePopover());
    box.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      triggerLocalChart(symbol);
    });
    return box;
  }

  /* ---------------- 6. 注入 ---------------- */
  function injectTags() {
    const cells = document.querySelectorAll('[col-id="symbol"]');
    if (cells.length) {
      cells.forEach((cell) => {
        if (cell.closest('.ag-header')) return;
        const anchor =
          cell.querySelector('button[data-tooltip-trigger]') ||
          cell.querySelector('button') ||
          cell.querySelector('[data-ref="eValue"]');
        if (!anchor) return;

        const row = cell.closest('[row-id]');
        const symbol = (row && symbolFromRowId(row.getAttribute('row-id'))) || extractSymbol(anchor);
        if (!symbol) return;

        anchor.dataset.ftSymbol = symbol;

        const existing = cell.querySelector('.ft-custom-tag-container');
        if (existing && existing.dataset.ftSymbol === symbol) return;
        if (existing) existing.remove();

        const tags = getTagsForSymbol(symbol);
        anchor.insertAdjacentElement('afterend', buildTagContainer(symbol, tags));
      });
    }
    scrapeGridData();
  }

  /* ---------------- 7. 调度 ---------------- */
  let timer = null;
  function scheduleInject(delay = 80) {
    if (timer) return;
    timer = setTimeout(() => { timer = null; try { injectTags(); } catch (e) { log(e); } }, delay);
  }

  function isOurNode(node) {
    if (!node || node.nodeType !== 1) return false;
    return !!(node.classList && (
      node.classList.contains('ft-custom-tag-container') ||
      node.id === 'ft-global-tag-popover' ||
      node.id === 'ft-toast'
    ));
  }

  const observer = new MutationObserver((records) => {
    for (const r of records) {
      if (isOurNode(r.target)) continue;
      scheduleInject();
      return;
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  document.addEventListener('scroll', () => scheduleInject(20), true);
  window.addEventListener('resize', () => scheduleInject(100));
  setInterval(() => scheduleInject(0), 2000);
  setInterval(() => { scrapeGridData(); flushPositions(); }, 30000); // 定期兜底同步

  /* ---------------- 8. 与 popup 通信 ---------------- */
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || !msg.action) return;
    if (msg.action === 'refreshTags') { loadTags(); sendResponse({ ok: true }); return; }
    if (msg.action === 'FT_DUMP') {
      scrapeGridData();
      sendResponse({ ok: true, count: Object.keys(positionCache).length, data: positionCache });
      return;
    }
    if (msg.action === 'FT_SYNC_ALL') {
      fullScan().then(r => sendResponse({ ok: true, count: Object.keys(positionCache).length, server: r }))
        .catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }
  });

  initGlobalPopover();
  loadTags();
  console.log(LOG_PREFIX, 'Content Script v3 初始化完成');
})();