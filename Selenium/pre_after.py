#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前/盘后涨跌幅排行（从小到大，取前 20）
涨跌幅 = (最新价 - 当日收盘价) / 当日收盘价
收盘价来自本地 SQLite 数据库（每个 symbol 最新日期的 price）
"""

import os
import sys
import json
import sqlite3

# ==================== 配置区 ====================
BASE_CODING_DIR = "/Users/yanzhang/Coding"
JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System/Modules/Sectors_All.json")
DB_PATH   = os.path.join(BASE_CODING_DIR, "Database/Finance.db")

TARGET_SECTORS = [
    "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
    "Industrials", "Real_Estate", "Technology", "Utilities",
]

TOP_N = 20

# ==================== 导入 Tiger_API ====================
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Selenium"))
try:
    from Tiger_API import _get_global_fetcher, _normalize_symbol
except ImportError as e:
    print(f"导入 Tiger_API 失败: {e}")
    sys.exit(1)

# ==================== 工具函数 ====================
def load_sector_map(json_path, sectors):
    """
    返回 {sector_name: [symbols...]} 以及全部 symbol 去重列表
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sector_map = {}
    seen, all_symbols = set(), []
    for sec in sectors:
        syms = data.get(sec, []) or []
        if not syms:
            continue
        sector_map[sec] = syms
        for s in syms:
            if s not in seen:
                seen.add(s)
                all_symbols.append(s)
    return sector_map, all_symbols


def fetch_closes_from_db(db_path, sector_map):
    """
    从 SQLite 拉取每个 symbol 在各自 sector 表中最新日期的 close(=price)
    返回 {symbol: close_price}
    """
    result = {}
    if not sector_map:
        return result

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        for sec, symbols in sector_map.items():
            if not symbols:
                continue

            placeholders = ",".join(["?"] * len(symbols))
            # 注意：表名不能用参数化占位符，这里直接拼接
            # 因为 sec 来自我们自己定义的白名单 TARGET_SECTORS，所以安全
            sql = f"""
                SELECT name, price
                FROM "{sec}"
                WHERE (name, date) IN (
                    SELECT name, MAX(date)
                    FROM "{sec}"
                    WHERE name IN ({placeholders})
                    GROUP BY name
                )
            """
            try:
                cur.execute(sql, symbols)
                rows = cur.fetchall()
                got = 0
                for name, price in rows:
                    if price is not None and price > 0:
                        result[name] = float(price)
                        got += 1
                print(f"  [{sec}] {got}/{len(symbols)} 只获取到收盘价")
            except sqlite3.Error as e:
                print(f"  ❌ 查询表 {sec} 失败: {e}")
    finally:
        conn.close()

    return result


# ==================== 主逻辑 ====================
def main():
    sector_map, symbols = load_sector_map(JSON_PATH, TARGET_SECTORS)
    if not symbols:
        print("⚠️ 指定板块下没有任何 symbol，请检查 JSON。")
        return
    print(f"共读取 {len(symbols)} 个 symbol\n")

    fetcher = _get_global_fetcher()

    # 1) 批量拿实时价（含盘前/盘后）
    print("▶ Step 1: 批量拉取实时价（含盘前/盘后）...")
    latest_prices = fetcher.get_realtime_prices(symbols)
    print(f"✅ 最新价: {len(latest_prices)} / {len(symbols)}\n")

    # 2) 从数据库拿收盘价（每个 symbol 最新日期的 price）
    print("▶ Step 2: 从本地数据库读取当日收盘价...")
    close_map = fetch_closes_from_db(DB_PATH, sector_map)
    print(f"✅ 收盘价: {len(close_map)} / {len(symbols)}\n")

    # 3) 计算涨跌幅
    changes, skipped = [], 0
    for sym in symbols:
        norm = _normalize_symbol(sym)
        latest = latest_prices.get(norm) or latest_prices.get(sym)
        close_price = close_map.get(sym)
        
        # 逻辑判断：如果最新价或收盘价缺失，则跳过
        if latest is None or latest <= 0 or close_price is None or close_price <= 0:
            skipped += 1
            continue
            
        # 计算公式：(最新价 - 收盘价) / 收盘价
        pct = (latest - close_price) / close_price * 100.0
        changes.append({
            "symbol": sym,
            "latest": latest,
            "close": close_price,
            "pct": pct,
        })

    if not changes:
        print("没有可计算的结果。")
        return

    # 4) 升序排序，取前 N
    changes.sort(key=lambda x: x["pct"])

    print("\n" + "=" * 78)
    print(f"  涨跌幅从小到大 · 前 {TOP_N}  (有效 {len(changes)}，跳过 {skipped})")
    print("=" * 78)
    print(f"{'#':<4}{'Symbol':<10}{'最新价':>12}{'当日收盘':>14}{'涨跌幅%':>12}")
    print("-" * 78)
    for i, it in enumerate(changes[:TOP_N], 1):
        print(f"{i:<4}{it['symbol']:<10}"
              f"{it['latest']:>12.4f}"
              f"{it['close']:>14.4f}"
              f"{it['pct']:>+12.4f}")
    print("=" * 78)


if __name__ == "__main__":
    main()