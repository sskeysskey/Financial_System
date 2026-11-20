/* 注入 MarketWatch 页面（扩展隔离环境）。用 IIFE 包裹，重复注入时不会因 const 重复声明而报错 */
(() => {
  if (self.__mwProbe) return;

  function mwIsStale() {
    try { if (window.__mwStalePage) return true; } catch (e) { }
    const p = location.protocol;
    return p === 'about:' || p === 'data:' || p === 'chrome-error:';
  }
  function mwText(el) { return el ? (el.textContent || '').replace(/\s+/g, ' ').trim() : ''; }
  function mwCellText(el) {
    if (!el) return '';
    const d = el.querySelector('div');
    return mwText(d || el);
  }
  function mwHasFollowing(el, maxDepth) {
    let n = el, d = 0;
    const lim = maxDepth || 3;
    while (n && n.parentNode && d <= lim) {
      if (n.nextElementSibling) return true;
      n = n.parentNode; d++;
    }
    return false;
  }
  function mwBodyText(doc, live) {
    const b = doc.body;
    if (!b) return '';
    if (live) return (b.innerText || '').slice(0, 3000);
    const c = b.cloneNode(true);
    c.querySelectorAll('script, style, noscript, template').forEach(e => e.remove());
    return (c.textContent || '').replace(/\s+/g, ' ').slice(0, 3000);
  }
  // 'blocked'（硬封禁页）/ 'captcha'（滑块）/ null；DataDome iframe t=bv 为封禁页
  function mwChallengeKind(doc, live) {
    const ifr = doc.querySelector('iframe[src*="captcha-delivery.com"], iframe[src*="geo.captcha"]');
    if (ifr) {
      const src = ifr.getAttribute('src') || '';
      return /[?&]t=bv(&|$)/i.test(src) ? 'blocked' : 'captcha';
    }
    if (doc.querySelector('.element--intraday, mw-downloaddata, .download-data, '
      + 'table[aria-label="Historical Quotes data table"], h1[class*="company"]')) return null;
    const txt = mwBodyText(doc, live);
    if (/access is temporarily restricted|temporarily restricted|access denied|you have been blocked|unusual activity/i.test(txt)) return 'blocked';
    if (/verify you are (a )?human|are you a robot/i.test(txt)) return 'captcha';
    return null;
  }
  function mwPathSymbolSeg(pathname) {
    const segs = (pathname || '').toLowerCase().split('/').filter(Boolean);
    let seg = segs.length > 2 ? segs[2] : '';
    try { seg = decodeURIComponent(seg); } catch (e) { }
    return seg;
  }
  const MW_NOTFOUND_RE = /symbol lookup|no results found|there were no matches/i;

  /* ---------- 历史表格 ---------- */
  function mwFindTable(doc) {
    let t = doc.querySelector('table[aria-label="Historical Quotes data table"]');
    if (t) return t;
    for (const cand of doc.querySelectorAll('table')) {
      const hs = Array.from(cand.querySelectorAll('thead th')).map(th => mwCellText(th).toLowerCase());
      if (hs.includes('date') && hs.includes('close')) return cand;
    }
    return null;
  }
  function mwTableState(doc, pathname, expectSeg, maxRows, complete, live) {
    const ck = mwChallengeKind(doc, live);
    if (ck) return ck;
    if (!(pathname || '').toLowerCase().includes('download-data')) return 'notfound';
    if (expectSeg && mwPathSymbolSeg(pathname) !== expectSeg) return 'wrong_symbol';
    const tbl = mwFindTable(doc);
    if (tbl) {
      const rows = tbl.querySelectorAll('tbody tr');
      const k = Math.min(rows.length, maxRows);
      if (k > 0 && (complete || mwHasFollowing(rows[k - 1], 3))) return 'ready';
    }
    if (complete && MW_NOTFOUND_RE.test(mwBodyText(doc, live))) return 'notfound';
    return 'loading';
  }
  function mwNum(s) {
    if (!s) return null;
    s = s.replace(/[$,\s]/g, '');
    if (!s || s === '-' || /^n\/?a$/i.test(s)) return null;
    const v = parseFloat(s);
    return isNaN(v) ? null : v;
  }
  function mwVol(s) {
    if (!s) return null;
    s = s.replace(/[,\s]/g, '').toUpperCase();
    const m = s.match(/^([\d.]+)([KMB])?$/);
    if (!m) return null;
    let v = parseFloat(m[1]);
    if (m[2]) v *= { K: 1e3, M: 1e6, B: 1e9 }[m[2]];
    return Math.round(v);
  }
  function mwParseTable(doc, maxRows) {
    const tbl = mwFindTable(doc);
    if (!tbl) return { error: '未找到数据表格' };
    const headers = Array.from(tbl.querySelectorAll('thead th')).map(th => mwCellText(th).toLowerCase());
    const idx = n => headers.indexOf(n);
    const cols = {
      date: idx('date'), open: idx('open'), high: idx('high'),
      low: idx('low'), close: idx('close'), volume: idx('volume')
    };
    if (cols.date < 0 || cols.close < 0) return { error: '表头解析失败: ' + headers.join('|') };
    const out = [];
    for (const tr of tbl.querySelectorAll('tbody tr')) {
      const cells = tr.querySelectorAll('td');
      if (cells.length <= Math.max(cols.date, cols.close)) continue;
      const m = mwCellText(cells[cols.date]).match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
      if (!m) continue;
      const dateStr = `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
      const g = k => (cols[k] >= 0 && cells[cols[k]]) ? mwCellText(cells[cols[k]]) : '';
      const close = mwNum(g('close'));
      if (close === null) continue;
      out.push([dateStr, close, mwVol(g('volume')), mwNum(g('open')), mwNum(g('high')), mwNum(g('low'))]);
      if (out.length >= maxRows) break;
    }
    return { data: out };
  }

  /* ---------- 行情概览 ---------- */
  function qNum(s) {
    if (s === null || s === undefined) return null;
    s = String(s).replace(/[\u2212\u2013]/g, '-').replace(/[^0-9.\-]/g, '');
    if (!s || s === '-' || s === '.') return null;
    const v = parseFloat(s);
    return isFinite(v) ? v : null;
  }
  function qScope(doc) { return doc.querySelector('.element--intraday') || doc; }
  function qPrice(doc) {
    const scope = qScope(doc);
    const h2 = scope.querySelector('h2[class*="intraday"][class*="price"]')
      || doc.querySelector('h2[class*="intraday"][class*="price"]');
    if (h2) {
      const bq = h2.querySelector('bg-quote[field="Last" i]') || h2.querySelector('bg-quote:not([class*="change"])');
      if (bq) {
        const raw = bq.getAttribute('data-last-raw');
        let v = qNum(raw);
        if (v !== null) return { raw: raw, value: v, src: 'data-last-raw', el: h2 };
        const t = mwText(bq);
        v = qNum(t);
        if (v !== null) return { raw: t, value: v, src: 'bg-quote', el: h2 };
      }
      const clone = h2.cloneNode(true);
      clone.querySelectorAll('sup').forEach(s => s.remove());
      const t = mwText(clone);
      const v = qNum(t);
      if (v !== null) return { raw: t, value: v, src: 'h2', el: h2 };
    }
    const meta = doc.querySelector('meta[name="price"]');
    if (meta) {
      const c = meta.getAttribute('content');
      const v = qNum(c);
      if (v !== null) return { raw: c, value: v, src: 'meta', el: meta };
    }
    return { raw: null, value: null, src: null, el: null };
  }
  function qTimestamp(doc) {
    const scope = qScope(doc);
    let el = scope.querySelector('bg-quote[field="date" i]');
    let t = mwText(el);
    if (!t) { el = scope.querySelector('[class*="timestamp"][class*="time"]'); t = mwText(el); }
    if (!t) {
      el = doc.querySelector('meta[name="quoteTime"]');
      t = el ? (el.getAttribute('content') || '') : '';
    }
    return { text: t, el: t ? el : null };
  }
  function mwQuoteState(doc, pathname, expectType, complete, live) {
    const ck = mwChallengeKind(doc, live);
    if (ck) return ck;
    const path = (pathname || '').toLowerCase();
    if (path.includes('/search') || path === '/' || path === '/investing' || path === '/investing/') return 'notfound';
    const bc = doc.body ? (doc.body.className || '') : '';
    if (expectType && /(^|\s)symbol--/.test(bc)
      && !new RegExp('(^|\\s)symbol--' + expectType + '(\\s|$)').test(bc)) return 'mismatch';
    const p = qPrice(doc);
    if (p.value !== null) {
      if (complete) return 'ready';
      if (p.src !== 'meta' && mwHasFollowing(p.el, 3)) {
        const ts = qTimestamp(doc);
        if (ts.el && mwHasFollowing(ts.el, 3)) return 'ready';
      }
    }
    if (complete && MW_NOTFOUND_RE.test(mwBodyText(doc, live))) return 'notfound';
    return 'loading';
  }
  function qExtract(doc) {
    const p = qPrice(doc);
    const st = qScope(doc).querySelector('small[class*="status"]');
    return {
      price: p.value, price_raw: p.raw, price_src: p.src,
      ts: qTimestamp(doc).text,
      status: mwText(st),
      company: mwText(doc.querySelector('h1[class*="company"]')),
      body_class: doc.body ? (doc.body.className || '') : ''
    };
  }

  /* ---------- 入口：一次调用返回状态，ready 时附带数据 ---------- */
  self.__mwProbe = function (a) {
    a = a || {};
    try {
      if (mwIsStale()) return { state: 'stale', url: location.href };
      const complete = document.readyState !== 'loading';
      const mode = a.mode === 'table' ? 'table' : 'quote';
      const maxRows = a.maxRows || 5;
      const st = mode === 'table'
        ? mwTableState(document, location.pathname, (a.expectSeg || '').toLowerCase(), maxRows, complete, true)
        : mwQuoteState(document, location.pathname, a.expectType || '', complete, true);
      const out = { state: st, url: location.href, body_class: document.body ? (document.body.className || '') : '' };
      if (st === 'ready') {
        const r = mode === 'table' ? mwParseTable(document, maxRows) : qExtract(document);
        if (mode === 'table') r.path_seg = mwPathSymbolSeg(location.pathname);
        r.url = location.href;
        out.payload = r;
      }
      return out;
    } catch (e) {
      return { state: 'transient', error: String((e && e.message) || e) };
    }
  };
})();