#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import sqlite3
import time
import sys
import json
import datetime
import subprocess
import pandas_market_calendars as mcal
from tqdm import tqdm

# 导入你的 Tiger API 封装类 (确保 Tiger_API.py 在同级目录或 Python 路径中)
from Tiger_API import TigerDataFetcher

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")

# 基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")

# 具体业务文件路径
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json")
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

# --- 老虎证券 API 配置 (请根据实际情况确认) ---
PRIVATE_KEY_PATH = '/Users/yanzhang/Downloads/tiger.pem'
TIGER_ID = '20150215'
ACCOUNT = '21638488022016545'

# ================= 1. 数据库与 JSON 操作 =================

def get_table_type(sector):
    """根据分组判断表结构类型"""
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
    """确保数据库表存在，根据 table_type 动态创建表结构"""
    safe_table_name = f'"{table_name}"'
    
    if table_type == "expanded":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER,
            open REAL,
            high REAL,
            low REAL,
            UNIQUE(date, name)
        )
        ''')
    elif table_type == "no_volume":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            UNIQUE(date, name)
        )
        ''')
    else: # standard
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER,
            UNIQUE(date, name)
        )
        ''')

def insert_data_to_db(db_path, table_name, data_rows, table_type):
    """将抓取的数据直接写入数据库"""
    if not data_rows:
        return False
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    safe_table = f'"{table_name}"'
    try:
        create_table_if_not_exists(cursor, table_name, table_type)
        
        filtered_data = []
        if table_type == "expanded":
            filtered_data = data_rows
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume, open, high, low)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price = excluded.price,
                volume = excluded.volume,
                open = excluded.open,
                high = excluded.high,
                low = excluded.low;
            """
        elif table_type == "no_volume":
            filtered_data = [(row[0], row[1], row[2]) for row in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price)
            VALUES (?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price = excluded.price;
            """
        else: # standard
            filtered_data = [(row[0], row[1], row[2], row[3]) for row in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price = excluded.price,
                volume = excluded.volume;
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
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
            return {v: k for k, v in mapping.items()}
    except Exception as e:
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

# ================= 2. 核心抓取逻辑 =================

def get_last_valid_trading_date():
    """获取美股最近的一个有效开盘日（严格小于今天）"""
    nyse = mcal.get_calendar('NYSE')
    today = datetime.datetime.now().date()
    start_date = today - datetime.timedelta(days=15)
    
    schedule = nyse.schedule(start_date=start_date, end_date=today)
    valid_days = schedule.index.date
    
    past_days = [d for d in valid_days if d < today]
    
    if past_days:
        return past_days[-1].strftime('%Y-%m-%d')
    return None

def fetch_and_process_data():
    # 1. 加载任务和映射表
    tasks_dict = load_tasks_from_json(SECTORS_JSON_PATH)
    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)
    
    last_valid_date = get_last_valid_trading_date()
    if last_valid_date:
        tqdm.write(f"📅 计算得出的最近有效开盘日为: {last_valid_date}")
    else:
        tqdm.write("⚠️ 无法计算最近有效开盘日，将使用 API 返回的最新日期。")
    
    task_list = []
    for group, symbols in tasks_dict.items():
        for sym in symbols:
            task_list.append((sym, group))
            
    if not task_list:
        tqdm.write("✅ JSON 文件中没有待抓取的 Symbol，任务结束。")
        # run_check_yesterday_if_empty()
        return

    tqdm.write(f"共加载 {len(task_list)} 个待抓取任务。")

    # 2. 初始化 Tiger API 客户端
    try:
        fetcher = TigerDataFetcher(
            private_key_path=PRIVATE_KEY_PATH,
            tiger_id=TIGER_ID,
            account=ACCOUNT
        )
    except Exception as e:
        tqdm.write(f"❌ Tiger API 初始化失败: {e}")
        return

    # 3. 遍历任务获取数据
    pbar = tqdm(task_list, desc="总体进度", position=0)
    for symbol, group in pbar:
        table_type = get_table_type(group)
        
        # 映射真实 Symbol
        if symbol in alias_to_symbol:
            scrape_symbol = alias_to_symbol[symbol]
            pbar.set_description(f"处理中: {symbol} (转译为 {scrape_symbol}) [{group}]")
        else:
            scrape_symbol = symbol
            pbar.set_description(f"处理中: {symbol} [{group}]")
        
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # 获取最近 5 天的 K 线数据，确保能覆盖到 last_valid_date
                bars_df = fetcher.get_historical_bars(scrape_symbol, days=5)
                
                if bars_df.empty:
                    raise Exception("获取到的K线数据为空")

                selected_row_data = None

                # ================= 日期校验与数据提取逻辑 =================
                if last_valid_date:
                    # 尝试寻找与 last_valid_date 完全匹配的行
                    match_df = bars_df[bars_df['date'] == last_valid_date]
                    
                    if not match_df.empty:
                        selected_row_data = match_df.iloc[-1].copy()
                    else:
                        # 如果没有匹配的日期，取最新的一条数据，并强行修改日期 (兼容原 YF_Today 逻辑)
                        selected_row_data = bars_df.iloc[-1].copy()
                        tqdm.write(f"⚠️ [{symbol}] API 未返回 {last_valid_date} 的数据，临时使用最新数据({selected_row_data['date']})并修改日期写入。")
                        selected_row_data['date'] = last_valid_date
                else:
                    # 无法计算有效日期时，直接取最新一条
                    selected_row_data = bars_df.iloc[-1].copy()
                # ======================================================

                # 提取并格式化数据 (date, name, price, volume, open, high, low)
                # 注意：Tiger API 返回的收盘价字段是 'close'
                date_val = selected_row_data['date']
                price_val = float(selected_row_data['close'])
                volume_val = int(selected_row_data.get('volume', 0))
                open_val = float(selected_row_data.get('open', price_val))
                high_val = float(selected_row_data.get('high', price_val))
                low_val = float(selected_row_data.get('low', price_val))
                
                formatted_row = (date_val, symbol, price_val, volume_val, open_val, high_val, low_val)

                # 写入数据库
                if insert_data_to_db(DB_PATH, group, [formatted_row], table_type):
                    tqdm.write(f"[{symbol}] 成功写入最新 1 条数据 ({date_val}) 到 {group} 表。")
                    remove_symbol_from_json(SECTORS_JSON_PATH, group, symbol)
                    break # 成功，跳出重试循环
                else:
                    raise Exception("数据库写入失败")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1) # API 请求失败稍微停顿一下
                else:
                    tqdm.write(f"❌ [{symbol}] 抓取失败 (已重试 {max_retries} 次): {str(e)[:100]}")
        
    tqdm.write("🎉 所有任务执行完毕。")

    # 4. 检查 JSON 是否为空
    # run_check_yesterday_if_empty()

def run_check_yesterday_if_empty():
    """检查 JSON 文件是否已清空，如果清空则执行 Check_yesterday.py"""
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
            subprocess.run([sys.executable, CHECK_YESTERDAY_SCRIPT_PATH, "--ignore_sectors"], check=True, capture_output=True, text=True, encoding='utf-8')
            print("✅ Check_yesterday.py 执行完毕。")
        except Exception as e:
            print(f"❌ 调用 Check_yesterday 出错: {e}")
    else:
        print("⚠️ Sectors_empty.json 中仍有未完成的任务，跳过执行 Check_yesterday.py。")

if __name__ == "__main__":
    fetch_and_process_data()