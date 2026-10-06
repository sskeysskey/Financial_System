/* ============================================================================
 * Firstrade 快速交易层  ft_trade.js  v4      /app/watchlist + /app/positions
 *   点击股票代码 → 弹出交易层 → 自动驱动页面底部「交易」快速下单面板
 *   v4：
 *     ★ 修复「加仓时 没有输入代号」：旧版 symbolConfirmed 只看输入框文字（脚本自己填的，永远为真）
 *       → 现在：等联想列表稳定（搜索结果优先于「最近搜寻」）→ 点选 →
 *         严格校验「输入框代码 + 面板出现公司名/报价 + 公司名与联想项一致」→ 失败改键盘选择 → 重试
 *     ★ 列表读不到现价时，改用交易面板报价换算股数（远程交易更稳）
 *     ★ 预演模式也做下单前复核
 *   下单模式（storage.ftTradeMode）：dry 预演 / confirm 下单前确认 / live 实盘
 * ==========================================================================*/
(() => {
  if (window.__FT_TRADE_V4__) return;
  window.__FT_TRADE_V4__ = true;

  const LOG = '[FT-TRADE]';
  const BUY_GROUPS = ['买', '买买', '买买买'];
  const SELL_GROUPS = ['卖卖卖'];
  const PROTECTED = ['Earning', 'Wrong'];
  const HIDDEN_GROUPS = ['temp'];
  const ROW_EXCLUDE = '.ag-floating-top, .ag-floating-bottom, #app-quote-bar, header, #app-header';
  const MODES = ['dry', 'confirm', 'live'];
  const MODE_TXT = { dry: '🧪 预演', confirm: '✋ 下单前确认', live: '⚡ 实盘' };
  const PAGE_TXT = { watchlist: '自选股页', positions: '持仓页' };
  const CONFIRM_TIMEOUT = 120000;
  const MAX_BUY_AMOUNT = 50000;
  const MAX_SHARES = 100000;
  const POS_STALE_H = 20;
  const PRICE_DRIFT_WARN = 0.03;
  const FRACTION_MSG = '该持仓含碎股（小数股），网页端只能卖整数股：请到 Firstrade 手机 App 卖出';
  const RECENT_RE = /最近搜寻|最近搜索|最近查询|搜寻记录|搜索记录|Recent/i;

  const S = { enabled: true, mode: 'dry', removeAfter: true, presets: [1000, 2000, 3000], debug: false };
  let running = false;
  let abortFlag = false;
  let confirmWaiter = null;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const log = (...a) => { if (S.debug) console.log(LOG, ...a); };
  const pageKind = () => {
    const p = location.pathname || '';
    if (/\/watchlist/i.test(p)) return 'watchlist';
    if (/\/positions?(\/|$)/i.test(p)) return 'positions';
    return '';
  };
  const isWatchlistPage = () => pageKind() === 'watchlist';
  const isTradePage = () => !!pageKind();
  const api = () => window.__FT_WL_API__ || null;
  const toast = (t, ms) => { try { (window.__FT_TOAST__ || console.log)(t, ms); } catch (e) { } };
  const normKey = (s) => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const normName = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]/g, '');
  const normGroup = (s) => String(s || '').replace(/[（(][^）)]*[）)]\s*$/g, '').replace(/\s+/g, '').toUpperCase();
  const cleanGroupName = (s) => String(s || '').replace(/\u00a0/g, ' ').replace(/[（(]\s*\d+\s*[）)]\s*$/, '').trim();
  const inList = (g, list) => list.some(x => normGroup(x) === normGroup(g));
  const $id = (id) => document.getElementById(id);
  const parseNum = (v) => parseFloat(String(v === undefined || v === null ? '' : v).replace(/[,$\s]/g, ''));
  const isWhole = (n) => Number.isFinite(n) && n > 0 && Math.abs(n - Math.round(n)) < 1e-6;
  const fmtPx = (n) => Number.isFinite(n) ? (n >= 1 ? n.toFixed(2) : n.toFixed(4)) : '-';
  const esc = (s) => String(s === undefined || s === null ? '' : s)
    .replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function isVisible(el) {
    if (!el) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    if (st.display === 'contents') return true;
    const r = el.getBoundingClientRect();
    return !!(r.width || r.height);
  }
  function cleanText(el) {
    const t = (el && (el.innerText || el.textContent)) || '';
    return t.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  }
  async function waitFor(fn, timeout = 4000, interval = 100) {
    const t0 = Date.now();
    for (; ;) {
      let v = null;
      try { v = fn(); } catch (e) { v = null; }
      if (v) return v;
      if (Date.now() - t0 > timeout) return null;
      await sleep(interval);
    }
  }
  function bg(msg) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (chrome.runtime.lastError) { resolve({ ok: false, error: chrome.runtime.lastError.message }); return; }
          resolve(resp || { ok: false, error: 'no response' });
        });
      } catch (e) { resolve({ ok: false, error: String(e) }); }
    });
  }
  function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, 'value') ||
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    if (desc && desc.set) desc.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function sendKey(el, key, keyCode) {
    const opt = { bubbles: true, cancelable: true, key, code: key, keyCode, which: keyCode };
    el.dispatchEvent(new KeyboardEvent('keydown', opt));
    el.dispatchEvent(new KeyboardEvent('keyup', opt));
  }
  function fireMouseSeq(el) {
    const r = el.getBoundingClientRect();
    const opt = {
      bubbles: true, cancelable: true, view: window,
      clientX: r.left + Math.max(2, r.width / 2), clientY: r.top + Math.max(2, r.height / 2),
      button: 0, buttons: 1, pointerId: 1, isPrimary: true, pointerType: 'mouse'
    };
    try { el.dispatchEvent(new PointerEvent('pointerover', opt)); } catch (e) { }
    try { el.dispatchEvent(new PointerEvent('pointerenter', opt)); } catch (e) { }
    el.dispatchEvent(new MouseEvent('mouseover', opt));
    el.dispatchEvent(new MouseEvent('mousemove', opt));
    try { el.dispatchEvent(new PointerEvent('pointerdown', opt)); } catch (e) { }
    el.dispatchEvent(new MouseEvent('mousedown', opt));
    try { el.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, opt, { buttons: 0 }))); } catch (e) { }
    el.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, opt, { buttons: 0 })));
    el.dispatchEvent(new MouseEvent('click', Object.assign({}, opt, { buttons: 0 })));
  }
  function symbolFromRowId(rowId) {
    if (!rowId) return '';
    const raw = String(rowId).split('|')[0].trim().toUpperCase();
    return /^[A-Z][A-Z0-9.\-]{0,9}$/.test(raw) ? raw : '';
  }
  function candidateForms(sym) {
    const s = String(sym).trim().toUpperCase();
    const out = [];
    if (s.includes('-')) out.push(s.replace(/-/g, '.'));
    out.push(s);
    if (s.includes('.')) out.push(s.replace(/\./g, '-'));
    return Array.from(new Set(out));
  }

  /* ==========================================================================
   *              网页实时行情（col-id="last" / "quantity"）
   * ========================================================================*/
  function readRow(sym) {
    const a = api();
    const q = a && a.rowQuote ? a.rowQuote(sym) : null;
    if (!q) return null;
    return {
      symbol: q.symbol, price: q.price > 0 ? q.price : null, last: q.last || '',
      qtyStr: q.quantity > 0 ? String(q.quantity) : '', change_pct: q.change_pct || ''
    };
  }

  async function livePrice(sym, ctx, allowSwitch, say) {
    const good = (q) => (q && q.price > 0) ? q : null;
    let q = good(readRow(sym));
    if (q) return q;
    const a = api();
    if (a && a.findRowQuote) {
      if (say) say('↳ 当前视图未渲染该行，滚动查找…');
      const r = await a.findRowQuote(sym, true);
      q = good(r ? { symbol: r.symbol, price: r.price, last: r.last } : null);
      if (q) return q;
    }
    if (allowSwitch && isWatchlistPage() && a && ctx) {
      const cur = normGroup(a.groupName());
      for (const g of allGroups(ctx)) {
        if (normGroup(g) === cur) continue;
        if (say) say(`↳ 切到「${g}」读取 ${sym} 现价…`);
        const sr = await a.switchGroup(g);
        if (!sr.ok) continue;
        await a.waitGridSettled(4000);
        const r = await a.findRowQuote(sym, true);
        q = good(r ? { symbol: r.symbol, price: r.price, last: r.last } : null);
        if (q) return q;
      }
    }
    return null;
  }

  /* ==========================================================================
   *                  页面「快速交易」面板 DOM 驱动
   * ========================================================================*/
  const NEW_ORDER_RE = /^(新订单|新建订单|再下一单|继续交易|继续下单|New Order|Place Another Order)$/i;

  function formReady() { const i = $id('quick-trade-symbol-search'); return !!(i && isVisible(i)); }

  function tradeRoot() {
    const inp = $id('quick-trade-symbol-search');
    if (inp && isVisible(inp)) {
      const r = inp.closest('[data-popover-content]') || inp.closest('div.fixed') || inp.closest('article');
      if (r) return r;
    }
    const hs = Array.from(document.querySelectorAll('article > header[data-drag-handle]'))
      .filter(h => isVisible(h) && !h.closest('#ft-trade-layer'));
    for (const h of hs) {
      const root = h.closest('[data-popover-content]') || h.closest('div.fixed') || h.closest('article');
      if (root && /订单|下单|交易|股票/.test(cleanText(root))) return root;
    }
    return null;
  }
  function tradeButton() {
    const b = $id('quick-trade-quote-bar');
    if (b && isVisible(b)) return b;
    const bar = $id('app-quote-bar');
    if (!bar) return null;
    return Array.from(bar.querySelectorAll('button')).find(x => isVisible(x) && cleanText(x) === '交易') || null;
  }
  async function closeTradePanel() {
    for (let i = 0; i < 2 && tradeRoot(); i++) {
      const root = tradeRoot();
      const hdr = root.querySelector('header');
      const btns = hdr ? Array.from(hdr.querySelectorAll('button')).filter(isVisible) : [];
      const x = btns.find(b => /关闭|close|×|✕/i.test((b.getAttribute('aria-label') || '') + (b.title || '') + cleanText(b)));
      if (x) fireMouseSeq(x);
      else { sendKey(root, 'Escape', 27); sendKey(document.body, 'Escape', 27); }
      await waitFor(() => !tradeRoot(), 1500, 100);
    }
    if (tradeRoot()) {
      const b = tradeButton();
      if (b) { fireMouseSeq(b); await waitFor(() => !tradeRoot(), 1500, 100); }
    }
    return !tradeRoot();
  }
  async function openPanel() {
    if (formReady()) return { ok: true, reused: true };
    const r0 = tradeRoot();
    if (r0) {
      const nb = Array.from(r0.querySelectorAll('button')).find(b => isVisible(b) && NEW_ORDER_RE.test(cleanText(b)));
      if (nb) {
        fireMouseSeq(nb);
        if (await waitFor(formReady, 3000, 120)) { await sleep(300); return { ok: true, renewed: true }; }
      }
      await closeTradePanel();
      await sleep(300);
    }
    for (let i = 0; i < 2; i++) {
      const b = tradeButton();
      if (!b) return { ok: false, error: '找不到页面底部报价条上的「交易」按钮 (#quick-trade-quote-bar)' };
      fireMouseSeq(b);
      if (await waitFor(formReady, 5000, 120)) { await sleep(350); return { ok: true }; }
      if (tradeRoot() && !formReady()) await closeTradePanel();
    }
    return { ok: false, error: '点击「交易」后未出现快速交易面板' };
  }
  async function ensureStocksTab() {
    const r = tradeRoot();
    if (!r) return;
    const tab = r.querySelector('[role="tab"][data-value="stocks"], [data-tabs-trigger][data-value="stocks"], button[data-value="stocks"]');
    if (tab && tab.getAttribute('aria-selected') !== 'true' && tab.getAttribute('data-state') !== 'active') {
      fireMouseSeq(tab);
      await sleep(400);
    }
  }

  /* ==========================================================================
   *        ★ v4 代码选择：稳定联想 → 点选 → 严格确认（公司名 + 报价）
   * ========================================================================*/
  function comboItems() {
    const sel = '[data-combobox-content] [data-combobox-item], [role="listbox"] [role="option"], [data-combobox-item]';
    return Array.from(document.querySelectorAll(sel)).filter(el => isVisible(el) &&
      !el.closest('[data-command-root]') && !el.closest('[data-select-content]') && !el.closest('#ft-trade-layer'));
  }
  function itemSym(el) {
    const v = el.getAttribute('data-label') || el.getAttribute('data-value');
    if (v && /[A-Za-z]/.test(v)) return String(v).trim().toUpperCase();
    const b = el.querySelector('.font-semibold, strong, b');
    if (b) return cleanText(b).toUpperCase();
    return (cleanText(el).split(/\s+/)[0] || '').toUpperCase();
  }
  function itemName(el) {
    const t = el.querySelector('.truncate');
    if (t) return cleanText(t);
    const sp = el.querySelectorAll('span');
    return sp.length > 1 ? cleanText(sp[1]) : '';
  }
  function itemMatches(el, k) {
    if (normKey(el.getAttribute('data-label')) === k) return true;
    if (normKey(el.getAttribute('data-value')) === k) return true;
    const b = el.querySelector('.font-semibold, strong, b');
    if (b && normKey(cleanText(b)) === k) return true;
    return normKey(cleanText(el).split(/\s+/)[0] || '') === k;
  }
  /* 该联想项是否位于「最近搜寻」分区（已持仓/搜过的股票几乎都在这里，且会被真正的搜索结果替换掉） */
  function isRecentItem(el) {
    const box = el.closest('[data-combobox-content], [role="listbox"]') ||
      (el.parentElement && el.parentElement.parentElement);
    if (!box) return false;
    const heads = Array.from(box.querySelectorAll('span, div, p'))
      .filter(x => x.children.length === 0 && RECENT_RE.test(cleanText(x)));
    return heads.some(h => !!(h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
  }
  /* 交易面板里的「公司名 + 现价」信息块（选中代码后才会出现） */
  function quoteInfo() {
    const root = tradeRoot();
    if (!root) return null;
    const boxes = Array.from(root.querySelectorAll('div.tabular-nums')).filter(isVisible);
    for (const box of boxes) {
      const pxEl = box.querySelector('span.text-xl');
      const nameEl = box.querySelector('span.truncate');
      if (!pxEl && !nameEl) continue;
      const px = pxEl ? parseNum(cleanText(pxEl)) : NaN;
      const name = nameEl ? cleanText(nameEl) : '';
      if (!name && !(px > 0)) continue;
      return { name, price: px > 0 ? px : NaN };
    }
    return null;
  }
  function inputSymKey() {
    const i = $id('quick-trade-symbol-search');
    return i ? normKey(String(i.value || '').trim().split(/\s+/)[0]) : '';
  }
  function selectionState(k, wantName) {
    const i = $id('quick-trade-symbol-search');
    if (!i || !isVisible(i)) return { ok: false, why: '代码输入框不见了' };
    if (inputSymKey() !== k) return { ok: false, why: `输入框内容是「${i.value || '空'}」` };
    const q = quoteInfo();
    if (!q) return { ok: false, why: '面板没有出现该股票的公司名/报价（联想项未真正选中）' };
    if (wantName && q.name && normName(wantName) !== normName(q.name)) {
      return { ok: false, why: `面板显示「${q.name}」≠ 联想项「${wantName}」（可能点到了别的股票）` };
    }
    return { ok: true, quote: q };
  }
  async function waitSelection(k, wantName, timeout) {
    const t0 = Date.now();
    let st = selectionState(k, wantName);
    while (!st.ok && Date.now() - t0 < timeout) {
      await sleep(150);
      st = selectionState(k, wantName);
    }
    return st;
  }
  /* 等联想列表稳定：搜索结果稳定 ≥ 3 次采样即可；只在「最近搜寻」里命中则多等一会儿给真正结果替换 */
  async function waitMatch(k, timeout) {
    const t0 = Date.now();
    let lastSig = '', stable = 0;
    while (Date.now() - t0 < timeout) {
      const items = comboItems();
      const sig = items.map(itemSym).join(',');
      if (sig && sig === lastSig) stable++; else { stable = 0; lastSig = sig; }
      const hits = items.filter(el => itemMatches(el, k));
      if (hits.length && stable >= 2) {
        const fresh = hits.find(el => !isRecentItem(el));
        if (fresh) return fresh;
        if (stable >= 6 || Date.now() - t0 > 2500) return hits[0];
      }
      await sleep(120);
    }
    const items = comboItems().filter(el => itemMatches(el, k));
    return items.find(el => !isRecentItem(el)) || items[0] || null;
  }
  async function keyboardPick(inp, k) {
    inp.focus();
    for (let i = 0; i < 12; i++) {
      const items = comboItems();
      const ad = inp.getAttribute('aria-activedescendant');
      const hl = items.find(el => el.hasAttribute('data-highlighted') || el.getAttribute('aria-selected') === 'true' ||
        (ad && (el.id === ad || (el.closest('[id]') && el.closest('[id]').id === ad))));
      if (hl && itemMatches(hl, k)) { sendKey(inp, 'Enter', 13); return true; }
      sendKey(inp, 'ArrowDown', 40);
      await sleep(130);
    }
    return false;
  }
  async function pickSymbol(sym, say) {
    let lastErr = '';
    for (const f of candidateForms(sym)) {
      const k = normKey(f);
      for (let attempt = 0; attempt < 3; attempt++) {
        const inp = $id('quick-trade-symbol-search');
        if (!inp || !isVisible(inp)) return { ok: false, error: '找不到交易面板的代码输入框' };
        inp.focus();
        setNativeValue(inp, '');
        await sleep(200);
        await waitFor(() => !quoteInfo(), 1200, 100);            // 清空后旧报价块一般会消失（不消失也不阻塞）
        setNativeValue(inp, f);
        inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: f.slice(-1) }));

        const hit = await waitMatch(k, 7000);
        if (!hit) { lastErr = `联想列表里没有精确匹配 ${f}`; break; }   // 换下一种写法（BRK.B / BRK-B）
        const wantName = itemName(hit);
        if (say) say(`↳ 联想命中 ${itemSym(hit)}${wantName ? '（' + wantName + '）' : ''}${isRecentItem(hit) ? '［最近搜寻］' : ''}`);
        if (!hit.isConnected) { lastErr = '联想项在点击前被刷新'; await sleep(400); continue; }
        try { hit.scrollIntoView({ block: 'nearest' }); } catch (e) { }
        fireMouseSeq(hit);
        let st = await waitSelection(k, wantName, 4000);
        if (!st.ok) {
          if (say) say(`↳ 鼠标选择未生效（${st.why}），改用键盘选择…`);
          const i2 = $id('quick-trade-symbol-search');
          if (i2) {
            if (!comboItems().some(el => itemMatches(el, k))) {
              setNativeValue(i2, f);
              await waitMatch(k, 4000);
            }
            if (await keyboardPick(i2, k)) st = await waitSelection(k, wantName, 4000);
          }
        }
        if (st.ok) {
          await sleep(500);
          const again = selectionState(k, wantName);               // 二次确认：防止页面随后又把代码清掉
          if (again.ok) {
            return { ok: true, form: f, name: again.quote.name || wantName, price: again.quote.price > 0 ? again.quote.price : null };
          }
          st = again;
        }
        lastErr = `选择 ${f} 未生效：${st.why}`;
        if (say) say(`↳ ${lastErr}（第 ${attempt + 1}/3 次）`);
        await sleep(600 + attempt * 600);
      }
    }
    return { ok: false, error: lastErr || '无法选择代码' };
  }

  /* ---------- 下拉框 ---------- */
  function openSelectItems() {
    return Array.from(document.querySelectorAll('[data-select-content] [data-select-item], [role="listbox"] [data-select-item]'))
      .filter(isVisible);
  }
  const trig = (id) => { const r = tradeRoot(); return (r && r.querySelector('#' + id)) || null; };
  async function chooseSelect(id, label) {
    const t = trig(id);
    if (!t) return { ok: false, missing: true, error: `找不到下拉框 #${id}` };
    if (cleanText(t) === label) return { ok: true, already: true };
    if (t.disabled) return { ok: false, error: `下拉框 #${id} 不可用（当前「${cleanText(t)}」）` };
    for (let a = 0; a < 3; a++) {
      fireMouseSeq(trig(id) || t);
      const items = await waitFor(() => { const it = openSelectItems(); return it.length ? it : null; }, 3000, 100);
      if (!items) { sendKey(t, 'Escape', 27); await sleep(300); continue; }
      const hit = items.find(i => (i.getAttribute('data-label') || '').trim() === label) ||
        items.find(i => cleanText(i) === label);
      if (!hit) {
        const names = items.map(i => i.getAttribute('data-label') || cleanText(i));
        sendKey(t, 'Escape', 27);
        return { ok: false, error: `下拉框里没有「${label}」（可选：${names.join(' / ')}）` };
      }
      fireMouseSeq(hit);
      const ok = await waitFor(() => { const x = trig(id); return x && cleanText(x) === label; }, 3000, 100);
      if (ok) { await sleep(250); return { ok: true }; }
      await sleep(400);
    }
    return { ok: false, error: `无法把 #${id} 设为「${label}」` };
  }

  /* ---------- 股数 / 金额 ---------- */
  function qtyFieldset() {
    const r = tradeRoot();
    if (!r) return null;
    const lb = r.querySelector('label[for="quick-trade-form-quantity-amount"]');
    return lb ? lb.closest('fieldset') : null;
  }
  function qtyInput() {
    const fs = qtyFieldset();
    if (fs) {
      const i = Array.from(fs.querySelectorAll('input')).find(isVisible);
      if (i) return i;
    }
    const byId = $id('quick-trade-form-quantity-amount');
    return byId && isVisible(byId) ? byId : null;
  }
  const qtyTypeBtn = () => { const r = tradeRoot(); return r && r.querySelector('#quick-trade-form-quantity-type'); };
  function qtyMode() {
    const fs = qtyFieldset();
    if (fs && Array.from(fs.querySelectorAll('span')).some(s => cleanText(s) === '$')) return '金额';
    if (fs && fs.querySelector('#quick-trade-form-quantity-amount')) return '股数';
    const b = qtyTypeBtn();
    const t = b ? (b.getAttribute('title') || '').trim() : '';
    return (t === '金额' || t === '股数') ? t : '';
  }
  async function setQtyMode(want) {
    for (let a = 0; a < 3; a++) {
      if (qtyMode() === want) return { ok: true };
      const b = qtyTypeBtn();
      if (!b) return { ok: false, error: '找不到「股数/金额」切换按钮 (#quick-trade-form-quantity-type)' };
      fireMouseSeq(b);
      await waitFor(() => qtyMode() === want, 1500, 100);
    }
    return qtyMode() === want ? { ok: true } : { ok: false, error: `无法切换到「${want}」（当前 ${qtyMode() || '未知'}）` };
  }
  function qtyMatches(val) {
    const i = qtyInput();
    return !!i && Math.abs(parseFloat(i.value) - parseNum(val)) < 1e-6;
  }
  async function fillQty(val) {
    const i = await waitFor(qtyInput, 2500, 100);
    if (!i) return { ok: false, error: '找不到数量输入框' };
    i.focus();
    setNativeValue(i, '');
    await sleep(60);
    setNativeValue(i, String(val));
    i.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: '0' }));
    i.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
    i.dispatchEvent(new Event('blur'));
    await sleep(250);
    if (!qtyMatches(val)) { const now = qtyInput(); return { ok: false, error: `写入失败（期望 ${val}，实际 ${now ? now.value : '-'}）` }; }
    return { ok: true };
  }

  /* ---------- 下单 & 结果识别 ---------- */
  const SENT_RE = /订单已送出|已送出|订单号码|委托号|submitted|order placed|has been placed/i;
  const OK_RE = /成功|已提交|已下单|已接收|已受理|已委托|success|accepted|received/i;
  const ERR_RE = /失败|错误|不足|拒绝|无效|不允许|无法|超出|没有输入|请输入|error|fail|insufficient|reject|invalid|not allowed|exceed|required/i;
  const CONFIRM_RE = /^(确认|确定|确认下单|确认交易|确认订单|提交|提交订单|发送订单|送出|继续|Confirm|Submit|Place Order|Send Order|Continue)$/i;

  function submitButton() {
    const r = tradeRoot();
    if (!r) return null;
    const f = r.querySelector('footer') || r;
    return Array.from(f.querySelectorAll('button')).find(b => isVisible(b) && cleanText(b) === '下单') || null;
  }
  const notifText = () => { const s = document.querySelector('section[aria-label^="Notifications"]'); return s ? cleanText(s) : ''; };
  function alertList() {
    const r = tradeRoot();
    if (!r) return [];
    return Array.from(r.querySelectorAll('[role="alert"]')).filter(isVisible)
      .map(el => ({ el, t: cleanText(el), cls: String(el.className || '') }));
  }
  const orderNoOf = (t) => ((String(t).match(/订单(?:号码|编号|号)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9\-]*)/) || [])[1] || '');
  function panelErrorText() {
    const r = tradeRoot();
    if (!r) return '';
    const errs = Array.from(r.querySelectorAll('[role="alert"], [aria-invalid="true"], [data-form-error], .text-error'))
      .filter(isVisible).map(cleanText).filter(Boolean);
    return errs.join('；').slice(0, 160) || '无明确提示';
  }
  function confirmCandidates(exclude) {
    const scopes = [tradeRoot()].concat(Array.from(document.querySelectorAll(
      '[role="dialog"], [role="alertdialog"], [data-dialog-content], [data-alert-dialog-content]')))
      .filter(el => el && isVisible(el) && !el.closest('#ft-trade-layer'));
    const out = [];
    scopes.forEach(s => s.querySelectorAll('button').forEach(b => {
      if (b !== exclude && isVisible(b) && !b.disabled && CONFIRM_RE.test(cleanText(b))) out.push(b);
    }));
    return out;
  }
  const newWords = (now, before) => now.split(' ').filter(w => w && !before.includes(w)).join(' ');

  function readOutcome(before, n0, sent0) {
    for (const a of alertList()) {
      if (!a.t || before.has(a.t)) continue;
      if (/success/i.test(a.cls) || SENT_RE.test(a.t)) {
        return { status: 'ok', message: '下单成功：' + a.t.slice(0, 120), orderNo: orderNoOf(a.t) };
      }
      if (/error|danger|destructive|fail/i.test(a.cls) || ERR_RE.test(a.t)) {
        return { status: 'error', message: '下单失败：' + a.t.slice(0, 160) };
      }
    }
    const n1 = notifText();
    const nNew = n1 !== n0 ? newWords(n1, n0) : '';
    if (nNew) {
      if (ERR_RE.test(nNew)) return { status: 'error', message: '下单失败：' + nNew.slice(0, 160) };
      if (SENT_RE.test(nNew) || OK_RE.test(nNew)) return { status: 'ok', message: '下单成功：' + nNew.slice(0, 120), orderNo: orderNoOf(nNew) };
    }
    const r = tradeRoot();
    if (r && !sent0) {
      const t = cleanText(r);
      if (/订单已送出|您的订单已送出/.test(t)) return { status: 'ok', message: '下单成功：您的订单已送出', orderNo: orderNoOf(t) };
    }
    return null;
  }

  async function submitAndWatch(say) {
    const btn = await waitFor(() => {
      const b = submitButton();
      return b && !b.disabled && b.getAttribute('aria-disabled') !== 'true' ? b : null;
    }, 5000, 120);
    if (!btn) {
      const b = submitButton();
      return { status: 'error', clicked: false, message: b ? `「下单」按钮不可点（表单校验未通过：${panelErrorText()}）` : '找不到「下单」按钮' };
    }
    const before = new Set(alertList().map(a => a.t));
    const n0 = notifText();
    const sent0 = /订单已送出/.test(cleanText(tradeRoot()));
    const clicked = new Set([btn]);
    fireMouseSeq(btn);                               // ★ 「下单」只点这一次
    let confirms = 0;
    const t0 = Date.now();
    while (Date.now() - t0 < 25000) {
      await sleep(250);
      const out = readOutcome(before, n0, sent0);
      if (out) return Object.assign({ clicked: true }, out);
      if (confirms < 2) {
        const c = confirmCandidates(btn).filter(b => !clicked.has(b));
        if (c.length) {
          clicked.add(c[0]); confirms++;
          if (say) say(`↳ 出现确认按钮「${cleanText(c[0])}」，自动确认`);
          fireMouseSeq(c[0]);
          await sleep(400);
          continue;
        }
      }
      if (!tradeRoot()) return { status: 'unknown', clicked: true, message: '交易面板在出现结果前关闭（无法确认是否成交，不会移出分组，请到订单页核对）' };
    }
    return { status: 'unknown', clicked: true, message: '25 秒内未看到成功/失败提示（不会移出分组，请到订单页核对）' };
  }

  function verifyForm(pk, txLabel, mode, val) {
    if (!formReady()) return { ok: false, error: '交易表单已不在（可能已手动下单或面板被关闭）' };
    const st = selectionState(normKey(pk.form), pk.name);
    if (!st.ok) return { ok: false, error: `代码未确认为 ${pk.form}：${st.why}` };
    const t = trig('quick-trade-form-transaction');
    if (!t || cleanText(t) !== txLabel) return { ok: false, error: `交易类型不是「${txLabel}」` };
    if (qtyMode() !== mode) return { ok: false, error: `数量方式不是「${mode}」` };
    if (!qtyMatches(val)) return { ok: false, error: `数量不是 ${val}` };
    const ot = trig('quick-trade-form-order-type');
    if (ot && cleanText(ot) !== '市价') return { ok: false, error: `订单类型不是「市价」（当前 ${cleanText(ot)}）` };
    return { ok: true };
  }

  /* ---------- 成交后移出分组 ---------- */
  async function removeFromGroups(sym, groups, say) {
    const a = api();
    const origin = a.groupName();
    const removed = [], failed = [];
    a.clearStopFlags();
    for (const g of groups) {
      try {
        if (normGroup(a.groupName()) !== normGroup(g)) {
          if (say) say(`↳ 切换到「${g}」…`);
          const sr = await a.switchGroup(g);
          if (!sr.ok) { failed.push({ group: g, error: sr.error }); if (say) say(`↳ ❌ 切换「${g}」失败：${sr.error}`); continue; }
          await a.waitGridSettled(4000);
        }
        const r = await a.deleteSymbol(sym);
        if (r.status === 'removed' || r.status === 'missing') {
          removed.push(g);
          if (say) say(`↳ 已从「${g}」移除 ${sym}${r.status === 'missing' ? '（本就不在）' : ''}`);
          try { window.__FT_WL_MEMBER__ && window.__FT_WL_MEMBER__.event(g, sym, 'remove', 'trade_remove'); } catch (e) { }
        } else {
          failed.push({ group: g, error: r.error || r.status });
          if (say) say(`↳ ❌ 从「${g}」移除失败：${r.error || r.status}`);
        }
      } catch (e) { failed.push({ group: g, error: String((e && e.message) || e) }); }
    }
    try {
      if (origin && normGroup(a.groupName()) !== normGroup(origin)) await a.switchGroup(origin);
    } catch (e) { }
    return { removed, failed };
  }

  async function enqueueRemoval(sym, groups, say) {
    const queued = [], failed = [];
    for (const g of groups) {
      const r = await bg({ action: 'FT_WL_ENQUEUE', task: 'remove', symbol: sym, group: g });
      if (r && r.ok) {
        queued.push(g);
        const tip = r.data && r.data.watchlistTab ? '自选股页代理会自动执行' : '⚠ 当前没有打开 /app/watchlist，打开后 1 小时内会自动执行';
        if (say) say(`↳ 已排队：从「${g}」移出 ${sym}（${tip}）`);
      } else {
        failed.push({ group: g, error: (r && r.error) || '排队失败' });
        if (say) say(`↳ ❌ 排队移出「${g}」失败：${(r && r.error) || ''}`);
      }
    }
    return { queued, failed };
  }

  function waitUserConfirm(ms) {
    return new Promise((resolve) => {
      const t = setTimeout(() => { if (confirmWaiter) confirmWaiter(false); }, ms);
      confirmWaiter = (v) => { confirmWaiter = null; clearTimeout(t); resolve(!!v); render(); };
      render();
    });
  }

  /* ---------- 主流程（一律按股数） ---------- */
  async function execute(opts) {
    const o = opts || {};
    const sym = String(o.symbol || '').trim().toUpperCase();
    const side = o.side === 'sell' ? 'sell' : (o.side === 'buy' ? 'buy' : '');
    let qty = (o.qty === undefined || o.qty === null || o.qty === '') ? NaN : parseNum(o.qty);
    const budget = (side === 'buy' && !(qty > 0)) ? parseNum(o.amount) : NaN;
    const groups = (Array.isArray(o.removeGroups) ? o.removeGroups : [])
      .filter(g => !inList(g, PROTECTED) && !inList(g, HIDDEN_GROUPS));
    const mode = o.dry ? 'dry' : (MODES.includes(S.mode) ? S.mode : 'dry');
    const page = pageKind();
    const say = (t) => { log(t); if (typeof o.onLog === 'function') { try { o.onLog(t); } catch (e) { } } };
    const res = {
      ok: false, symbol: sym, side, amount: budget > 0 ? budget : null, qty: null, price: null,
      mode, page, status: '', message: '', orderNo: '', submitted: false,
      removed: [], removeFailed: [], removeQueued: [], source: o.source || 'layer'
    };
    const fail = (m, st) => Object.assign(res, { message: m, error: m, status: st || 'error' });

    if (running) return fail('已有一笔交易在执行中');
    const a = api();
    if (!page) return fail('请在 /app/watchlist 或 /app/positions 页面使用');
    if (!a) return fail('watchlist.js 未就绪，请刷新页面');
    if (a.isBusy()) return fail('自选股同步/行情抓取进行中，请稍后再交易');
    if (!sym || !side) return fail('缺少代码或买卖方向');
    if (side === 'sell' && !(qty > 0)) return fail('卖出股数必须大于 0');
    if (side === 'buy' && !(qty > 0) && !(budget > 0)) return fail('买入金额必须大于 0');
    if (budget > MAX_BUY_AMOUNT) return fail(`单笔买入金额超过上限 $${MAX_BUY_AMOUNT}`);
    if (qty > 0 && !isWhole(qty)) return fail('股数必须是整数（网页端不支持碎股；碎股请到手机 App 操作）', 'fractional');

    running = true; abortFlag = false;
    try { a.setTradeBusy(true); } catch (e) { }
    const startGroup = isWatchlistPage() ? a.groupName() : '';
    const chk = () => { if (abortFlag) throw new Error('已取消（尚未点击「下单」）'); };
    const must = (r, step) => { if (!r || !r.ok) throw new Error(`${step}：${(r && r.error) || '失败'}`); return r; };
    const sizeFromPrice = (px, how) => {
      res.price = px;
      qty = Math.round(budget / px);
      say(`${how} $${fmtPx(px)}：$${budget} ÷ ${fmtPx(px)} = ${(budget / px).toFixed(2)} → 四舍五入 ${qty} 股（约 $${(qty * px).toFixed(2)}）`);
      if (qty < 1) throw new Error(`$${budget} 不足 1 股（现价 $${fmtPx(px)}）`);
      if (qty * px > MAX_BUY_AMOUNT * 1.05) throw new Error(`换算后金额 $${(qty * px).toFixed(0)} 超过上限 $${MAX_BUY_AMOUNT}`);
      const prev = o.ctx && o.ctx.price;
      if (prev > 0 && Math.abs(px - prev) / prev > PRICE_DRIFT_WARN) {
        say(`⚠ 现价较打开交易层时变动 ${(((px - prev) / prev) * 100).toFixed(1)}%（以最新价为准）`);
      }
    };
    try {
      a.clearStopFlags(); a.cleanNavSearch();
      say(`模式：${MODE_TXT[mode]}｜页面：${PAGE_TXT[page]}`);

      /* ⓪ 金额 → 股数：优先用列表实时价；读不到则选好代码后用面板报价 */
      let deferred = false;
      if (!(qty > 0)) {
        say('⓪ 读取网页最新价…');
        const q = await livePrice(sym, o.ctx, !!o.allowSwitch, say);
        if (q) sizeFromPrice(q.price, '列表现价');
        else { deferred = true; say('↳ 列表里读不到现价：先选好代码，再用交易面板报价换算股数'); }
        chk();
      } else if (side === 'buy') {
        const q = readRow(sym);
        if (q && q.price) res.price = q.price;
      }
      const txLabel = side === 'buy' ? '买进' : '卖出';

      say('① 打开快速交易面板…'); must(await openPanel(), '打开交易面板'); chk();
      await ensureStocksTab();
      say(`② 选择代码 ${sym}…`);
      const pk = must(await pickSymbol(sym, say), '选择代码'); chk();
      say(`↳ ✔ 面板已确认：${pk.form}${pk.name ? '｜' + pk.name : ''}${pk.price ? '｜$' + fmtPx(pk.price) : ''}`);
      if (deferred) {
        const qp = pk.price || await waitFor(() => { const q = quoteInfo(); return q && q.price > 0 ? q.price : null; }, 5000, 150);
        if (!qp) throw new Error('交易面板也读不到报价：为防股数算错已中止（未点击「下单」）');
        sizeFromPrice(qp, '面板报价');
        chk();
      } else if (res.price && pk.price && Math.abs(pk.price - res.price) / res.price > PRICE_DRIFT_WARN) {
        say(`⚠ 面板报价 $${fmtPx(pk.price)} 与列表现价 $${fmtPx(res.price)} 相差超过 ${PRICE_DRIFT_WARN * 100}%，请核对`);
      }
      if (!(qty > 0)) throw new Error('股数无效');
      if (qty > MAX_SHARES) throw new Error(`股数 ${qty} 超过单笔上限 ${MAX_SHARES}`);
      qty = Math.round(qty);
      res.qty = qty;
      const valStr = String(qty);

      say(`③ 交易类型 → ${txLabel}`); must(await chooseSelect('quick-trade-form-transaction', txLabel), '交易类型'); chk();
      await sleep(300);
      say('④ 数量方式 → 股数'); must(await setQtyMode('股数'), '数量方式'); chk();
      say(`⑤ 填写 ${valStr} 股`); must(await fillQty(valStr), '填写股数'); chk();
      if (await waitFor(() => trig('quick-trade-form-order-type'), 1500, 100)) {
        say('⑥ 订单类型 → 市价'); must(await chooseSelect('quick-trade-form-order-type', '市价'), '订单类型');
      } else say('⑥ 未出现订单类型下拉框，跳过');
      await sleep(250);
      if (!qtyMatches(valStr)) { say('股数框被重置，重新填写…'); must(await fillQty(valStr), '重新填写股数'); }
      chk();

      const notional = res.price ? `，约 $${(qty * res.price).toFixed(2)}` : '';
      if (mode === 'dry') {
        const vf0 = verifyForm(pk, txLabel, '股数', valStr);
        if (!vf0.ok) throw new Error('预演复核失败：' + vf0.error);
        res.ok = true; res.status = 'dry';
        res.message = `🧪 预演完成：${txLabel} ${qty} 股（市价${notional}），表单复核通过，未点击「下单」`;
        say(res.message);
        return res;
      }
      if (mode === 'confirm') {
        say(`⏸ 表单已填好（${txLabel} ${qty} 股${notional}）：核对后在本层点「✅ 确认下单」（120 秒内）`);
        const go = await waitUserConfirm(CONFIRM_TIMEOUT);
        if (!go) throw new Error('已取消：未点击「下单」');
      }
      chk();
      const vf = verifyForm(pk, txLabel, '股数', valStr);
      if (!vf.ok) throw new Error('下单前复核失败：' + vf.error + '（未点击「下单」）');

      say('⑦ 点击「下单」…');
      const sw = await submitAndWatch(say);
      res.submitted = !!sw.clicked;
      res.status = sw.status; res.message = sw.message; res.orderNo = sw.orderNo || '';
      if (sw.status !== 'ok') {
        res.ok = false; res.error = sw.message;
        say((sw.status === 'unknown' ? '⚠️ ' : '❌ ') + sw.message);
        return res;
      }
      res.ok = true;
      say('✅ ' + sw.message + (res.orderNo ? `（订单号 ${res.orderNo}）` : ''));
      if (groups.length) {
        say(`⑧ 从分组移除：${groups.join(' / ')}`);
        if (isWatchlistPage()) {
          await closeTradePanel();
          const rr = await removeFromGroups(sym, groups, say);
          res.removed = rr.removed; res.removeFailed = rr.failed;
        } else {
          const rq = await enqueueRemoval(sym, groups, say);
          res.removeQueued = rq.queued; res.removeFailed = rq.failed;
        }
      } else {
        say('⑧ 未勾选任何分组，保留在分组内');
      }
      /* ★ v5：实盘成交后关闭 Firstrade 自带的「订单已送出」面板（订单号已读取），不在屏幕中间留结果 */
      if (tradeRoot()) { try { await closeTradePanel(); } catch (e) { } }
    } catch (e) {
      res.ok = false;
      res.error = String((e && e.message) || e);
      if (!res.message || res.status === '') res.message = res.error;
      if (!res.status) res.status = 'error';
      say('❌ ' + res.error);
    } finally {
      try {
        if (startGroup && isWatchlistPage() && normGroup(a.groupName()) !== normGroup(startGroup)) {
          say(`↳ 切回「${cleanGroupName(startGroup)}」`);
          await a.switchGroup(startGroup);
        }
      } catch (e) { }
      running = false;
      try { a.setTradeBusy(false); } catch (e) { }
      bg({ action: 'FT_TRADE_LOG', payload: Object.assign({ ts: Date.now(), page_group: isWatchlistPage() ? cleanGroupName(a.groupName()) : '(positions)' }, res) });
    }
    return res;
  }

  /* ==========================================================================
   *                       上下文（分组归属 / 持仓 / 现价）
   * ========================================================================*/
  async function loadContext(sym, inCurrent) {
    const a = api();
    const page = pageKind();
    const current = (page === 'watchlist' && a) ? cleanGroupName(a.groupName()) : '';
    const [mem, pos] = await Promise.all([bg({ action: 'FT_SERVER_MEMBERSHIP' }), bg({ action: 'FT_SERVER_POSITIONS' })]);
    const k = normKey(sym);
    const groups = [];
    const gmap = (mem && mem.ok && mem.data && mem.data.groups) || {};
    Object.keys(gmap).forEach(g => {
      if (inList(g, HIDDEN_GROUPS)) return;
      const syms = (gmap[g] && gmap[g].symbols) || [];
      if (syms.some(s => normKey(s) === k)) groups.push(g);
    });
    let position = null, posMeta = null;
    if (pos && pos.ok && pos.data) {
      posMeta = pos.data._meta || null;
      for (const key of Object.keys(pos.data)) {
        if (key.startsWith('_')) continue;
        if (normKey(key) === k) { position = pos.data[key]; break; }
      }
    }
    const row = readRow(sym);
    return {
      symbol: sym, page, current, inCurrent: !!inCurrent, groups, position, posMeta,
      price: row && row.price > 0 ? row.price : null,
      liveQtyStr: (page === 'positions' && row && row.qtyStr) ? row.qtyStr : '',
      memOk: !!(mem && mem.ok), posOk: !!(pos && pos.ok)
    };
  }
  function allGroups(c) {
    const s = c.groups.filter(g => !inList(g, HIDDEN_GROUPS));
    if (c.inCurrent && c.current && !inList(c.current, HIDDEN_GROUPS) &&
      !s.some(g => normGroup(g) === normGroup(c.current))) s.unshift(c.current);
    return s;
  }
  const removable = (groups) => groups.filter(g => !inList(g, PROTECTED) && !inList(g, HIDDEN_GROUPS));
  function positionQtyStr(p) {
    if (!p) return '';
    const raw = String(p.quantity === undefined || p.quantity === null ? '' : p.quantity).replace(/,/g, '').trim();
    const n = parseFloat(raw);
    return Number.isFinite(n) && n > 0 ? raw : '';
  }
  const heldQtyStr = (c) => (c && c.liveQtyStr) || positionQtyStr(c && c.position);
  const heldQty = (c) => { const s = heldQtyStr(c); return s ? parseFloat(s) : 0; };
  function decideSide(c) {
    if (c.inCurrent && inList(c.current, BUY_GROUPS)) return 'buy';
    if (c.inCurrent && inList(c.current, SELL_GROUPS)) return 'sell';
    const gs = allGroups(c);
    const b = gs.some(g => inList(g, BUY_GROUPS)), s = gs.some(g => inList(g, SELL_GROUPS));
    if (b && !s) return 'buy';
    if (s && !b) return 'sell';
    return '';
  }

  /* ==========================================================================
   *                             交易层 UI
   * ========================================================================*/
  let layer = null;
  let view = null;

  function ensureLayer() {
    if (layer && document.body.contains(layer)) return layer;
    layer = document.createElement('div');
    layer.id = 'ft-trade-layer';
    document.body.appendChild(layer);
    return layer;
  }
  function openLayer(ctx, side, opts) {
    opts = opts || {};
    view = {
      ctx, side: side || '', rmSel: new Set(opts.rmSel || []), logs: [],
      remote: !!opts.remote, result: null, loading: !!opts.loading
    };
    ensureLayer();
    layer.classList.remove('ftt-running', 'ftt-docked');
    layer.classList.add('ftt-show');
    render();
  }
  function closeLayer() {
    if (running) {
      abortFlag = true;
      if (confirmWaiter) confirmWaiter(false);
      addLog('⏹ 已请求中止（若尚未点击「下单」则不会下单）');
      return;
    }
    if (layer) layer.classList.remove('ftt-show', 'ftt-running', 'ftt-docked');
    view = null;
  }
  function addLog(t) {
    if (!view) return;
    const line = `${new Date().toLocaleTimeString()} ${t}`;
    view.logs.push(line);
    const el = layer && layer.querySelector('.ftt-log');
    if (el) {
      el.insertAdjacentHTML('beforeend', `<div>${esc(line)}</div>`);
      el.scrollTop = el.scrollHeight;
    }
  }

  function render() {
    if (!layer || !view) return;
    const c = view.ctx;
    const sd = view.side;
    const qStr = heldQtyStr(c);
    const held = qStr ? parseFloat(qStr) : 0;
    const frac = held > 0 && !isWhole(held);
    const modeCls = S.mode === 'live' ? 'live' : (S.mode === 'confirm' ? 'confirm' : 'dry');
    const gs = allGroups(c);
    const badge = (g) => `<span class="ftt-badge ${inList(g, BUY_GROUPS) ? 'b' : (inList(g, SELL_GROUPS) ? 's' : '')}">${esc(g)}</span>`;
    let h = `<div class="ftt-box">
      <div class="ftt-head">
        <span class="ftt-title">${esc(c.symbol)}</span>
        <span class="ftt-tag ${modeCls}">${MODE_TXT[S.mode] || S.mode}${view.remote ? '·远程' : ''}</span>
        <span class="ftt-x" data-act="close" title="${running ? '中止' : '关闭 (Esc)'}">✕</span>
      </div>`;
    if (view.loading) {
      h += `<div class="ftt-line ftt-dim">正在读取分组归属 / 持仓 / 现价…</div></div>`;
      layer.innerHTML = h;
      return;
    }
    const where = c.page === 'positions' ? '页面：<b>持仓页</b>' : `当前分组：<b>${esc(c.current || '?')}</b>`;
    h += `<div class="ftt-line">${where}　所在：${gs.length ? gs.map(badge).join('') : '<span class="ftt-dim">（无归属数据）</span>'}</div>`;
    h += c.price > 0
      ? `<div class="ftt-line ftt-dim">网页现价 <b>$${fmtPx(c.price)}</b>（下单前会再读一次最新价）</div>`
      : `<div class="ftt-warn">⚠ 当前列表读不到 ${esc(c.symbol)} 的现价，买入时会用交易面板报价换算</div>`;
    if (c.position || qStr) {
      const p = c.position || {};
      h += `<div class="ftt-line ftt-dim">持仓 <b>${esc(qStr || '?')}</b> 股${c.liveQtyStr ? '（持仓页实时）' : ''} · 成本 ${esc(p.cost || '-')} · 损益 ${esc(p.gainloss_amount || '-')} (${esc(p.gainloss || '-')})</div>`;
      const ts = c.posMeta && c.posMeta.updated_at;
      if (!c.liveQtyStr && ts && (Date.now() / 1000 - ts) / 3600 > POS_STALE_H) {
        h += `<div class="ftt-warn">⚠ 持仓数据更新于 ${esc(c.posMeta.updated_at_str || '?')}，可能已过期（建议先抓一次持仓）</div>`;
      }
    } else {
      h += `<div class="ftt-line ftt-dim">${c.posOk ? '无持仓记录（不能一键全卖）' : '⚠ 读不到持仓 JSON（bridge_server.py 是否在运行？）'}</div>`;
    }
    if (frac) h += `<div class="ftt-frac">⛔ 持仓 ${esc(qStr)} 股含碎股：网页端只能卖整数股，<b>请到 Firstrade 手机 App 卖出</b></div>`;
    if (!c.memOk) h += `<div class="ftt-warn">⚠ 读不到分组归属，仅按当前分组判断</div>`;
    if (S.mode === 'live') h += `<div class="ftt-warn">⚡ 实盘模式：点击金额档 / 全卖 会<b>立即真实下单</b></div>`;

    h += `<div class="ftt-tabs">
        <button class="ftt-tab ${sd === 'buy' ? 'on' : ''}" data-act="side" data-side="buy">买进</button>
        <button class="ftt-tab sell ${sd === 'sell' ? 'on' : ''}" data-act="side" data-side="sell">卖出</button>
      </div>`;
    if (!sd) {
      h += `<div class="ftt-warn">该股票所在分组没有固定方向（或同时在买/卖分组），请选择买进或卖出</div>`;
    } else if (sd === 'buy') {
      h += `<div class="ftt-presets">${S.presets.map(v => {
        const est = c.price > 0 ? Math.round(v / c.price) : null;
        return `<button class="ftt-btn" data-act="buy" data-amt="${v}">$${v}<span class="ftt-sub">${est === null ? '按现价换算' : (est >= 1 ? '≈' + est + ' 股' : '不足 1 股')}</span></button>`;
      }).join('')}</div>
        <div class="ftt-row"><input data-in="amt" type="number" min="1" step="1" placeholder="自定义金额 $"><button class="ftt-btn" data-act="buy-custom">买进</button></div>
        <div class="ftt-dim">金额 ÷ 网页实时价 → 四舍五入整数股，以「股数 + 市价」下单</div>`;
    } else if (frac) {
      h += `<div class="ftt-warn">碎股持仓不支持网页卖出，请用手机 App</div>`;
    } else {
      if (qStr) h += `<button class="ftt-btn sell wide" data-act="sell-all">一键全卖 ${esc(String(Math.round(held)))} 股</button>`;
      h += `<div class="ftt-row"><input data-in="qty" type="number" min="1" step="1" placeholder="自定义整数股数${qStr ? '（≤ ' + esc(String(Math.round(held))) + '）' : ''}"><button class="ftt-btn sell" data-act="sell-custom">卖出</button></div>`;
    }
    const rm = removable(gs);
    if (rm.length) {
      h += `<div class="ftt-rm">成交后移出：${rm.map(g =>
        `<label><input type="checkbox" data-rm="${esc(g)}" ${view.rmSel.has(g) ? 'checked' : ''}> ${esc(g)}</label>`).join('')}` +
        (c.page === 'positions' ? `<div class="ftt-dim">（持仓页：移出任务会排队到 /app/watchlist 页执行）</div>` : '') + `</div>`;
    } else if (gs.length) {
      h += `<div class="ftt-rm ftt-dim">所在分组均为保护分组（Earning / Wrong），成交后不移除</div>`;
    }
    if (confirmWaiter) {
      h += `<div class="ftt-confirm">
          <div class="ftt-warn">⏸ 表单已填好，请核对交易面板（代码 / 买卖 / 股数 / 市价）</div>
          <div class="ftt-row"><button class="ftt-btn go" data-act="confirm">✅ 确认下单</button>
          <button class="ftt-btn ghost" data-act="cancel">取消</button></div>
        </div>`;
    }
    if (view.result) {
      const r = view.result;
      const color = r.ok ? '#A3BE8C' : (r.status === 'unknown' ? '#EBCB8B' : '#BF616A');
      h += `<div class="ftt-line" style="color:${color} !important;font-weight:700;">${esc(r.message || r.error || '')}` +
        (r.qty ? `<br>股数：${esc(r.qty)}${r.price ? ' @ $' + esc(fmtPx(r.price)) : ''}` : '') +
        (r.orderNo ? `<br>订单号：${esc(r.orderNo)}` : '') +
        (r.removed && r.removed.length ? `<br>已移出：${esc(r.removed.join(' / '))}` : '') +
        (r.removeQueued && r.removeQueued.length ? `<br>已排队移出：${esc(r.removeQueued.join(' / '))}` : '') +
        (r.removeFailed && r.removeFailed.length ? `<br>移出失败：${esc(r.removeFailed.map(f => f.group).join(' / '))}` : '') + `</div>`;
    }
    h += `<div class="ftt-log">${view.logs.map(l => `<div>${esc(l)}</div>`).join('')}</div>
      <div class="ftt-foot"><button class="ftt-btn ghost" data-act="close">${running ? '⏹ 中止（下单前有效）' : '关闭 (Esc)'}</button></div>
    </div>`;
    layer.innerHTML = h;
    const lg = layer.querySelector('.ftt-log');
    if (lg) lg.scrollTop = lg.scrollHeight;
  }

  /* ★ v5：交易结果 → 右下角提示文本（多行） */
  function resultSummary(sym, r) {
    const icon = r.ok ? (r.status === 'dry' ? '🧪' : '✅') : (r.status === 'unknown' ? '⚠️' : '❌');
    const lines = [`${icon} ${sym} ${r.message || r.error || ''}`.slice(0, 160)];
    if (r.qty) lines.push(`股数 ${r.qty}${r.price ? ' @ $' + fmtPx(r.price) : ''}`);
    if (r.orderNo) lines.push(`订单号 ${r.orderNo}`);
    if (r.removed && r.removed.length) lines.push(`已移出：${r.removed.join(' / ')}`);
    if (r.removeQueued && r.removeQueued.length) lines.push(`已排队移出：${r.removeQueued.join(' / ')}`);
    if (r.removeFailed && r.removeFailed.length) lines.push(`⚠ 移出失败：${r.removeFailed.map(f => f.group).join(' / ')}`);
    return lines.join('\n');
  }

  async function runTrade(sd, val, extra) {
    const x = extra || {};
    if (running || !view) return { ok: false, message: running ? '已有交易在执行' : '交易层未打开' };
    const c = view.ctx;
    let amount, qty;
    if (sd === 'buy') {
      if (x.qty !== undefined) {
        qty = parseNum(x.qty);
        if (!isWhole(qty)) { addLog('❌ 买入股数必须是正整数'); return { ok: false, message: '股数无效' }; }
      } else {
        amount = parseNum(val);
        if (!(amount > 0)) { addLog('❌ 请输入大于 0 的金额'); return { ok: false, message: '金额无效' }; }
        if (amount > MAX_BUY_AMOUNT) { addLog(`❌ 超过单笔上限 $${MAX_BUY_AMOUNT}`); return { ok: false, message: '超过上限' }; }
      }
    } else {
      const held = heldQty(c);
      if (held > 0 && !isWhole(held)) {
        addLog('⛔ ' + FRACTION_MSG);
        toast(`⛔ ${c.symbol}：${FRACTION_MSG}`);
        return { ok: false, status: 'fractional', message: `${c.symbol} ${FRACTION_MSG}` };
      }
      qty = parseNum(val);
      if (!isWhole(qty)) { addLog('❌ 卖出股数必须是正整数（网页端不支持碎股）'); return { ok: false, message: '股数无效' }; }
      if (held > 0 && qty > held + 1e-6) { addLog(`❌ 卖出股数 ${qty} 超过持仓 ${held}`); return { ok: false, message: '超过持仓' }; }
    }
    view.side = sd; view.logs = []; view.result = null;
    layer.classList.remove('ftt-docked');
    layer.classList.add('ftt-running');
    render();
    const groups = allGroups(c).filter(g => view.rmSel.has(g));
    const res = await execute({
      symbol: c.symbol, side: sd, amount, qty,
      removeGroups: groups, dry: !!x.dry, source: x.source || 'layer', onLog: addLog,
      ctx: c, allowSwitch: !!x.allowSwitch
    });
    if (layer) layer.classList.remove('ftt-running');
    if (view && res.price) view.ctx.price = res.price;
    const text = resultSummary(c.symbol, res);
    const clean = res.ok && !(res.removeFailed && res.removeFailed.length);
    if (clean) {
      /* ★ v5：成功（含预演）不在屏幕中央保留结果页 → 自动关闭交易层，结果放到右下角提示 */
      closeLayer();
      toast(text, res.status === 'dry' ? 5000 : 8000);
    } else {
      /* 失败 / 无法确认 / 移出失败：结果停靠在右下角（无遮罩、不拦截页面点击），看完点 ✕ 或 Esc 关闭 */
      if (view && layer) { view.result = res; layer.classList.add('ftt-docked'); render(); }
      toast(text, 8000);
    }
    return res;
  }

  function onLayerAction(e) {
    if (!view) return;
    const t = e.target;
    if (t === layer) { if (!running) closeLayer(); return; }
    const cb = t.closest && t.closest('input[data-rm]');
    if (cb) {
      setTimeout(() => {
        const g = cb.getAttribute('data-rm');
        if (cb.checked) view.rmSel.add(g); else view.rmSel.delete(g);
      }, 0);
      return;
    }
    const b = t.closest && t.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    if (act === 'close') { closeLayer(); return; }
    if (act === 'confirm') { if (confirmWaiter) confirmWaiter(true); return; }
    if (act === 'cancel') { if (confirmWaiter) confirmWaiter(false); return; }
    if (running) return;
    if (act === 'side') { view.side = b.dataset.side; view.result = null; render(); return; }
    if (act === 'buy') { runTrade('buy', b.dataset.amt); return; }
    if (act === 'buy-custom') { const i = layer.querySelector('input[data-in="amt"]'); runTrade('buy', i ? i.value : ''); return; }
    if (act === 'sell-all') { runTrade('sell', String(Math.round(heldQty(view.ctx)))); return; }
    if (act === 'sell-custom') { const i = layer.querySelector('input[data-in="qty"]'); runTrade('sell', i ? i.value : ''); return; }
  }

  const inLayer = (e) => !!(e.target && e.target.closest && e.target.closest('#ft-trade-layer'));
  ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'focusin'].forEach(type => {
    window.addEventListener(type, (e) => {
      if (!inLayer(e)) return;
      e.stopPropagation();
      if ((type === 'pointerdown' || type === 'mousedown') && e.target.closest('button, .ftt-x')) e.preventDefault();
    }, true);
  });
  window.addEventListener('click', (e) => {
    if (inLayer(e)) { e.stopPropagation(); onLayerAction(e); return; }
    onMaybeSymbolClick(e);
  }, true);
  window.addEventListener('keydown', (e) => {
    if (!layer || !view || !layer.classList.contains('ftt-show')) return;
    if (e.key === 'Escape') {
      const docked = layer.classList.contains('ftt-docked');
      if (confirmWaiter) confirmWaiter(false);
      else if (!running) closeLayer();
      if (!docked || inLayer(e)) e.stopPropagation();
      return;
    }
    if (inLayer(e)) {
      e.stopPropagation();
      if (e.key === 'Enter' && !running) {
        const k = e.target.getAttribute && e.target.getAttribute('data-in');
        if (k === 'amt') runTrade('buy', e.target.value);
        if (k === 'qty') runTrade('sell', e.target.value);
      }
    }
  }, true);

  /* ==========================================================================
   *                点击股票代码 → 打开交易层（watchlist + positions）
   * ========================================================================*/
  function symbolFromEvent(e) {
    if (!S.enabled || !isTradePage() || !e.isTrusted) return '';
    if (e.button !== 0 || e.altKey || e.metaKey || e.ctrlKey || e.shiftKey) return '';
    const t = e.target;
    if (!t || !t.closest) return '';
    if (t.closest('.ft-custom-tag-container, #ft-wl-hud, #ft-trade-layer')) return '';
    if (t.closest('.ag-group-contracted, .ag-group-expanded, .ag-group-checkbox, .ag-row-drag')) return '';
    const cell = t.closest('[col-id="symbol"]');
    if (!cell || cell.closest('.ag-header') || cell.closest(ROW_EXCLUDE)) return '';
    const row = cell.closest('[row-id]');
    return row ? symbolFromRowId(row.getAttribute('row-id')) : '';
  }
  ['pointerdown', 'mousedown', 'mouseup'].forEach(type => {
    window.addEventListener(type, (e) => { if (symbolFromEvent(e)) e.stopPropagation(); }, true);
  });
  function onMaybeSymbolClick(e) {
    const sym = symbolFromEvent(e);
    if (!sym) return;
    e.preventDefault();
    e.stopPropagation();
    openForSymbol(sym);
  }
  async function openForSymbol(sym) {
    if (running) { toast('⏳ 上一笔交易还在执行'); return; }
    const a = api();
    if (!a) { toast('watchlist.js 未就绪，请刷新页面'); return; }
    if (a.isBusy() || window.__FT_AGENT_BUSY__) { toast('⏳ 自选股任务/远程任务进行中，稍后再交易'); return; }
    const pg = pageKind();
    const inCur = pg === 'watchlist';
    openLayer({ symbol: sym, page: pg, current: inCur ? cleanGroupName(a.groupName()) : '', inCurrent: inCur, groups: [] }, '', { loading: true });
    const c = await loadContext(sym, inCur);
    if (!view || view.ctx.symbol !== sym || running) return;
    view.ctx = c;
    view.side = decideSide(c);
    view.rmSel = new Set(S.removeAfter ? removable(allGroups(c)) : []);
    view.loading = false;
    render();
  }

  /* ---------- 远程（Python /wl_trade → wl_agent.js，仅 watchlist 页） ---------- */
  async function executeRemote(p) {
    p = p || {};
    const sym = String(p.symbol || '').trim().toUpperCase();
    const side = p.side === 'sell' ? 'sell' : (p.side === 'buy' ? 'buy' : '');
    if (running) return { ok: false, message: '已有一笔交易在执行中' };
    if (!S.enabled) return { ok: false, message: '快速交易已在 popup 中关闭' };
    if (!sym || !side) return { ok: false, message: '缺少代码或买卖方向' };
    if (!isWatchlistPage()) return { ok: false, message: '远程交易只在 /app/watchlist 页执行' };
    const a = api();
    const inCur = !!(a && a.hasSymbolInGrid && a.hasSymbolInGrid(sym));
    const c = await loadContext(sym, inCur);
    const rm = p.remove === false ? [] : removable(allGroups(c));
    if (side === 'sell') {
      const held = heldQty(c);
      if (held > 0 && !isWhole(held)) return { ok: false, status: 'fractional', message: `${sym} ${FRACTION_MSG}` };
      let val = p.qty;
      if (val === undefined || val === null || val === '' || String(val).toLowerCase() === 'all') {
        val = heldQtyStr(c);
        if (!val) return { ok: false, message: `${sym} 无持仓记录，无法全卖` };
        val = String(Math.round(parseFloat(val)));
      }
      openLayer(c, 'sell', { remote: true, rmSel: rm });
      return runTrade('sell', val, { dry: !!p.dry, source: 'remote', allowSwitch: true });
    }
    openLayer(c, 'buy', { remote: true, rmSel: rm });
    const hasQty = p.qty !== undefined && p.qty !== null && p.qty !== '' && String(p.qty).toLowerCase() !== 'all';
    return runTrade('buy', p.amount, { dry: !!p.dry, source: 'remote', allowSwitch: true, qty: hasQty ? p.qty : undefined });
  }

  /* ---------- 探测（popup 按钮） ---------- */
  async function probe() {
    const tb = tradeButton();
    const op = await openPanel();
    const r = tradeRoot();
    const tabs = r ? Array.from(r.querySelectorAll('[role="tab"]')).map(x => cleanText(x) + (x.getAttribute('aria-selected') === 'true' ? '✓' : '')) : [];
    const foot = r && r.querySelector('footer');
    const tx = trig('quick-trade-form-transaction');
    const ot = trig('quick-trade-form-order-type');
    const sb = submitButton();
    const qi = quoteInfo();
    return {
      ok: true,
      tradeBtn: !!tb,
      panel: r ? (formReady() ? '已打开（表单态）✅' : '已打开（非表单态）') : ('未打开 ❌ ' + (op.error || '')),
      tabs,
      symbolInput: formReady(),
      quoteInfo: qi ? `${qi.name || '-'} $${fmtPx(qi.price)}` : '',
      transaction: tx ? cleanText(tx) : '',
      qtyMode: qtyMode(),
      orderType: ot ? cleanText(ot) : '',
      submit: sb ? `找到（${sb.disabled ? '禁用' : '可点'}）` : '',
      footerButtons: foot ? Array.from(foot.querySelectorAll('button')).filter(isVisible).map(cleanText).filter(Boolean) : [],
      notifications: !!document.querySelector('section[aria-label^="Notifications"]')
    };
  }

  /* ---------- 设置 & 通信 ---------- */
  function applyClass() {
    document.documentElement.classList.toggle('ft-trade-on', S.enabled && isTradePage());
  }
  function loadSettings() {
    chrome.storage.local.get(['ftTradeEnabled', 'ftTradeMode', 'ftTradeRemoveAfter', 'ftTradePresets', 'ftDebug'], (res) => {
      S.enabled = res.ftTradeEnabled !== false;
      S.mode = MODES.includes(res.ftTradeMode) ? res.ftTradeMode : 'dry';
      S.removeAfter = res.ftTradeRemoveAfter !== false;
      S.presets = (Array.isArray(res.ftTradePresets) && res.ftTradePresets.length ? res.ftTradePresets : [1000, 2000, 3000])
        .map(Number).filter(n => n > 0).slice(0, 6);
      S.debug = !!res.ftDebug;
      applyClass();
      if (view && !running) render();
    });
  }
  chrome.storage.onChanged.addListener((c, area) => {
    if (area !== 'local') return;
    if (c.ftTradeEnabled || c.ftTradeMode || c.ftTradeRemoveAfter || c.ftTradePresets || c.ftDebug) loadSettings();
  });
  setInterval(applyClass, 1500);

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || !msg.action) return;
    if (msg.action === 'FT_TRADE_PROBE') {
      probe().then(sendResponse).catch(e => sendResponse({ ok: false, error: String(e) }));
      return true;
    }
    if (msg.action === 'FT_TRADE_STATUS') {
      sendResponse({ ok: true, running, mode: S.mode, enabled: S.enabled, page: pageKind() });
      return;
    }
  });

  window.__FT_TRADE__ = { version: 4, execute, executeRemote, probe, isRunning: () => running };

  loadSettings();
  console.log(LOG, `ft_trade.js v4 就绪（page=${pageKind() || 'other'}）`);
})();