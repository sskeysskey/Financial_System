#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前/盘后涨跌幅排行（从小到大，取前 20）
涨跌幅 = (最新价 - 当日收盘价) / 当日收盘价
"""

import os
import sys
import json
import time

# ==================== 配置区 ====================
BASE_CODING_DIR = "/Users/yanzhang/Coding"
JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System/Modules/Sectors_All.json")

TARGET_SECTORS = [
    "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
    "Industrials", "Real_Estate", "Technology", "Utilities",
]

TOP_N = 20
BATCH_SIZE = 50          # 老虎 get_bars 单次最多 50 只
SLEEP_BETWEEN_BATCH = 1.1 # 秒；保证每分钟 < 60 次

# ==================== 导入 Tiger_API ====================
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Selenium"))
try:
    from Tiger_API import _get_global_fetcher, _normalize_symbol
except ImportError as e:
    print(f"导入 Tiger_API 失败: {e}")
    sys.exit(1)

# ==================== 工具函数 ====================
def load_symbols(json_path, sectors):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    seen, result = set(), []
    for sec in sectors:
        for sym in data.get(sec, []):
            if sym not in seen:
                seen.add(sym)
                result.append(sym)
    return result


def fetch_closes_batch(fetcher, symbols, batch_size=50, sleep_sec=1.1):
    """
    批量拉取多只股票的"当日收盘价" (close)
    """
    # 归一化 & 反向映射，方便最后把结果 key 还原成原始 symbol
    norm_list = [_normalize_symbol(s) for s in symbols]
    norm_to_orig = {}
    for orig, norm in zip(symbols, norm_list):
        norm_to_orig.setdefault(norm, orig)

    result = {}
    total_batches = (len(norm_list) + batch_size - 1) // batch_size

    for bi, i in enumerate(range(0, len(norm_list), batch_size), 1):
        batch = norm_list[i:i + batch_size]
        print(f"  [{bi}/{total_batches}] 拉取 {len(batch)} 只股票的收盘价...")
        try:
            # 使用 get_stock_briefs 获取实时行情，其中包含 close
            briefs = fetcher.quote_client.get_stock_briefs(
                symbols=batch,
                include_hour_trading=False, # 这里不需要盘前盘后，只要昨收
                lang='zh_CN'
            )
            
            if briefs is not None and not briefs.empty:
                for _, row in briefs.iterrows():
                    sym = row.get('symbol')
                    # 修改点：这里获取 'close' 字段
                    close_price = row.get('close')
                    
                    if close_price is not None and close_price > 0:
                        orig = norm_to_orig.get(sym, sym)
                        result[orig] = float(close_price)
            else:
                print(f"    ⚠️ 批次 {bi} 返回空")
        except Exception as e:
            print(f"    ❌ 批次 {bi} 失败: {e}")

        # 最后一批不用睡
        if bi < total_batches:
            time.sleep(sleep_sec)

    return result


# ==================== 主逻辑 ====================
def main():
    symbols = load_symbols(JSON_PATH, TARGET_SECTORS)
    if not symbols:
        print("⚠️ 指定板块下没有任何 symbol，请检查 JSON。")
        return
    print(f"共读取 {len(symbols)} 个 symbol\n")

    fetcher = _get_global_fetcher()

    # 1) 批量拿实时价（含盘前/盘后）
    print("▶ Step 1: 批量拉取实时价（含盘前/盘后）...")
    latest_prices = fetcher.get_realtime_prices(symbols)
    print(f"✅ 最新价: {len(latest_prices)} / {len(symbols)}\n")

    # 2) 批量拿收盘价
    print("▶ Step 2: 批量拉取当日收盘价...")
    close_map = fetch_closes_batch(fetcher, symbols)
    print(f"✅ 收盘价: {len(close_map)} / {len(symbols)}\n")

    # 3) 计算涨跌幅
    changes, skipped = [], 0
    print("▶ Step 3: 计算涨跌幅并获取 PE (可能较慢)...")
    
    for sym in symbols:
        norm = _normalize_symbol(sym)
        latest = latest_prices.get(norm) or latest_prices.get(sym)
        close_price = close_map.get(sym)
        
        # 逻辑判断：如果最新价或收盘价缺失，则跳过
        if latest is None or latest <= 0 or close_price is None or close_price <= 0:
            skipped += 1
            continue
            
        # --- 新增：获取 PE ---
        pe = fetcher.get_financial_data(sym)
        # --------------------
            
        pct = (latest - close_price) / close_price * 100.0
        changes.append({
            "symbol": sym,
            "latest": latest,
            "close": close_price,
            "pct": pct,
            "pe": pe if pe is not None else 0.0 # 处理 None 情况
        })

    if not changes:
        print("没有可计算的结果。")
        return

    # 4) 升序排序，取前 N
    changes.sort(key=lambda x: x["pct"])

    print("\n" + "=" * 78)
    print(f"  涨跌幅从小到大 · 前 {TOP_N}  (有效 {len(changes)}，跳过 {skipped})")
    print("=" * 78)
    print(f"{'#':<4}{'Symbol':<10}{'最新价':>12}{'当日收盘':>14}{'涨跌幅%':>12}{'PE(TTM)':>12}")
    print("-" * 85) # 调整长度
    for i, it in enumerate(changes[:TOP_N], 1):
        print(f"{i:<4}{it['symbol']:<10}"
              f"{it['latest']:>12.4f}"
              f"{it['close']:>14.4f}"
              f"{it['pct']:>+12.4f}"
              f"{it['pe']:>12.2f}") # 格式化 PE 输出
    print("=" * 78)


if __name__ == "__main__":
    main()