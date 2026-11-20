#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 Firstrade「账户记录」中【系统日期前一天】的买/卖记录,
以 lean_v1 格式追加写入 firstrade_orders.json。

用法:
    python scrape_firstrade_history.py              # 抓昨天
    python scrape_firstrade_history.py --date 2026-11-19   # 指定日期(补抓)
    python scrape_firstrade_history.py --dry-run    # 只打印,不写文件
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ============================ 配置区 ============================
HISTORY_URL = "https://invest.firstrade.com/app/history"
OUTPUT_FILE = Path("/Users/yanzhang/Coding/Financial_System/Modules/firstrade_orders.json")

KEY_PREFIX = "90185542"      # key 前缀
KEY_START = 10000            # 新增记录从 90185542-10000 开始,逐行 +1
ST_VALUE = "F"               # 与其他记录保持一致

AMOUNT_DECIMALS = 0          # 金额保留小数位(按你的要求:整数)
PRICE_DECIMALS = 0           # 价格保留小数位(按你的要求:整数;想保留原精度可改成 2 或 4)

CDP_PORT = 9222
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE = Path("/Users/yanzhang/Coding/Financial_System/.chrome_profile_firstrade")

LOGIN_WAIT_SEC = 180         # 首次需要手动登录时,最多等待多久
ROWS_WAIT_SEC = 20           # 表头出现后,等待数据行加载的最长时间
MAX_PAGES = 10               # 最多翻页数(防死循环)

SIDE_MAP = {                 # 交易类别 -> side;未列出的类别(股息、利息、转账等)一律跳过
    "买进": "buy", "buy": "buy", "bought": "buy",
    "卖出": "sell", "sell": "sell", "sold": "sell",
}
# ===============================================================

# 在浏览器内执行:读取当前页所有行(按 row-id 合并左固定列与滚动列)
EXTRACT_JS = r"""
() => {
  const rows = new Map();
  document.querySelectorAll('.ag-row[row-id]').forEach(r => {
    const id = r.getAttribute('row-id');
    const idx = parseInt(r.getAttribute('aria-rowindex') || '0', 10);
    if (!rows.has(id)) rows.set(id, {id, idx, cells: {}});
    const rec = rows.get(id);
    r.querySelectorAll('[role="gridcell"][col-id]').forEach(c => {
      const colId = c.getAttribute('col-id');
      let v = '';
      if (colId === 'symbol') {
        const b = c.querySelector('[data-ft-symbol]');
        v = b ? b.getAttribute('data-ft-symbol') : (c.innerText || '');
      } else {
        v = c.innerText || '';
      }
      rec.cells[colId] = v.trim();
    });
  });
  return [...rows.values()].sort((a, b) => a.idx - b.idx);
}
"""


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ------------------------- 数值 / 日期处理 -------------------------
def to_decimal(text):
    s = (text or "").replace("−", "-")
    s = re.sub(r"[,$\s]", "", s)
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"无法解析数字: {text!r}")


def round_half_up(d, decimals):
    """四舍五入(非银行家舍入),去掉负号。decimals=0 返回 int,否则 float。"""
    d = abs(d)
    q = Decimal(1).scaleb(-decimals)
    r = d.quantize(q, rounding=ROUND_HALF_UP)
    return int(r) if decimals == 0 else float(r)


def parse_quantity(text):
    d = abs(to_decimal(text))
    return int(d) if d == d.to_integral_value() else float(d)   # 支持碎股


