#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tiger_Today.py
使用老虎证券 API 获取最近一个交易日的 OHLCV 数据，写入数据库
业务逻辑完全沿用 YF_Today.py，仅将数据源从 Yahoo 页面替换为 Tiger API。
"""

import sqlite3
import time
import os
import sys
import json
import datetime
import subprocess
import pandas as pd
from tqdm import tqdm
import pandas_market_calendars as mcal
from tigeropen.common.consts import Language

# ================= 路径配置 =================
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")

DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json")
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

# 导入 Tiger 封装
sys.path.append(os.path.join(FINANCIAL_SYSTEM_DIR, "Selenium"))
from Tiger_API import _get_global_fetcher, _normalize_symbol
from tigeropen.common.consts import BarPeriod, QuoteRight

# ================= 批量参数 =================
BATCH_SIZE = 50           # Tiger 单次 get_bars 最多 50 只
SLEEP_BETWEEN_BATCH = 1.1 # 秒，限速
BARS_LIMIT = 3            # 每只拉 3 条，够做日期校验


# =========================================================
# 以下三个函数（get_table_type / create_table_if_not_exists /
# insert_data_to_db）完全沿用 YF_Today.py，保持行为一致
# =========================================================

def get_table_type(sector):
    expanded_sectors = [
        'ETFs', 'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical',
        'Consumer_Defensive', 'Energy', 'Financial_Services', 'Healthcare',
        'Industrials', 'Real_Estate', 'Technology', 'Utilities', 'Crypto'
    ]
    no_volume_sectors = ['Bonds', 'Currencies', 'Commodities', 'Economics']
    if sector in expanded_sectors:
        return "expanded"
    elif sector in no_volume_sectors:
        return "no_volume"
    else:
        return "standard"

def create_table_if_not_exists(cursor, table_name, table_type):
    safe_table_name = f'"{table_name}"'
    if table_type == "expanded":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL, volume INTEGER,
            open REAL, high REAL, low REAL, UNIQUE(date, name)
        )''')
    elif table_type == "no_volume":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL, UNIQUE(date, name)
        )''')
    else:
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL, volume INTEGER, UNIQUE(date, name)
        )''')

def insert_data_to_db(db_path, table_name, data_rows, table_type):
    if not data_rows:
        return False
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    safe_table = f'"{table_name}"'
    try:
        create_table_if_not_exists(cursor, table_name, table_type)
        if table_type == "expanded":
            filtered_data = data_rows
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume, open, high, low)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price=excluded.price, volume=excluded.volume,
                open=excluded.open, high=excluded.high, low=excluded.low;
            """
        elif table_type == "no_volume":
            filtered_data = [(r[0], r[1], r[2]) for r in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price) VALUES (?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET price=excluded.price;
            """
        else:
            filtered_data = [(r[0], r[1], r[2], r[3]) for r in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume) VALUES (?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price=excluded.price, volume=excluded.volume;
            """
        cursor.executemany(upsert_sql, filtered_data)
        conn.commit()
        return True
    except sqlite3.Error as e:
        tqdm.write(f"❌ 数据库写入失败 ({table_name}): {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


# =========================================================
# JSON 管理 & 交易日（沿用 YF_Today.py）
# =========================================================

def load_tasks_from_json(json_path):
    if not os.path.exists(json_path):
        tqdm.write(f"⚠️ 未找到 JSON 文件: {json_path}")
        return {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        tqdm.write(f"⚠️ 读取 JSON 出错: {e}")
        return {}

def load_alias_mapping(json_path):
    """反向映射: {真实代码: 别名} -> {别名: 真实代码}"""
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
            return {v: k for k, v in mapping.items()}
    except Exception as e:
        tqdm.write(f"⚠️ 读取映射文件出错: {e}")
        return {}

def remove_symbol_from_json(json_path, group_name, symbol):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if group_name in data and symbol in data[group_name]:
            data[group_name].remove(symbol)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
    except Exception as e:
        tqdm.write(f"⚠️ 更新 JSON 失败 [{symbol}]: {e}")
    return False

def get_last_valid_trading_date():
    nyse = mcal.get_calendar('NYSE')
    today = datetime.datetime.now().date()
    start_date = today - datetime.timedelta(days=15)
    schedule = nyse.schedule(start_date=start_date, end_date=today)
    valid_days = schedule.index.date
    past_days = [d for d in valid_days if d < today]
    if past_days:
        return past_days[-1].strftime('%Y-%m-%d')
    return None


# =========================================================
# Tiger 批量取数据（替换掉原来的 Selenium + JS 部分）
# =========================================================

def fetch_briefs_batch(fetcher, symbols, batch_size=BATCH_SIZE,
                       sleep_sec=SLEEP_BETWEEN_BATCH):
    """
    用 get_stock_briefs 批量拉当日 OHLCV（不吃历史行情配额）
    返回: {symbol: [(date, open, high, low, close, volume)]}
          为了兼容原来的 pick_row_by_rules，仍然返回 list 结构，只是只有一条
    """
    uniq = list(dict.fromkeys(symbols))
    result = {}
    total_batches = (len(uniq) + batch_size - 1) // batch_size

    for bi, i in enumerate(range(0, len(uniq), batch_size), 1):
        batch = uniq[i:i + batch_size]
        tqdm.write(f"  [{bi}/{total_batches}] 批量拉取 brief {len(batch)} 只...")
        try:
            df = fetcher.quote_client.get_stock_briefs(
                symbols=batch,
                include_hour_trading=False,   # 只要常规盘 OHLCV
                lang=Language.zh_CN
            )
            if df is None or df.empty:
                tqdm.write(f"    ⚠️ 批次 {bi} 返回空")
            else:
                # latest_time 是毫秒时间戳，转美东日期
                if 'latest_time' in df.columns:
                    df['latest_time'] = pd.to_numeric(df['latest_time'], errors='coerce')
                    df['date'] = (
                        pd.to_datetime(df['latest_time'], unit='ms')
                          .dt.tz_localize('UTC')
                          .dt.tz_convert('US/Eastern')
                          .dt.strftime('%Y-%m-%d')
                    )
                else:
                    df['date'] = None

                for _, r in df.iterrows():
                    sym = r.get('symbol')
                    if not sym:
                        continue
                    try:
                        o = float(r.get('open'))
                        h = float(r.get('high'))
                        l = float(r.get('low'))
                        c = float(r.get('latest_price'))
                        v = int(r.get('volume')) if not pd.isna(r.get('volume')) else 0
                        d = r.get('date')
                    except Exception:
                        continue
                    if not (o and h and l and c and d):
                        continue
                    result[sym] = [(d, o, h, l, c, v)]
        except Exception as e:
            tqdm.write(f"    ❌ 批次 {bi} 失败: {e}")

        if bi < total_batches:
            time.sleep(sleep_sec)

    return result


# =========================================================
# 日期校验逻辑（移植自 YF_Today.py 的规则 1/2/3）
# =========================================================

def pick_row_by_rules(symbol, bars, last_valid_date):
    if not bars:
        return None, "无数据"
    row = bars[0]
    row_date = row[0]

    if last_valid_date is None:
        return row, None

    if row_date == last_valid_date:
        return row, None

    # brief 日期>预期：说明今天在盘中/刚收盘；<预期：说明停牌或脚本跑得太早
    if row_date > last_valid_date:
        tqdm.write(f"⚠️ [{symbol}] brief 日期 {row_date} > 预期 {last_valid_date}，改写为预期日期。")
        lst = list(row); lst[0] = last_valid_date
        return tuple(lst), None

    return None, f"brief 日期 {row_date} < 预期 {last_valid_date}，数据未更新"


# =========================================================
# 主流程
# =========================================================

def run():
    tasks_dict = load_tasks_from_json(SECTORS_JSON_PATH)
    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)

    last_valid_date = get_last_valid_trading_date()
    if last_valid_date:
        tqdm.write(f"📅 最近有效开盘日: {last_valid_date}")
    else:
        tqdm.write("⚠️ 无法计算最近有效开盘日，将使用接口原始日期。")

    # 展平任务列表
    task_list = []
    for group, symbols in tasks_dict.items():
        for sym in symbols:
            task_list.append((sym, group))

    if not task_list:
        tqdm.write("✅ Empty JSON 文件中没有待抓取的 Symbol，任务结束。")
        run_check_yesterday_if_empty()
        return

    tqdm.write(f"共加载 {len(task_list)} 个待抓取任务。\n")

    # 初始化 Tiger
    try:
        fetcher = _get_global_fetcher()
    except Exception as e:
        tqdm.write(f"❌ Tiger 初始化失败: {e}")
        return

    # 建立映射：Tiger 真实代码 -> [(原始 symbol, group), ...]
    # 之所以用列表，是为了支持一个真实代码对应多个别名的情况（极少）
    scrape_to_tasks = {}
    for orig, group in task_list:
        # 两步转译：JSON 别名映射 -> Tiger 内置符号规范化
        intermediate = alias_to_symbol.get(orig, orig)
        scrape_sym = _normalize_symbol(intermediate)
        scrape_to_tasks.setdefault(scrape_sym, []).append((orig, group))

    scrape_symbols = list(scrape_to_tasks.keys())
    tqdm.write(f"▶ 将批量请求 {len(scrape_symbols)} 个 Tiger 代码...\n")

    bars_map = fetch_briefs_batch(fetcher, scrape_symbols)
    tqdm.write(f"\n✅ 拿到 {len(bars_map)} / {len(scrape_symbols)} 只 symbol 的数据\n")

    # 遍历原始任务，从 bars_map 里查，走日期校验，写 DB
    success_cnt = fail_cnt = skip_cnt = 0
    pbar = tqdm(task_list, desc="写入进度")
    for orig_symbol, group in pbar:
        pbar.set_description(f"处理: {orig_symbol} [{group}]")

        intermediate = alias_to_symbol.get(orig_symbol, orig_symbol)
        scrape_sym = _normalize_symbol(intermediate)
        bars = bars_map.get(scrape_sym)

        if not bars:
            tqdm.write(f"❌ [{orig_symbol}] Tiger 未返回数据，跳过（保留在 JSON 中）")
            fail_cnt += 1
            continue

        selected, err = pick_row_by_rules(orig_symbol, bars, last_valid_date)
        if selected is None:
            tqdm.write(f"⚠️ [{orig_symbol}] {err}")
            skip_cnt += 1
            continue

        # selected: (date, open, high, low, close, volume)
        date, o, h, l, c, v = selected

        # 数据库统一入参格式: (date, name, price, volume, open, high, low)
        # price 用 close
        db_row = (date, orig_symbol, c, v, o, h, l)
        table_type = get_table_type(group)

        if insert_data_to_db(DB_PATH, group, [db_row], table_type):
            tqdm.write(f"✅ [{orig_symbol}] 写入 {group} ({date})")
            remove_symbol_from_json(SECTORS_JSON_PATH, group, orig_symbol)
            success_cnt += 1
        else:
            fail_cnt += 1

    tqdm.write(f"\n🎉 完成: 成功 {success_cnt} / 失败 {fail_cnt} / 跳过 {skip_cnt}")
    run_check_yesterday_if_empty()


def run_check_yesterday_if_empty():
    final_tasks = load_tasks_from_json(SECTORS_JSON_PATH)
    is_empty = True
    if final_tasks:
        for group, symbols in final_tasks.items():
            if len(symbols) > 0:
                is_empty = False
                break
    if is_empty:
        print("✅ Sectors_empty.json 已全部清空，开始执行 Check_yesterday.py...")
        try:
            subprocess.run(
                [sys.executable, CHECK_YESTERDAY_SCRIPT_PATH, "--ignore_sectors"],
                check=True, capture_output=True, text=True, encoding='utf-8'
            )
            print("✅ Check_yesterday.py 执行完毕。")
        except Exception as e:
            print(f"❌ 调用 Check_yesterday 出错: {e}")
    else:
        print("⚠️ Sectors_empty.json 中仍有未完成的任务，跳过执行 Check_yesterday.py。")


if __name__ == "__main__":
    run()