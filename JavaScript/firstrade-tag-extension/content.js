/* ============================================================================
 * Firstrade 助手 content script v5
 *  1) Tag 徽章 + 一键看图（纯展示）
 *  2) 持仓抓取：仅 /app/positions      —— 开关 ftAutoPositions
 *  3) 订单痕迹：仅 /app/order-status    —— 开关 ftAutoOrders
 *  ★ 自选股（/app/watchlist）的抓取与批量补齐由 watchlist.js 负责
 *  ★ 三个自动开关互相独立，默认全部关闭
 * ==========================================================================*/
(() => {
  if (window.__FT_TAG_HELPER_V5__) return;
  window.__FT_TAG_HELPER_V5__ = true;

  const LOG_PREFIX = '[FT]';
  let DEBUG = false;
  let AUTO_POSITIONS = false;     // ★ 独立开关
  let AUTO_ORDERS = false;        // ★ 独立开关
  let stockTagMap = {};
  let maxTags = 2;

  const log = (...a) => { if (DEBUG) console.log(LOG_PREFIX, ...a); };
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  /* ==================== 0. 页面闸门（双重校验） ==================== */
  const PAGE_RULES = [
    { key: 'positions', re: /\/positions?(\/|$|\?|#)/i },
    { key: 'orders', re: /\/order-status/i },
    { key: 'watchlist', re: /\/watchlist/i }
  ];

  function detectPage() {
    const p = (location.pathname || '').toLowerCase();
    for (const r of PAGE_RULES) if (r.re.test(p)) return r.key;
    return null;
  }
  let PAGE = detectPage();

  const POSITION_COL_HINTS = ['allocationPercent', 'marketValue', 'gainlossPercent',
    'totalCost', 'changePercent', 'quantity', 'averageCost'];
  const ORDER_COL_HINTS = ['transaction', 'statusCategory', 'durationType',
    'instructionType', 'limitPrice', 'priceType'];

  function colIdSet() {
    const s = new Set();
    document.querySelectorAll('[col-id]').forEach(el => s.add(el.getAttribute('col-id')));
    return s;
  }

  function gridLooksLike(kind) {
    const s = colIdSet();
    if (!s.has('symbol')) return false;
    if (kind === 'positions') {
      if (s.has('transaction') || s.has('statusCategory') || s.has('durationType')) return false;
      return POSITION_COL_HINTS.filter(c => s.has(c)).length >= 2;
    }
    if (kind === 'orders') {
      if (!s.has('transaction')) return false;
      return s.has('statusCategory') || s.has('limitPrice') || s.has('durationType');
    }
    return false;
  }

  const canScrapePositions = () => PAGE === 'positions' && gridLooksLike('positions');
  const canScrapeOrders = () => PAGE === 'orders' && gridLooksLike('orders');

  /* 自选股批量补齐进行中 → 暂停一切 DOM 注入，减少干扰 */
  const automationBusy = () => window.__FT_AUTOMATION__ === true;

  /* ==================== 1. 缓存与通用工具 ==================== */
  const positionCache = Object.create(null);
  const orderCache = Object.create(null);
  let lastSentSig = '';
  let lastOrderSig = '';
  let syncTimer = null;
  let orderSyncTimer = null;

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
      } catch (e) { resolve({ ok: false, error: String(e) }); }
    });
  }

  function cleanText(el) {
    let t = (el.innerText || el.textContent || '');
    return t.replace(/\u00a0/g, ' ')
      .replace(/\s+/g, ' ')
      .replace(/(\d),\s+(\d)/g, '$1,$2')
      .trim();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  const toNum = (s) => {
    if (s === null || s === undefined) return null;
    const m = String(s).replace(/\s/g, '').match(/-?\d[\d,]*\.?\d*/);
    return m ? parseFloat(m[0].replace(/,/g, '')) : null;
  };

  const pad2 = (n) => String(parseInt(n, 10)).padStart(2, '0');

  function parseUpdatedDate(txt) {
    if (!txt) return '';
    const head = String(txt).split(',')[0].trim();
    let m = head.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m) return `${m[3]}-${pad2(m[1])}-${pad2(m[2])}`;
    m = head.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (m) return `${m[1]}-${pad2(m[2])}-${pad2(m[3])}`;
    m = head.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2})$/);
    if (m) return `20${m[3]}-${pad2(m[1])}-${pad2(m[2])}`;
    return '';
  }

  function symbolFromRowId(rowId) {
    if (!rowId) return '';
    const raw = String(rowId).split('|')[0].trim().toUpperCase();
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(raw)) return '';
    return raw;
  }

  function extractSymbol(el) {
    let t = (el.textContent || '').trim().toUpperCase();
    if (!t) return '';
    t = t.split(/[\s\n\r\t/(]/)[0];
    return t.replace(/[^A-Z0-9.\-]/g, '');
  }

  function symbolFromCell(cell) {
    const tagged = cell.querySelector('[data-ft-symbol]');
    if (tagged && tagged.dataset.ftSymbol) return tagged.dataset.ftSymbol;
    const btn = cell.querySelector('button[data-tooltip-trigger]') ||
      cell.querySelector('button') ||
      cell.querySelector('[data-ref="eValue"]');
    if (!btn) return '';
    const clone = btn.cloneNode(true);
    clone.querySelectorAll('.ft-custom-tag-container').forEach(n => n.remove());
    return extractSymbol(clone);
  }

  /* ==================== 2. 全局悬浮 Popover ==================== */
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

  function showPopover(anchorEl, symbol, tags) {
    initGlobalPopover();
    clearTimeout(popoverTimer);

    const hasTags = tags && tags.length > 0;
    const tagsHtml = hasTags
      ? tags.map(t => `<span class="ft-popover-fulltag">${escapeHtml(t)}</span>`).join('')
      : '<span style="color:#94a3b8;font-size:11px;">(无对应标签)</span>';

    let posHtml = '';
    const p = positionCache[symbol];
    if (p) {
      const bits = [];
      if (p.cost) bits.push(`成本 ${escapeHtml(p.cost)}`);
      if (p.day_change) bits.push(`今日 ${escapeHtml(p.day_change)}`);
      if (p.gainloss) bits.push(`盈亏 ${escapeHtml(p.gainloss)}`);
      if (p.quantity) bits.push(`数量 ${escapeHtml(p.quantity)}`);
      if (bits.length) posHtml = `<div class="ft-popover-position">${bits.join(' · ')}</div>`;
    } else {
      posHtml = `<div class="ft-popover-position" style="color:#81A1C1;">本页未抓取，图表会读取本机已保存的 JSON</div>`;
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
    if (btn) btn.addEventListener('click', (e) => { e.stopPropagation(); triggerLocalChart(symbol); });

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

  function flashToast(text) {
    let el = document.getElementById('ft-toast');
    if (!el) { el = document.createElement('div'); el.id = 'ft-toast'; document.body.appendChild(el); }
    el.textContent = text;
    el.classList.add('ft-toast-show');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('ft-toast-show'), 2400);
  }
  window.__FT_TOAST__ = flashToast;      // 供 watchlist.js 复用

  /* ==================== 3. 拉起本机 Python 图表 ==================== */
  async function triggerLocalChart(symbol) {
    if (!symbol) return;
    const resp = await safeSendMessage({ action: 'FT_PLOT', symbol, payload: {} });
    if (!resp.ok) {
      console.warn(`${LOG_PREFIX} 无法连接本地桥接服务(bridge_server.py 是否在运行?)：`, resp.error);
      flashToast(`❌ 桥接失败: ${resp.error}`);
    } else {
      log('图表已启动:', resp.data);
      flashToast(`📈 ${symbol} 已发送`);
    }
  }

  /* ==================== 4. 持仓抓取（仅 positions 页） ==================== */
  function scrapeGridData() {
    if (!canScrapePositions()) return 0;

    const rows = document.querySelectorAll('[row-id]');
    if (!rows.length) return 0;
    const buf = Object.create(null);

    rows.forEach((row) => {
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
      log('持仓抓取更新', changed, '条，累计', Object.keys(positionCache).length);
      if (AUTO_POSITIONS) debounceSync();
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

  async function flushPositions(force = false, overwrite = false) {
    const payload = buildPayload();
    if (!Object.keys(payload).length && !overwrite) return { ok: false, error: 'cache empty' };
    const sig = signature();
    if (!force && !overwrite && sig === lastSentSig) return { ok: true, data: { status: 'unchanged' } };
    const resp = await safeSendMessage({ action: 'FT_SYNC', payload, overwrite });
    if (resp.ok) { lastSentSig = sig; log('持仓已同步:', resp.data); }
    else log('持仓同步失败:', resp.error);
    return resp;
  }

  async function fullScan() {
    if (!canScrapePositions()) {
      return { ok: false, error: `当前页面不是持仓页（PAGE=${PAGE}），已拒绝抓取` };
    }
    for (const sym of Object.keys(positionCache)) delete positionCache[sym];
    lastSentSig = '';

    const vp = document.querySelector('.ag-body-viewport');
    scrapeGridData();
    if (!vp) return flushPositions(true, true);

    const original = vp.scrollTop;
    const step = Math.max(150, vp.clientHeight - 60);
    let guard = 0;
    vp.scrollTop = 0;
    await sleep(250);
    scrapeGridData();
    while (guard++ < 400) {
      if (vp.scrollTop + vp.clientHeight >= vp.scrollHeight - 2) break;
      vp.scrollTop = vp.scrollTop + step;
      await sleep(200);
      scrapeGridData();
    }
    await sleep(250);
    scrapeGridData();
    vp.scrollTop = original;
    await sleep(150);

    const r = await flushPositions(true, true);
    flashToast(`✅ 已全量刷新并保存 ${Object.keys(positionCache).length} 只持仓`);
    return r;
  }

  /* ==================== 5. 订单痕迹抓取（仅 order-status 页） ==================== */
  const ORDER_FIELD_COLS = {
    updated: ['updated', 'updatedTime', 'updateTime', 'time', 'date'],
    side: ['transaction', 'action', 'side'],
    qty: ['0', 'quantity', 'qty', 'amount', 'dollarAmount', 'orderAmount'],
    priceType: ['priceType'],
    price: ['limitPrice', 'price', 'stopPrice'],
    duration: ['durationType'],
    instruction: ['instructionType'],
    status: ['statusCategory', 'status', 'orderStatus']
  };

  function pickCol(raw, keys) {
    for (const k of keys) {
      if (raw[k] !== undefined && raw[k] !== null && raw[k] !== '') return raw[k];
    }
    return '';
  }

  function normalizeOrder(rec) {
    const raw = rec.raw || {};
    const updatedTxt = pickCol(raw, ORDER_FIELD_COLS.updated);
    const date = parseUpdatedDate(updatedTxt);
    const sideTxt = pickCol(raw, ORDER_FIELD_COLS.side);
    let side = '';
    if (/买|buy|bought/i.test(sideTxt)) side = 'buy';
    else if (/卖|sell|sold/i.test(sideTxt)) side = 'sell';

    const sym = rec.symbol || '';
    if (!sym || !date || !side) return false;

    let qtyTxt = pickCol(raw, ORDER_FIELD_COLS.qty);
    if (!qtyTxt && raw['@3']) qtyTxt = raw['@3'];
    const isDollar = /\$/.test(qtyTxt);
    const qtyNum = toNum(qtyTxt);
    const price = toNum(pickCol(raw, ORDER_FIELD_COLS.price));

    let amount = null, quantity = null, source = 'unknown';
    if (isDollar && qtyNum !== null) { amount = qtyNum; source = 'dollar'; }
    else if (qtyNum !== null) {
      quantity = qtyNum;
      if (price !== null && price > 0) { amount = qtyNum * price; source = 'qty*price'; }
      else source = 'qty_only';
    }

    const key = rec.row_id ? String(rec.row_id)
      : `${date}|${sym}|${side}|${qtyTxt}|${price}`;

    const out = {
      key: key,
      order_id: rec.row_id || '',
      symbol: sym,
      side: side,
      side_text: sideTxt,
      date: date,
      datetime: updatedTxt,
      quantity: quantity,
      amount: amount === null ? null : Math.round(amount * 100) / 100,
      price: price,
      amount_source: source,
      price_type: pickCol(raw, ORDER_FIELD_COLS.priceType),
      duration: pickCol(raw, ORDER_FIELD_COLS.duration),
      instruction: pickCol(raw, ORDER_FIELD_COLS.instruction),
      status: pickCol(raw, ORDER_FIELD_COLS.status),
      raw: raw,
      scraped_at: Date.now()
    };

    const old = orderCache[key];
    orderCache[key] = old ? Object.assign({}, old, out) : out;
    return !old || JSON.stringify(old.status) !== JSON.stringify(out.status);
  }

  function scrapeOrderGrid() {
    if (!canScrapeOrders()) return 0;
    const rows = document.querySelectorAll('[row-id]');
    if (!rows.length) return 0;

    const buf = Object.create(null);
    rows.forEach((row) => {
      if (row.closest('.ag-floating-top, .ag-floating-bottom')) return;
      const rid = row.getAttribute('row-id');
      if (!rid) return;
      const rec = buf[rid] || (buf[rid] = { row_id: rid, raw: {} });
      row.querySelectorAll('[col-id]').forEach((cell) => {
        const col = cell.getAttribute('col-id');
        if (!col) return;
        if (col === 'symbol') {
          const sym = symbolFromCell(cell);
          if (sym) rec.symbol = sym;
          return;
        }
        const txt = cleanText(cell);
        if (!txt) return;
        rec.raw[col] = txt;
        const ci = cell.getAttribute('aria-colindex');
        if (ci) rec.raw['@' + ci] = txt;
      });
    });

    let changed = 0;
    Object.keys(buf).forEach((rid) => { if (normalizeOrder(buf[rid])) changed++; });
    if (changed > 0) {
      log('订单抓取更新', changed, '条，累计', Object.keys(orderCache).length);
      if (AUTO_ORDERS) debounceOrderSync();
    }
    return Object.keys(buf).length;
  }

  function debounceOrderSync(delay = 1500) {
    clearTimeout(orderSyncTimer);
    orderSyncTimer = setTimeout(() => { flushOrders(); }, delay);
  }

  async function flushOrders(force = false) {
    const payload = {};
    Object.keys(orderCache).forEach(k => { payload[k] = orderCache[k]; });
    const n = Object.keys(payload).length;
    if (!n) return { ok: false, error: 'order cache empty' };
    const sig = `${n}|` + Object.keys(payload).sort().join(',');
    if (!force && sig === lastOrderSig) return { ok: true, data: { status: 'unchanged' } };
    const resp = await safeSendMessage({ action: 'FT_SYNC_ORDERS', payload });
    if (resp.ok) { lastOrderSig = sig; log('订单已追加:', resp.data); }
    else log('订单同步失败:', resp.error);
    return resp;
  }

  async function fullScanOrders() {
    if (!canScrapeOrders()) {
      return { ok: false, error: `当前页面不是订单页（PAGE=${PAGE}），已拒绝抓取` };
    }
    const vp = document.querySelector('.ag-body-viewport');
    scrapeOrderGrid();
    if (vp) {
      const original = vp.scrollTop;
      const step = Math.max(150, vp.clientHeight - 60);
      let guard = 0;
      vp.scrollTop = 0;
      await sleep(250);
      scrapeOrderGrid();
      while (guard++ < 400) {
        if (vp.scrollTop + vp.clientHeight >= vp.scrollHeight - 2) break;
        vp.scrollTop = vp.scrollTop + step;
        await sleep(200);
        scrapeOrderGrid();
      }
      await sleep(250);
      scrapeOrderGrid();
      vp.scrollTop = original;
      await sleep(150);
    }
    const r = await flushOrders(true);
    flashToast(`✅ 已抓取 ${Object.keys(orderCache).length} 笔订单（追加写入）`);
    return r;
  }

  /* ==================== 6. 标签匹配与注入（纯展示） ==================== */
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

  function loadSettings() {
    chrome.storage.local.get(
      ['stockData', 'maxTags', 'ftDebug', 'ftAutoPositions', 'ftAutoOrders', 'ftAutoScrape'],
      (res) => {
        stockTagMap = res.stockData || {};
        maxTags = res.maxTags || 2;
        DEBUG = !!res.ftDebug;
        const legacy = res.ftAutoScrape === true;
        AUTO_POSITIONS = res.ftAutoPositions === undefined ? legacy : res.ftAutoPositions === true;
        AUTO_ORDERS = res.ftAutoOrders === undefined ? legacy : res.ftAutoOrders === true;
        log('设置已加载 AUTO_POSITIONS=', AUTO_POSITIONS, 'AUTO_ORDERS=', AUTO_ORDERS, 'PAGE=', PAGE);
        clearAllTags();
        scheduleInject();
      });
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (changes.stockData || changes.maxTags || changes.ftDebug ||
      changes.ftAutoPositions || changes.ftAutoOrders || changes.ftAutoScrape) loadSettings();
  });

  function clearAllTags() {
    document.querySelectorAll('.ft-custom-tag-container').forEach(el => el.remove());
  }

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
      const only = document.createElement('span');
      only.className = 'ft-custom-tag-badge ft-custom-tag-chart';
      only.textContent = '📈';
      box.appendChild(only);
    }

    box.addEventListener('mouseenter', () => showPopover(box, symbol, tags));
    box.addEventListener('mouseleave', () => hidePopover());
    box.addEventListener('click', (e) => {
      e.stopPropagation(); e.preventDefault();
      triggerLocalChart(symbol);
    });
    return box;
  }

  function injectTags() {
    if (automationBusy()) return;           // ★ 批量补齐进行中，不注入

    const cells = document.querySelectorAll('[col-id="symbol"]');
    cells.forEach((cell) => {
      if (cell.closest('.ag-header')) return;
      const anchor =
        cell.querySelector('button[data-tooltip-trigger]') ||
        cell.querySelector('button') ||
        cell.querySelector('[data-ref="eValue"]');
      if (!anchor) return;

      const row = cell.closest('[row-id]');
      const symbol = (row && symbolFromRowId(row.getAttribute('row-id'))) || symbolFromCell(cell);
      if (!symbol) return;

      anchor.dataset.ftSymbol = symbol;
      const existing = cell.querySelector('.ft-custom-tag-container');
      if (existing && existing.dataset.ftSymbol === symbol) return;
      if (existing) existing.remove();
      anchor.insertAdjacentElement('afterend', buildTagContainer(symbol, getTagsForSymbol(symbol)));
    });

    if (AUTO_POSITIONS && PAGE === 'positions') scrapeGridData();
    if (AUTO_ORDERS && PAGE === 'orders') scrapeOrderGrid();
  }

  /* ==================== 7. 调度 ==================== */
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
      node.id === 'ft-toast' ||
      node.id === 'ft-wl-hud' ||
      (node.closest && node.closest('#ft-wl-hud'))
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

  /* 定期兜底同步：仅在对应开关打开时才动作 */
  setInterval(() => {
    if (automationBusy()) return;
    if (AUTO_POSITIONS && PAGE === 'positions') { scrapeGridData(); flushPositions(); }
    if (AUTO_ORDERS && PAGE === 'orders') { scrapeOrderGrid(); flushOrders(); }
  }, 30000);

  /* SPA 路由变化 → 重新判定页面 */
  let lastHref = location.href;
  setInterval(() => {
    if (location.href === lastHref) return;
    lastHref = location.href;
    PAGE = detectPage();
    log('路由变化 ->', location.pathname, 'PAGE =', PAGE);
    clearAllTags();
    scheduleInject(150);
  }, 800);

  /* ==================== 8. 与 popup 通信 ==================== */
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || !msg.action) return;

    if (msg.action === 'refreshTags') { loadSettings(); sendResponse({ ok: true }); return; }

    if (msg.action === 'FT_STATUS') {
      sendResponse({
        ok: true,
        page: PAGE || 'other',
        path: location.pathname,
        autoPositions: AUTO_POSITIONS,
        autoOrders: AUTO_ORDERS,
        canPositions: canScrapePositions(),
        canOrders: canScrapeOrders(),
        positions: Object.keys(positionCache).length,
        orders: Object.keys(orderCache).length
      });
      return;
    }

    if (msg.action === 'FT_DUMP') {
      sendResponse({ ok: true, count: Object.keys(positionCache).length, data: positionCache });
      return;
    }

    if (msg.action === 'FT_DUMP_ORDERS') {
      sendResponse({ ok: true, count: Object.keys(orderCache).length, data: orderCache });
      return;
    }

    if (msg.action === 'FT_SYNC_ALL') {
      fullScan().then(r => sendResponse({ ok: true, count: Object.keys(positionCache).length, server: r }))
        .catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }

    if (msg.action === 'FT_SCAN_ORDERS') {
      fullScanOrders().then(r => sendResponse({ ok: true, count: Object.keys(orderCache).length, server: r }))
        .catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }
  });

  initGlobalPopover();
  loadSettings();
  console.log(LOG_PREFIX, `Content Script v5 就绪（PAGE=${PAGE}，三个自动开关默认关闭）`);
})();