def parse_us_date(text):
    try:
        return datetime.strptime((text or "").strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


# ------------------------- 浏览器连接 -------------------------
def port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_chrome():
    if port_open(CDP_PORT):
        return
    log("未检测到调试模式 Chrome,正在启动(首次需在弹出的窗口里手动登录 Firstrade)…")
    CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [CHROME_BIN,
         f"--remote-debugging-port={CDP_PORT}",
         f"--user-data-dir={CHROME_PROFILE}",
         "--no-first-run", "--no-default-browser-check"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if port_open(CDP_PORT):
            time.sleep(1)
            return
        time.sleep(0.5)
    raise RuntimeError("Chrome 调试端口启动失败,请检查 CHROME_BIN 路径")


# ------------------------- 抓取 -------------------------
def wait_for_grid(page):
    log(f"等待表格加载(如跳转到登录页,请在 {LOGIN_WAIT_SEC}s 内手动登录)…")
    try:
        page.wait_for_selector('.ag-header-cell[col-id="reportDate"]',
                               timeout=LOGIN_WAIT_SEC * 1000)
    except PWTimeout:
        raise RuntimeError("等待表头超时:可能未登录或页面结构已变化")
    # 登录后若停在别的页面,重新进入历史页
    if "/app/history" not in page.url:
        page.goto(HISTORY_URL, wait_until="domcontentloaded")
        page.wait_for_selector('.ag-header-cell[col-id="reportDate"]', timeout=30000)
    try:
        page.wait_for_function(
            "document.querySelectorAll('.ag-row[row-id]').length > 0",
            timeout=ROWS_WAIT_SEC * 1000)
    except PWTimeout:
        log("提示:表格没有数据行(可能该时间范围内无记录)")
    time.sleep(1)   # 让数据渲染稳定


def goto_next_page(page, first_row_id):
    btn = page.locator(
        'button[aria-label*="下一页"], button[aria-label*="Next"], '
        '[data-ref="btNext"], .ag-paging-button[aria-label*="Next"]'
    ).first
    try:
        if btn.count() == 0 or not btn.is_enabled():
            return False
        btn.click()
        page.wait_for_function(
            """(oldId) => {
                const r = document.querySelector('.ag-row[row-id]');
                return r && r.getAttribute('row-id') !== oldId;
            }""", arg=first_row_id, timeout=10000)
        time.sleep(0.5)
        return True
    except Exception as e:
        log(f"翻页失败/无下一页: {e}")
        return False


def scrape_rows(page, target_date):
    """返回目标日期的所有原始行(按页面从上到下的顺序)。"""
    collected, seen = [], set()
    for page_no in range(1, MAX_PAGES + 1):
        rows = page.evaluate(EXTRACT_JS)
        log(f"第 {page_no} 页读取到 {len(rows)} 行")
        oldest = None
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            d = parse_us_date(r["cells"].get("reportDate"))
            if d is None:
                continue
            oldest = d if oldest is None else min(oldest, d)
            if d == target_date:
                collected.append(r)
        # 表格按日期倒序:本页最旧日期已早于目标日 => 不用再翻页
        if oldest is None or oldest < target_date or not rows:
            break
        if not goto_next_page(page, rows[0]["id"]):
            break
    return collected


# ------------------------- 转换 -------------------------
def convert(raw_rows, target_date):
    """原始行 -> lean_v1 记录(不含 key)。"""
    result = []
    for r in raw_rows:
        c = r["cells"]
        tx = (c.get("transStr") or "").strip()
        side = SIDE_MAP.get(tx.lower()) or SIDE_MAP.get(tx)
        symbol = (c.get("symbol") or "").strip().upper()
        if not side:
            log(f"跳过非买卖记录: 类别={tx!r} 代号={symbol!r}")
            continue
        if not symbol:
            log(f"跳过无代号记录: {c}")
            continue
        try:
            result.append({
                "symbol": symbol,
                "side": side,
                "date": target_date.isoformat(),
                "quantity": parse_quantity(c.get("quantity")),
                "amount": round_half_up(to_decimal(c.get("amount")), AMOUNT_DECIMALS),
                "price": round_half_up(to_decimal(c.get("tradePrice")), PRICE_DECIMALS),
                "st": ST_VALUE,
            })
        except ValueError as e:
            log(f"跳过无法解析的行 {c}: {e}")
    return result


# ------------------------- JSON 读写 -------------------------
def load_store():
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data.setdefault("_meta", {})
    data.setdefault("orders", {})
    return data


def fingerprint(o):
    return (o.get("symbol"), o.get("side"), o.get("date"),
            o.get("quantity"), o.get("amount"), o.get("price"))


def key_num(key):
    m = re.fullmatch(rf"{KEY_PREFIX}-(\d+)", key)
    return int(m.group(1)) if m else None


def merge(data, new_records):
    """
    追加新记录,返回实际新增条数。
    幂等:对本脚本生成的记录(编号 >= KEY_START),按"指纹出现次数"去重,
    同一天重复运行不会重复写入,同时允许同一天真实存在的多笔相同成交。
    """
    orders = data["orders"]
    nums = [n for n in (key_num(k) for k in orders) if n is not None and n >= KEY_START]
    next_num = (max(nums) if nums else KEY_START - 1) + 1

    existing = Counter(fingerprint(v) for k, v in orders.items()
                       if (key_num(k) or 0) >= KEY_START)
    added = 0
    for rec in new_records:
        fp = fingerprint(rec)
        if existing[fp] > 0:
            existing[fp] -= 1
            log(f"已存在,跳过: {rec['symbol']} {rec['side']} {rec['quantity']}")
            continue
        key = f"{KEY_PREFIX}-{next_num}"
        orders[key] = rec
        log(f"新增 {key}: {rec}")
        next_num += 1
        added += 1
    return added


def save_store(data):
    now = time.time()
    meta = data["_meta"]
    meta["updated_at"] = now
    meta["updated_at_str"] = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
    meta["count"] = len(data["orders"])
    meta["mode"] = "append"
    meta["schema"] = "lean_v1"

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_FILE.exists():
        shutil.copy2(OUTPUT_FILE, OUTPUT_FILE.with_suffix(".json.bak"))   # 保留上一版备份
    tmp = OUTPUT_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, OUTPUT_FILE)   # 原子替换,避免写一半崩溃导致文件损坏


# ------------------------- 主流程 -------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="指定抓取日期 YYYY-MM-DD,默认=系统日期前一天")
    ap.add_argument("--dry-run", action="store_true", help="只打印结果,不写文件")
    args = ap.parse_args()

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target = (datetime.now() - timedelta(days=1)).date()
    log(f"目标日期: {target}(页面显示格式 {target:%m/%d/%Y})")

    ensure_chrome()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(HISTORY_URL, wait_until="domcontentloaded")
            wait_for_grid(page)
            raw = scrape_rows(page, target)
        finally:
            page.close()   # 只关本脚本打开的标签页,Chrome 与登录态保留

    log(f"目标日期共抓到 {len(raw)} 行原始记录")
    records = convert(raw, target)
    if not records:
        log("没有可写入的买/卖记录,结束(文件未改动)")
        return 0

    data = load_store()
    added = merge(data, records)
    if args.dry_run:
        log(f"[dry-run] 将新增 {added} 条,未写入文件")
        return 0
    if added:
        save_store(data)
        log(f"完成:新增 {added} 条,文件总数 {len(data['orders'])} -> {OUTPUT_FILE}")
    else:
        log("没有新增(均已存在),文件未改动")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"出错: {e}")
        sys.exit(1)