/* ============================================================================
 * Firstrade 快速交易层  ft_trade.js  v2        仅在 /app/watchlist 生效
 *   点击股票代码 → 弹出交易层 → 自动驱动页面底部「交易」快速下单面板
 *   规则：当前/所在分组 ∈ 买/买买/买买买 → 买进（金额档 / 自定义金额）
 *         当前/所在分组 ∈ 卖卖卖          → 卖出（股数：positions JSON 的 quantity 一键全卖 / 自定义）
 *         其它 / 冲突                     → 由用户选择
 *   下单模式（storage.ftTradeMode）：
 *         dry     预演：自动填好表单，绝不点「下单」
 *         confirm 下单前暂停：填好后等用户在交易层点「确认下单」
 *         live    实盘：直接点「下单」
 *   成交判定：仅当出现「您的订单已送出 / 订单号码」等明确成功提示才算成功 → 才移出分组
 *   安全：同一时间只跑一笔；「下单」只点一次；下单前复核表单；全程审计日志
 * ==========================================================================*/
(() => {
  if (window.__FT_TRADE_V2__) return;
  window.__FT_TRADE_V2__ = true;

  const LOG = '[FT-TRADE]';
  const BUY_GROUPS = ['买', '买买', '买买买'];
  const SELL_GROUPS = ['卖卖卖'];
  const PROTECTED = ['Earning', 'Wrong'];
  const ROW_EXCLUDE = '.ag-floating-top, .ag-floating-bottom, #app-quote-bar, header, #app-header';
  const MODES = ['dry', 'confirm', 'live'];
  const MODE_TXT = { dry: '🧪 预演', confirm: '✋ 下单前确认', live: '⚡ 实盘' };
  const CONFIRM_TIMEOUT = 120000;
  const MAX_BUY_AMOUNT = 50000;          // 单笔买入金额上限（防手滑多打一个 0）
  const POS_STALE_H = 20;                // 持仓 JSON 超过这么多小时提示过期

  const S = { enabled: true, mode: 'dry', removeAfter: true, presets: [1000, 2000, 3000], debug: false };
  let running = false;
  let abortFlag = false;
  let confirmWaiter = null;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const log = (...a) => { if (S.debug) console.log(LOG, ...a); };
  const isWatchlistPage = () => /\/watchlist/i.test(location.pathname || '');
  const api = () => window.__FT_WL_API__ || null;
  const toast = (t) => { try { (window.__FT_TOAST__ || console.log)(t); } catch (e) { } };
  const normKey = (s) => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const normGroup = (s) => String(s || '').replace(/[（(][^）)]*[）)]\s*$/g, '').replace(/\s+/g, '').toUpperCase();
  const cleanGroupName = (s) => String(s || '').replace(/\u00a0/g, ' ').replace(/[（(]\s*\d+\s*[）)]\s*$/, '').trim();
  const inList = (g, list) => list.some(x => normGroup(x) === normGroup(g));
  const $id = (id) => document.getElementById(id);
  const parseNum = (v) => parseFloat(String(v === undefined || v === null ? '' : v).replace(/[,$\s]/g, ''));
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
   *                  页面「快速交易」面板 DOM 驱动
   * ========================================================================*/
  const NEW_ORDER_RE = /^(新订单|新建订单|再下一单|继续交易|继续下单|New Order|Place Another Order)$/i;

  /* 表单态：代码输入框可见 */
  function formReady() { const i = $id('quick-trade-symbol-search'); return !!(i && isVisible(i)); }

  /* ★ v2：面板根节点按「可拖动标题栏」识别，表单态 / 订单确认态都能找到 */
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
    if (r0) {                                      // 停在上一笔的「订单确认」页
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

  /* ---------- 代码选择 ---------- */
  function comboItems() {
    const sel = '[data-combobox-content] [data-combobox-item], [role="listbox"] [role="option"], [data-combobox-item]';
    return Array.from(document.querySelectorAll(sel)).filter(el => isVisible(el) &&
      !el.closest('[data-command-root]') && !el.closest('[data-select-content]') && !el.closest('#ft-trade-layer'));
  }
  function itemMatches(el, k) {
    if (normKey(el.getAttribute('data-value')) === k || normKey(el.getAttribute('data-label')) === k) return true;
    const first = (cleanText(el).split(/\s+/)[0] || '');
    if (normKey(first) === k) return true;
    return Array.from(el.querySelectorAll('span, div, p, strong, b')).some(x => normKey(cleanText(x)) === k);
  }
  function symbolConfirmed(k) {
    const root = tradeRoot();
    if (!root) return false;
    const i = $id('quick-trade-symbol-search');
    if (i && normKey(i.value) === k) return true;
    const info = root.querySelector('p[class*="pl-8"]');
    if (info) {
      const toks = cleanText(info).toUpperCase().split(/[^A-Z0-9.\-]+/);
      if (toks.some(t => normKey(t) === k)) return true;
    }
    return false;
  }
  async function pickSymbol(sym) {
    let lastErr = '';
    for (const f of candidateForms(sym)) {
      const inp = $id('quick-trade-symbol-search');
      if (!inp) return { ok: false, error: '找不到交易面板的代码输入框' };
      const k = normKey(f);
      inp.focus();
      setNativeValue(inp, '');
      await sleep(80);
      setNativeValue(inp, f);
      inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: f.slice(-1) }));
      const hit = await waitFor(() => comboItems().find(el => itemMatches(el, k)) || null, 6000, 120);
      if (!hit) { lastErr = `联想列表里没有精确匹配 ${f}`; continue; }
      fireMouseSeq(hit);
      const ok = await waitFor(() => symbolConfirmed(k), 4000, 120);
      if (ok) { await sleep(350); return { ok: true, form: f }; }
      lastErr = `点选 ${f} 后未在面板上确认到该代码`;
    }
    return { ok: false, error: lastErr || '无法选择代码' };
  }

  /* ---------- 下拉框（交易类型 / 订单类型） ---------- */
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
    if (!i) return { ok: false, error: '找不到数量/金额输入框' };
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
  const ERR_RE = /失败|错误|不足|拒绝|无效|不允许|无法|超出|error|fail|insufficient|reject|invalid|not allowed|exceed/i;
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
      const out = readOutcome(before, n0, sent0);    // ★ 先判结果，再考虑点确认（防止成功后误点「确定」）
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

  /* 下单前最后复核：防止等待确认期间表单被改动 */
  function verifyForm(form, txLabel, mode, val) {
    if (!formReady()) return { ok: false, error: '交易表单已不在（可能已手动下单或面板被关闭）' };
    if (!symbolConfirmed(normKey(form))) return { ok: false, error: `代码不是 ${form}` };
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

  function waitUserConfirm(ms) {
    return new Promise((resolve) => {
      const t = setTimeout(() => { if (confirmWaiter) confirmWaiter(false); }, ms);
      confirmWaiter = (v) => { confirmWaiter = null; clearTimeout(t); resolve(!!v); render(); };
      render();
    });
  }

  /* ---------- 主流程 ---------- */
  async function execute(opts) {
    const o = opts || {};
    const sym = String(o.symbol || '').trim().toUpperCase();
    const side = o.side === 'sell' ? 'sell' : (o.side === 'buy' ? 'buy' : '');
    const valStr = side === 'buy' ? String(parseNum(o.amount)) : String(o.qty === undefined ? '' : o.qty).replace(/,/g, '').trim();
    const valNum = parseNum(valStr);
    const groups = (Array.isArray(o.removeGroups) ? o.removeGroups : []).filter(g => !inList(g, PROTECTED));
    const mode = o.dry ? 'dry' : (MODES.includes(S.mode) ? S.mode : 'dry');
    const say = (t) => { log(t); if (typeof o.onLog === 'function') { try { o.onLog(t); } catch (e) { } } };
    const res = {
      ok: false, symbol: sym, side, amount: side === 'buy' ? valNum : null, qty: side === 'sell' ? valStr : null,
      mode, status: '', message: '', orderNo: '', submitted: false, removed: [], removeFailed: [],
      source: o.source || 'layer'
    };
    const fail = (m) => Object.assign(res, { message: m, error: m });

    if (running) return fail('已有一笔交易在执行中');
    const a = api();
    if (!isWatchlistPage() || !a) return fail('请在 /app/watchlist 页面使用（watchlist.js 未就绪）');
    if (a.isBusy()) return fail('自选股同步/行情抓取进行中，请稍后再交易');
    if (!sym || !side) return fail('缺少代码或买卖方向');
    if (!(valNum > 0)) return fail(side === 'buy' ? '买入金额必须大于 0' : '卖出股数必须大于 0');
    if (side === 'buy' && valNum > MAX_BUY_AMOUNT) return fail(`单笔买入金额超过上限 $${MAX_BUY_AMOUNT}`);

    running = true; abortFlag = false;
    try { a.setTradeBusy(true); } catch (e) { }
    const chk = () => { if (abortFlag) throw new Error('已取消（尚未点击「下单」）'); };
    const must = (r, step) => { if (!r || !r.ok) throw new Error(`${step}：${(r && r.error) || '失败'}`); return r; };
    try {
      a.clearStopFlags(); a.cleanNavSearch();
      say(`模式：${MODE_TXT[mode]}`);
      say('① 打开快速交易面板…'); must(await openPanel(), '打开交易面板'); chk();
      await ensureStocksTab();
      say(`② 选择代码 ${sym}…`);
      const pk = must(await pickSymbol(sym), '选择代码'); chk();
      const txLabel = side === 'buy' ? '买进' : '卖出';
      say(`③ 交易类型 → ${txLabel}`); must(await chooseSelect('quick-trade-form-transaction', txLabel), '交易类型'); chk();
      await sleep(300);
      const qMode = side === 'buy' ? '金额' : '股数';
      say(`④ 数量方式 → ${qMode}`); must(await setQtyMode(qMode), '数量方式'); chk();
      say(`⑤ 填写 ${side === 'buy' ? '$' + valStr : valStr + ' 股'}`); must(await fillQty(valStr), '填写数量'); chk();
      if (trig('quick-trade-form-order-type')) {
        say('⑥ 订单类型 → 市价'); must(await chooseSelect('quick-trade-form-order-type', '市价'), '订单类型');
      } else say('⑥ 未出现订单类型下拉框（金额单通常固定市价），跳过');
      await sleep(250);
      if (!qtyMatches(valStr)) { say('数量框被重置，重新填写…'); must(await fillQty(valStr), '重新填写数量'); }
      chk();

      if (mode === 'dry') {
        res.ok = true; res.status = 'dry';
        res.message = '🧪 预演完成：表单已全部填好，未点击「下单」，请在页面右侧交易面板核对';
        say(res.message);
        return res;
      }
      if (mode === 'confirm') {
        say('⏸ 表单已填好：请核对右侧交易面板，然后在本层点「✅ 确认下单」（120 秒内）');
        const go = await waitUserConfirm(CONFIRM_TIMEOUT);
        if (!go) throw new Error('已取消：未点击「下单」');
      }
      chk();
      const vf = verifyForm(pk.form, txLabel, qMode, valStr);
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
        await closeTradePanel();
        const rr = await removeFromGroups(sym, groups, say);
        res.removed = rr.removed; res.removeFailed = rr.failed;
      } else {
        say('⑧ 未勾选任何分组，保留在分组内');
      }
    } catch (e) {
      res.ok = false;
      res.error = String((e && e.message) || e);
      if (!res.message || res.status === '') res.message = res.error;
      say('❌ ' + res.error);
    } finally {
      running = false;
      try { a.setTradeBusy(false); } catch (e) { }
      bg({ action: 'FT_TRADE_LOG', payload: Object.assign({ ts: Date.now(), page_group: cleanGroupName(a.groupName()) }, res) });
    }
    return res;
  }

  /* ==========================================================================
   *                       上下文（分组归属 / 持仓）
   * ========================================================================*/
  async function loadContext(sym, inCurrent) {
    const a = api();
    const current = a ? cleanGroupName(a.groupName()) : '';
    const [mem, pos] = await Promise.all([bg({ action: 'FT_SERVER_MEMBERSHIP' }), bg({ action: 'FT_SERVER_POSITIONS' })]);
    const k = normKey(sym);
    const groups = [];
    const gmap = (mem && mem.ok && mem.data && mem.data.groups) || {};
    Object.keys(gmap).forEach(g => {
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
    return {
      symbol: sym, current, inCurrent: !!inCurrent, groups, position, posMeta,
      memOk: !!(mem && mem.ok), posOk: !!(pos && pos.ok)
    };
  }
  function allGroups(c) {
    const s = c.groups.slice();
    if (c.inCurrent && c.current && !s.some(g => normGroup(g) === normGroup(c.current))) s.unshift(c.current);
    return s;
  }
  const removable = (groups) => groups.filter(g => !inList(g, PROTECTED));
  function positionQtyStr(p) {
    if (!p) return '';
    const raw = String(p.quantity === undefined || p.quantity === null ? '' : p.quantity).replace(/,/g, '').trim();
    const n = parseFloat(raw);
    return Number.isFinite(n) && n > 0 ? raw : '';
  }
  const positionQty = (p) => { const s = positionQtyStr(p); return s ? parseFloat(s) : 0; };
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
  let view = null;     // { ctx, side, rmSel:Set, logs:[], remote, result, loading }

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
    layer.classList.remove('ftt-running');
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
    if (layer) layer.classList.remove('ftt-show', 'ftt-running');
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
    const qStr = positionQtyStr(c.position);
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
      h += `<div class="ftt-line ftt-dim">正在读取分组归属 / 持仓…</div></div>`;
      layer.innerHTML = h;
      return;
    }
    h += `<div class="ftt-line">当前分组：<b>${esc(c.current || '?')}</b>　所在：${gs.length ? gs.map(badge).join('') : '<span class="ftt-dim">（无归属数据）</span>'}</div>`;
    if (c.position) {
      const p = c.position;
      h += `<div class="ftt-line ftt-dim">持仓 <b>${esc(qStr || '?')}</b> 股 · 成本 ${esc(p.cost || '-')} · 损益 ${esc(p.gainloss_amount || '-')} (${esc(p.gainloss || '-')})</div>`;
      const ts = c.posMeta && c.posMeta.updated_at;
      if (ts && (Date.now() / 1000 - ts) / 3600 > POS_STALE_H) {
        h += `<div class="ftt-warn">⚠ 持仓数据更新于 ${esc(c.posMeta.updated_at_str || '?')}，可能已过期（建议先抓一次持仓）</div>`;
      }
    } else {
      h += `<div class="ftt-line ftt-dim">${c.posOk ? '无持仓记录（没买过 → 不能一键全卖）' : '⚠ 读不到持仓 JSON（bridge_server.py 是否在运行？）'}</div>`;
    }
    if (!c.memOk) h += `<div class="ftt-warn">⚠ 读不到分组归属，仅按当前分组判断</div>`;
    if (S.mode === 'live') h += `<div class="ftt-warn">⚡ 实盘模式：点击金额档 / 全卖 会<b>立即真实下单</b></div>`;

    h += `<div class="ftt-tabs">
        <button class="ftt-tab ${sd === 'buy' ? 'on' : ''}" data-act="side" data-side="buy">买进</button>
        <button class="ftt-tab sell ${sd === 'sell' ? 'on' : ''}" data-act="side" data-side="sell">卖出</button>
      </div>`;
    if (!sd) {
      h += `<div class="ftt-warn">该股票所在分组没有固定方向（或同时在买/卖分组），请选择买进或卖出</div>`;
    } else if (sd === 'buy') {
      h += `<div class="ftt-presets">${S.presets.map(v => `<button class="ftt-btn" data-act="buy" data-amt="${v}">$${v}</button>`).join('')}</div>
        <div class="ftt-row"><input data-in="amt" type="number" min="1" step="1" placeholder="自定义金额 $"><button class="ftt-btn" data-act="buy-custom">买进</button></div>`;
    } else {
      if (qStr) h += `<button class="ftt-btn sell wide" data-act="sell-all">一键全卖 ${esc(qStr)} 股</button>`;
      h += `<div class="ftt-row"><input data-in="qty" type="number" min="0" step="any" placeholder="自定义股数${qStr ? '（≤ ' + esc(qStr) + '）' : ''}"><button class="ftt-btn sell" data-act="sell-custom">卖出</button></div>`;
    }
    const rm = removable(gs);
    if (rm.length) {
      h += `<div class="ftt-rm">成交后移出：${rm.map(g =>
        `<label><input type="checkbox" data-rm="${esc(g)}" ${view.rmSel.has(g) ? 'checked' : ''}> ${esc(g)}</label>`).join('')}</div>`;
    } else if (gs.length) {
      h += `<div class="ftt-rm ftt-dim">所在分组均为保护分组（Earning / Wrong），成交后不移除</div>`;
    }
    if (confirmWaiter) {
      h += `<div class="ftt-confirm">
          <div class="ftt-warn">⏸ 表单已填好，请核对右侧交易面板（代码 / 买卖 / 数量 / 市价）</div>
          <div class="ftt-row"><button class="ftt-btn go" data-act="confirm">✅ 确认下单</button>
          <button class="ftt-btn ghost" data-act="cancel">取消</button></div>
        </div>`;
    }
    if (view.result) {
      const r = view.result;
      const color = r.ok ? '#A3BE8C' : (r.status === 'unknown' ? '#EBCB8B' : '#BF616A');
      h += `<div class="ftt-line" style="color:${color} !important;font-weight:700;">${esc(r.message || r.error || '')}` +
        (r.orderNo ? `<br>订单号：${esc(r.orderNo)}` : '') +
        (r.removed && r.removed.length ? `<br>已移出：${esc(r.removed.join(' / '))}` : '') +
        (r.removeFailed && r.removeFailed.length ? `<br>移出失败：${esc(r.removeFailed.map(f => f.group).join(' / '))}` : '') + `</div>`;
    }
    h += `<div class="ftt-log">${view.logs.map(l => `<div>${esc(l)}</div>`).join('')}</div>
      <div class="ftt-foot"><button class="ftt-btn ghost" data-act="close">${running ? '⏹ 中止（下单前有效）' : '关闭 (Esc)'}</button></div>
    </div>`;
    layer.innerHTML = h;
    const lg = layer.querySelector('.ftt-log');
    if (lg) lg.scrollTop = lg.scrollHeight;
  }

  async function runTrade(sd, val, extra) {
    const x = extra || {};
    if (running || !view) return { ok: false, message: running ? '已有交易在执行' : '交易层未打开' };
    const c = view.ctx;
    const n = parseNum(val);
    if (!(n > 0)) { addLog(sd === 'buy' ? '❌ 请输入大于 0 的金额' : '❌ 请输入大于 0 的股数'); return { ok: false, message: '数值无效' }; }
    if (sd === 'buy' && n > MAX_BUY_AMOUNT) { addLog(`❌ 超过单笔上限 $${MAX_BUY_AMOUNT}`); return { ok: false, message: '超过上限' }; }
    if (sd === 'sell') {
      const held = positionQty(c.position);
      if (held > 0 && n > held * 1.000001) { addLog(`❌ 卖出股数 ${n} 超过持仓 ${held}`); return { ok: false, message: '超过持仓' }; }
    }
    view.side = sd; view.logs = []; view.result = null;
    layer.classList.add('ftt-running');
    render();
    const groups = allGroups(c).filter(g => view.rmSel.has(g));
    const res = await execute({
      symbol: c.symbol, side: sd,
      amount: sd === 'buy' ? n : undefined,
      qty: sd === 'sell' ? String(val).replace(/,/g, '').trim() : undefined,
      removeGroups: groups, dry: !!x.dry, source: x.source || 'layer', onLog: addLog
    });
    if (layer) layer.classList.remove('ftt-running');
    if (view) { view.result = res; render(); }
    toast((res.ok ? (res.status === 'dry' ? '🧪 ' : '✅ ') : '❌ ') + `${c.symbol} ${res.message || res.error || ''}`.slice(0, 120));
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
    if (act === 'sell-all') { runTrade('sell', positionQtyStr(view.ctx.position)); return; }
    if (act === 'sell-custom') { const i = layer.querySelector('input[data-in="qty"]'); runTrade('sell', i ? i.value : ''); return; }
  }

  /* ★ window 捕获阶段拦截：交易层内的事件不再传到页面（防止 Firstrade 交易面板把它当成"点外面"而自动关闭） */
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
      if (confirmWaiter) confirmWaiter(false);
      else if (!running) closeLayer();
      e.stopPropagation();
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
   *                      点击股票代码 → 打开交易层
   * ========================================================================*/
  function symbolFromEvent(e) {
    if (!S.enabled || !isWatchlistPage() || !e.isTrusted) return '';
    if (e.button !== 0 || e.altKey || e.metaKey || e.ctrlKey || e.shiftKey) return '';
    const t = e.target;
    if (!t || !t.closest) return '';
    if (t.closest('.ft-custom-tag-container, #ft-wl-hud, #ft-trade-layer')) return '';
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
    openLayer({ symbol: sym, current: cleanGroupName(a.groupName()), inCurrent: true, groups: [] }, '', { loading: true });
    const c = await loadContext(sym, true);
    if (!view || view.ctx.symbol !== sym || running) return;
    view.ctx = c;
    view.side = decideSide(c);
    view.rmSel = new Set(S.removeAfter ? removable(allGroups(c)) : []);
    view.loading = false;
    render();
  }

  /* ---------- 远程（Python /wl_trade → wl_agent.js） ---------- */
  async function executeRemote(p) {
    p = p || {};
    const sym = String(p.symbol || '').trim().toUpperCase();
    const side = p.side === 'sell' ? 'sell' : (p.side === 'buy' ? 'buy' : '');
    if (running) return { ok: false, message: '已有一笔交易在执行中' };
    if (!S.enabled) return { ok: false, message: '快速交易已在 popup 中关闭' };
    if (!sym || !side) return { ok: false, message: '缺少代码或买卖方向' };
    const a = api();
    const inCur = !!(a && a.hasSymbolInGrid && a.hasSymbolInGrid(sym));
    const c = await loadContext(sym, inCur);
    let val = side === 'buy' ? p.amount : p.qty;
    if (side === 'sell' && (val === undefined || val === null || val === '' || String(val).toLowerCase() === 'all')) {
      val = positionQtyStr(c.position);
      if (!val) return { ok: false, message: `${sym} 无持仓记录，无法全卖` };
    }
    openLayer(c, side, { remote: true, rmSel: p.remove === false ? [] : removable(allGroups(c)) });
    return runTrade(side, val, { dry: !!p.dry, source: 'remote' });
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
    return {
      ok: true,
      tradeBtn: !!tb,
      panel: r ? (formReady() ? '已打开（表单态）✅' : '已打开（非表单态）') : ('未打开 ❌ ' + (op.error || '')),
      tabs,
      symbolInput: formReady(),
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
    document.documentElement.classList.toggle('ft-trade-on', S.enabled && isWatchlistPage());
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
      sendResponse({ ok: true, running, mode: S.mode, enabled: S.enabled });
      return;
    }
  });

  window.__FT_TRADE__ = { version: 2, execute, executeRemote, probe, isRunning: () => running };

  loadSettings();
  console.log(LOG, `ft_trade.js v2 就绪（isWatchlist=${isWatchlistPage()}）`);
})();