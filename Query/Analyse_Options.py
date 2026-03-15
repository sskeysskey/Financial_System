import pandas as pd
import numpy as np
import os
import datetime
import glob
import subprocess
import json
import sqlite3
import sys
from datetime import timedelta
from pandas.tseries.holiday import USFederalHolidayCalendar

# ==========================================
# 全局配置区域 (Configuration)
# ==========================================

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 路径配置 ---

# 备份文件所在的文件夹路径 (自动模式用)
BACKUP_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")

# 【修改】将输出路径改为 Database 目录
OUTPUT_DIR = os.path.join(BASE_CODING_DIR, "Database")
OUTPUT_FILENAME = 'Options_Change.csv'

# 【修改】文件名改为 History，暗示这是一个累加的文件
LARGE_PRICE_FILENAME = 'Options_History.csv' 

# JSON 映射文件路径
SECTORS_JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")

# SQLite 数据库路径 (共用)
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
TABLE_NAME = 'Options'

# 调试输出路径 (b.py逻辑用)
OUTPUT_DEBUG_PATH = os.path.join(USER_HOME, "Downloads", "3.txt")

# --- 算法参数配置 ---

# 【策略 1：每个 Symbol 的 Calls 和 Puts 各保留前多少名 (用于 Part A 过滤和 Part B 策略1)】
TOP_N = 200000

# [策略 2 (IV 计算) 参数配置]
IV_TOP_N = 100000           # 【修改】取排名前 30 名
IV_DIVISOR = 7.0        # 最终汇总时的除数

# 以下两个参数在逻辑移除后将不再起作用，但保留定义以防报错
IV_THRESHOLD = 20.0     
IV_ADJUSTMENT = 1.0     # 设为 1.0 相当于不调整

# [策略 3] 金额阈值，默认1000万 (10,000,000)
LARGE_PRICE_THRESHOLD = 10000000 

# a.py 逻辑参数: 是否考虑新增的数据 (B有A无)
INCLUDE_NEW_ROWS = True

# 策略1： 逻辑参数: 权重幂次配置 (1=线性, 2=平方...)
WEIGHT_POWER = 1

# [策略 3 参数配置]
STRAT3_COEFF_A = 0.5  # 系数 A
STRAT3_COEFF_B = 0.05  # 系数 B

# b.py 调试 Symbol
DEBUG_SYMBOL = ""

# --- 模式切换配置 ---

# True: 手动模式 (使用下方指定的两个具体文件)
# False: 自动模式 (自动寻找 BACKUP_DIR 下最新的两个文件)
USE_MANUAL_MODE = False

# 手动模式下的文件路径
MANUAL_FILE_OLD = os.path.join(BACKUP_DIR, 'Options_251224.csv')
MANUAL_FILE_NEW = os.path.join(BACKUP_DIR, 'Options_251227.csv')

# ==========================================
# [Part A] 辅助函数与核心处理 (原 a.py)
# ==========================================

def load_symbol_sector_map(json_path):
    """加载 JSON 并反转为 Symbol -> Sector 的字典"""
    if not os.path.exists(json_path):
        print(f"⚠️ 警告: 找不到 JSON 映射文件: {json_path}")
        return {}
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        symbol_map = {}
        for sector, symbols in data.items():
            for sym in symbols:
                symbol_map[sym.upper()] = sector
        return symbol_map
    except Exception as e:
        print(f"⚠️ 读取 JSON 失败: {e}")
        return {}

def get_latest_prices(symbols, symbol_sector_map, db_path):
    """
    批量获取 Symbol 在系统日期之前（不含今天）的最新价格。
    如果昨天没数据，自动向前追溯。
    """
    if not os.path.exists(db_path):
        print(f"⚠️ 警告: 找不到数据库文件: {db_path}")
        return {}

    price_dict = {}
    conn = None
    
    # 获取系统今天的日期字符串 (格式: YYYY-MM-DD)
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    
    try:
        conn = sqlite3.connect(db_path, timeout=60.0)
        cursor = conn.cursor()

        # 按板块分组查询，提高效率
        sector_groups = {}
        for sym in symbols:
            sym_upper = sym.upper()
            lookup_sym = 'VIX' if sym_upper == '^VIX' else sym_upper
            sector = symbol_sector_map.get(lookup_sym)
            
            if sector:
                if sector not in sector_groups:
                    sector_groups[sector] = []
                sector_groups[sector].append(lookup_sym)

        print(f"正在从数据库获取 {len(symbols)} 个 Symbol 在 {today_str} 之前的最新价格...")

        for sector, sym_list in sector_groups.items():
            if not sym_list:
                continue

            # 构建占位符
            placeholders = ','.join(['?'] * len(sym_list))
            
            # 修改后的 SQL 逻辑：
            # 1. 增加 WHERE date < ? 确保不取今天的数据
            # 2. 通过 MAX(date) 自动获取距离今天最近的那个历史日期
            query = f"""
                SELECT t1.name, t1.price
                FROM "{sector}" t1
                JOIN (
                    SELECT name, MAX(date) as max_date
                    FROM "{sector}"
                    WHERE name IN ({placeholders}) AND date < ?
                    GROUP BY name
                ) t2 ON t1.name = t2.name AND t1.date = t2.max_date
            """
            
            try:
                # 将 sym_list 和 today_str 传入执行
                params = sym_list + [today_str]
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                for name, price in rows:
                    name_upper = name.upper()
                    price_dict[name_upper] = price
                    if name_upper == 'VIX':
                        price_dict['^VIX'] = price
            except Exception as e:
                print(f" ⚠️ 查询表 '{sector}' 出错: {e}")

    except Exception as e:
        print(f"数据库连接或查询总错误: {e}")
    finally:
        if conn:
            conn.close()
            
    return price_dict

def process_options_change(file_old, file_new, top_n=50, include_new=True):
    """
    处理期权变化逻辑。
    修改：确保 Price > 1000万的数据在 Top_N 过滤前被提取。
    """
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 开始处理文件比对...")
    print(f"旧文件: {os.path.basename(file_old)}")
    print(f"新文件: {os.path.basename(file_new)}")

    if not os.path.exists(file_old) or not os.path.exists(file_new):
        print("错误: 找不到文件。")
        return None

    try:
        # 1. 在读取时包含 Last Price
        dtype_dict = {'Symbol': str, 'Expiry Date': str, 'Type': str, 'Strike': str, 'Last Price': str}
        df_old = pd.read_csv(file_old, dtype=dtype_dict)
        df_new = pd.read_csv(file_new, dtype=dtype_dict)
    except Exception as e:
        print(f"读取错误: {e}")
        return None

    # 数据清洗
    df_old.columns = df_old.columns.str.strip()
    df_new.columns = df_new.columns.str.strip()
    
    # --- 推荐的清洗方式 ---
    def clean_numeric(val):
        if pd.isna(val): return 0.0
        if isinstance(val, (int, float)): return float(val)
        try: return float(str(val).replace(',', '').strip())
        except: return 0.0

    # 统一清洗两个文件的数值列
    for df_temp in [df_old, df_new]:
        # 清洗 Open Interest
        df_temp['Open Interest'] = df_temp.get('Open Interest', pd.Series(0)).apply(clean_numeric)
        
        # --- 【修复代码开始】 ---
        # 强制确保 'Last Price' 字段存在。
        # 如果旧文件缺少此字段，补 0.0，这样 merge 时才会产生 Last Price_old 和 Last Price_new
        if 'Last Price' not in df_temp.columns:
            df_temp['Last Price'] = 0.0
        else:
            df_temp['Last Price'] = df_temp['Last Price'].apply(clean_numeric)

    # 过滤全新日期
    print("正在过滤全新出现的 Expiry Date ...")
    valid_old_dates = set(zip(df_old['Symbol'], df_old['Expiry Date']))
    df_new['_date_key'] = list(zip(df_new['Symbol'], df_new['Expiry Date']))
    rows_before = len(df_new)
    df_new = df_new[df_new['_date_key'].isin(valid_old_dates)].copy()
    print(f"已剔除 {rows_before - len(df_new)} 行全新日期数据。")
    df_new.drop(columns=['_date_key'], inplace=True)

    old_expiry_set = set(zip(df_old['Symbol'], df_old['Expiry Date']))
    
    # 合并 (Last Price 会变成 Last Price_new)
    key_columns = ['Symbol', 'Expiry Date', 'Type', 'Strike']
    merged = pd.merge(df_old, df_new, on=key_columns, how='outer', suffixes=('_old', '_new'), indicator=True)
    
    # 过滤逻辑
    merged = merged[merged['_merge'] != 'left_only'].copy()
    if not include_new:
        merged = merged[merged['_merge'] == 'both'].copy()
        
    merged['Open Interest_old'] = merged['Open Interest_old'].fillna(0)
    merged['Open Interest_new'] = merged['Open Interest_new'].fillna(0)
    merged['Last Price_new'] = merged['Last Price_new'].fillna(0)
    
    # 剔除旧持仓为0的
    merged = merged[merged['Open Interest_old'] != 0].copy()
    
    # 计算 1-Day Chg 和 Price
    merged['1-Day Chg'] = merged['Open Interest_new'] - merged['Open Interest_old']
    merged = merged[merged['1-Day Chg'] >= 0].copy()

    # --- 【新增步骤】计算 Price 列 ---
    # 公式：1-Day Chg * Last Price (来自最新文件)
    merged['Price'] = merged['1-Day Chg'] * merged['Last Price_new']

    # --- 【策略 3：大额异动追踪逻辑提前】 ---
    # 在这里，merged 包含所有变动大于0的行，尚未进行 TOP_N 过滤
    
    large_price_raw = merged[merged['Price'] > LARGE_PRICE_THRESHOLD].copy()
    if not large_price_raw.empty:
        # 为大额数据准备 Distance
        unique_l_symbols = large_price_raw['Symbol'].unique().tolist()
        symbol_map_l = load_symbol_sector_map(SECTORS_JSON_PATH)
        price_map_l = get_latest_prices(unique_l_symbols, symbol_map_l, DB_PATH)

        def calc_dist_temp(row):
            sym = row['Symbol'].upper()
            try: strike_val = float(str(row['Strike']).replace(',', '').strip())
            except: return "N/A"
            p_val = price_map_l.get(sym)
            if p_val is None or p_val == 0: return "N/A"
            return f"{((strike_val - p_val) / p_val) * 100:.2f}%"

        large_price_raw['Distance'] = large_price_raw.apply(calc_dist_temp, axis=1)
        
        # 整理格式
        current_date_str = datetime.datetime.now().strftime('%Y-%m-%d')
        large_price_raw['Run_Date'] = current_date_str
        large_price_raw = large_price_raw.rename(columns={'Open Interest_new': 'Open Interest'})
        
        l_cols = ['Run_Date', 'Symbol', 'Type', 'Expiry Date', 'Strike', 'Distance', 'Open Interest', '1-Day Chg', 'Price']
        large_price_final = large_price_raw[l_cols].copy()
        large_price_final['Symbol'] = large_price_final['Symbol'].replace('^VIX', 'VIX')

        # 写入历史库文件
        large_price_path = os.path.join(OUTPUT_DIR, LARGE_PRICE_FILENAME)
        if os.path.exists(large_price_path):
            try:
                history_df = pd.read_csv(large_price_path)
                if 'Run_Date' in history_df.columns:
                    history_clean = history_df[history_df['Run_Date'] != current_date_str]
                    final_save_df = pd.concat([history_clean, large_price_final], ignore_index=True)
                else:
                    final_save_df = pd.concat([history_df, large_price_final], ignore_index=True)
                final_save_df.to_csv(large_price_path, index=False)
                print(f"🔥 大额变动历史库已更新 (全量监控): {large_price_path} (今日: {len(large_price_final)} 条)")
            except Exception as e:
                print(f"⚠️ 历史库写入失败: {e}")
        else:
            large_price_final.to_csv(large_price_path, index=False)
            print(f"🔥 大额变动历史库已创建: {large_price_path}")

    # --- 【回到原有逻辑：执行 TOP_N 过滤用于主表和评分】 ---
    
    # 标记 new (仅针对即将进入 Top N 的数据)
    if include_new and not merged.empty:
        def mark_new_rows(row):
            if row['_merge'] == 'right_only':
                if (row['Symbol'], row['Expiry Date']) not in old_expiry_set:
                    row['Expiry Date'] = str(row['Expiry Date']) + " new"
                else:
                    row['Strike'] = str(row['Strike']) + " new"
            return row
        merged = merged.apply(mark_new_rows, axis=1)

    # 排序取 Top N
    merged['Abs_Chg'] = merged['1-Day Chg'].abs()
    merged['Type_Rank'] = merged['Type'].str.lower().apply(lambda x: 0 if 'call' in x else 1)
    
    final_rows = []
    if not merged.empty:
        all_symbols = merged['Symbol'].unique()
        for symbol in all_symbols:
            symbol_df = merged[merged['Symbol'] == symbol]
            for type_val in symbol_df['Type'].unique():
                sub_df = symbol_df[symbol_df['Type'] == type_val]
                sub_df_sorted = sub_df.sort_values(by='Abs_Chg', ascending=False)
                final_rows.append(sub_df_sorted.head(top_n))

    if not final_rows:
        print("没有符合条件的数据。")
        return None

    result_df = pd.concat(final_rows)

    # 计算 Distance
    print("正在计算 Distance ...")
    unique_symbols = result_df['Symbol'].unique().tolist()
    symbol_map = load_symbol_sector_map(SECTORS_JSON_PATH)
    price_map = get_latest_prices(unique_symbols, symbol_map, DB_PATH)

    def calculate_distance(row):
        sym = row['Symbol'].upper()
        strike_str = str(row['Strike']).replace(' new', '').strip()
        try: strike_val = float(strike_str.replace(',', ''))
        except: return "N/A"
        
        price_val = price_map.get(sym)
        if price_val is None: return "N/A"
        if price_val == 0: return "Err"
        
        dist = (strike_val - price_val) / price_val
        return f"{dist * 100:.2f}%"

    result_df['Distance'] = result_df.apply(calculate_distance, axis=1)

    # 最终整理
    result_df = result_df.sort_values(by=['Symbol', 'Type_Rank', 'Abs_Chg'], ascending=[True, True, False])
    
    # --- 【修改点】在输出列中增加 'Price' ---
    output_cols = ['Symbol', 'Type', 'Expiry Date', 'Strike', 'Distance', 'Open Interest_new', '1-Day Chg', 'Price']
    final_output = result_df[output_cols].rename(columns={'Open Interest_new': 'Open Interest'})
    final_output['Symbol'] = final_output['Symbol'].replace('^VIX', 'VIX')

    # 保存文件
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    # 1. 保存常规主文件 (这个文件通常还是只保留当天最新，或者你可以根据需要修改)
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
    final_output.to_csv(output_path, index=False)
    
    date_str = datetime.datetime.now().strftime('%y%m%d')
    backup_path = os.path.join(BACKUP_DIR, f"Options_Change_{date_str}.csv")
    if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
    final_output.to_csv(backup_path, index=False)
    print(f"✅ 备份文件已保存: {backup_path}")

    # 返回 DataFrame 供后续步骤使用
    return final_output

# ==========================================
# [新增] 独立出来的数据库写入函数
# ==========================================
def save_results_to_db(processed_data, db_path, table_name, iv_divisor):
    """
    将计算完毕的 processed_data 写入到 SQLite 数据库中。
    如果需要临时关闭数据库写入，只需在调用处注释掉此函数即可。
    """
    print(f"正在连接数据库: {db_path} ...")
    
    # 设定写入日期
    target_date = (pd.Timestamp.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"写入日期设定为: {target_date}")
    
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    # 1. 建表(增加 iv2 字段)
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        call TEXT,
        put TEXT,
        price REAL,
        change REAL,
        iv TEXT,
        iv2 TEXT,
        UNIQUE(date, name)
    )
    """
    cursor.execute(create_table_sql)

    # 2. 检查并自动添加列
    for col_name, col_type in [('change', 'REAL'), ('iv', 'TEXT'), ('iv2', 'TEXT')]:
        try:
            cursor.execute(f"SELECT {col_name} FROM {table_name} LIMIT 1")
        except:
            print(f"检测到缺少 '{col_name}' 列，正在添加...")
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                print(f"添加 {col_name} 列失败: {e}")

    query_prev_price_sql = f"SELECT price FROM {table_name} WHERE name = ? AND date < ? ORDER BY date DESC LIMIT 1"
    
    insert_sql = f"""
    INSERT INTO {table_name} (date, name, call, put, price, change, iv, iv2)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(date, name) DO UPDATE SET
        call=excluded.call,
        put=excluded.put,
        price=excluded.price,
        change=excluded.change,
        iv=excluded.iv,
        iv2=excluded.iv2
    """
    
    count_success = 0
    
    for symbol, values in processed_data.items():
        # --- 策略 1 结果 ---
        raw_call_d = values['Call']
        raw_put_d = values['Put']
        call_str = f"{raw_call_d * 100:.2f}%"
        put_str = f"{raw_put_d * 100:.2f}%"
        final_price = round((raw_call_d + raw_put_d) * 100, 2)
        
        # 计算 Change
        change_val = None
        try:
            cursor.execute(query_prev_price_sql, (symbol, target_date))
            row = cursor.fetchone()
            if row and row[0] is not None:
                prev_price = row[0]
                change_val = round(final_price - prev_price, 2)
        except:
            change_val = None
            
        # --- 策略 2 结果 ---
        sum_a = values['Call_IV_Sum']
        sum_b = values['Put_IV_Sum']
        raw_iv_val = (sum_a + sum_b) / iv_divisor
        final_iv = f"{raw_iv_val:.2f}%"

        # 策略 3
        raw_iv2_val = values.get('IV2', 0)
        final_iv2 = f"{raw_iv2_val * 100:.2f}%"

        try:
            cursor.execute(insert_sql, (target_date, symbol, call_str, put_str, final_price, change_val, final_iv, final_iv2))
            count_success += 1
        except Exception as e:
            print(f"错误: 写入/更新 {symbol} 失败: {e}")

    conn.commit()
    conn.close()
    print(f"入库完成！已处理（插入或更新）: {count_success} 条数据")


# ==========================================
# [Part B] 计算 D-Score, IV 及 IV2 并入库
# ==========================================
# 修改点：增加 iv_divisor, iv_threshold, iv_adj_factor 参数

def calculate_d_score_from_df(df_input, db_path, debug_path, n_config, iv_n_config, power_config, target_symbol, 
                              iv_divisor, iv_threshold, iv_adj_factor, price_map):
    """
    直接从 DataFrame 计算 Score 并写入数据库
    iv_n_config: 策略2取排名的数量
    iv_divisor: 策略2最终除数
    iv_threshold: 策略2距离阈值
    iv_adj_factor: 策略2权重调节系数
    """
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 开始执行 Score 与 IV / IV2 计算与入库...")
    print(f"当前配置: D-Score Top N = {n_config}, IV Top N = {iv_n_config}, 权重幂次 = {power_config}")
    print(f"IV配置: 除数={iv_divisor}, 阈值={iv_threshold}%, 调节系数={iv_adj_factor}")

    # 这里的 df_input 已经是内存中的 DataFrame，防止修改原数据
    df = df_input.copy()

    # 初始化调试文件
    if target_symbol:
        try:
            with open(debug_path, 'w') as f:
                f.write(f"=== {target_symbol} 计算过程追踪日志 ===\n")
                f.write(f"运行时间: {pd.Timestamp.now()}\n")
                f.write(f"权重幂次 (Power): {power_config}\n")
                f.write(f"IV参数: Divisor={iv_divisor}, Threshold={iv_threshold}%, Adj={iv_adj_factor}\n\n")
                f.write(f"策略3系数: A={STRAT3_COEFF_A}, B={STRAT3_COEFF_B}\n\n")
        except: pass

    # --- 数据预处理 (兼容 a.py 生成的格式) ---
    # 1. Distance 去百分号，转为小数
    try:
        df['Distance'] = df['Distance'].astype(str).str.rstrip('%').astype(float) / 100
    except:
        pass

    # 2. 确保数值列格式正确
    for col in ['Open Interest', '1-Day Chg', 'Price', 'Strike']:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 3. 解析日期
    df['Expiry Date'] = pd.to_datetime(df['Expiry Date'], errors='coerce')
    if df['Expiry Date'].isnull().any():
        print("警告: 有部分日期无法解析，将被忽略。")
        df = df.dropna(subset=['Expiry Date'])

    # 准备日期
    us_cal = USFederalHolidayCalendar()
    holidays = us_cal.holidays(start='2024-01-01', end='2030-12-31')
    today = pd.Timestamp.now().normalize()
    # 策略3用到的基准日期：今天的前一天
    ref_date_strat3 = today - timedelta(days=1)
    
    # 存储结果字典
    processed_data = {}

    # =========================================================================
    # 循环 1: 基于 (Symbol, Type) 分组 -> 计算 策略1 (D-Score) 和 策略2 (IV)
    # =========================================================================
    grouped = df.groupby(['Symbol', 'Type'])

    print(f"开始计算分数... (调试目标: {target_symbol})")

    for (symbol, type_), group in grouped:
        # 确保该 Symbol 在字典中初始化
        if symbol not in processed_data:
            processed_data[symbol] = {'Call': 0.0, 'Put': 0.0, 'Call_IV_Sum': 0.0, 'Put_IV_Sum': 0.0, 'IV2': 0.0}
        
        # 按数值降序排列
        group = group.sort_values(by='1-Day Chg', ascending=False)
        
        # ---------------------------
        # 策略 1: D-Score 逻辑 (已修改: 基于 1-Day Chg 加权)
        # ---------------------------
        top_items = group.head(n_config).copy()
        D = 0 
        
        # 调试数据容器
        strat1_debug_rows = []
        
        if not top_items.empty:
            max_expiry = top_items['Expiry Date'].max()
            
            # 计算 A (日期距离)
            a_days = np.busday_count(
                np.array([today], dtype='datetime64[D]'),
                np.array([max_expiry], dtype='datetime64[D]'),
                holidays=holidays.values.astype('datetime64[D]')
            )[0]
            
            # 计算每行差值
            expiry_dates = top_items['Expiry Date'].values.astype('datetime64[D]')
            today_arr = np.full(expiry_dates.shape, today).astype('datetime64[D]')
            days_i = np.busday_count(today_arr, expiry_dates, holidays=holidays.values.astype('datetime64[D]'))
            
            diff_i = a_days - days_i
            diff_pow = diff_i ** power_config
            B_val = np.sum(diff_pow) # 改名防止变量混淆
            
            # [修改点 1] 计算总的 1-Day Chg 作为分母，而非 Total Open Interest
            total_chg = top_items['1-Day Chg'].sum()
            C_val = 0
            
            # [修改点 2] 判断条件改为 total_chg != 0
            if B_val != 0 and total_chg != 0:
                w_i = diff_pow / B_val
                
                # [修改点 3] 核心公式修改：
                # 原来: ... * top_items['Open Interest'].values
                # 现在: ... * top_items['1-Day Chg'].values
                scores = w_i * top_items['Distance'].values * top_items['1-Day Chg'].values
                C_val = np.sum(scores)
                
                # --- 【核心修改点】 ---
                # 统计真正对 C 有贡献的行数：
                # 1. 1-Day Chg 必须大于 0
                # 2. diff_i 必须大于 0 (即不是最远的那一天，因为最远那一天的权重是0)
                valid_mask = (top_items['1-Day Chg'] > 0) & (diff_i > 0)
                valid_count = np.sum(valid_mask)
                
                if total_chg > 0:
                    # 使用有效行数作为乘数，而不是固定的 n_config(20)
                    D = C_val * valid_count / total_chg
                # ----------------------
                
                if symbol == target_symbol:
                    for idx in range(len(top_items)):
                        # 【修复点】使用 .iloc[idx] 来按位置访问 Series，避免 KeyError
                        is_valid_str = "Yes" if valid_mask.iloc[idx] else "No"
                        
                        strat1_debug_rows.append({
                            'Expiry': top_items.iloc[idx]['Expiry Date'].strftime('%Y-%m-%d'),
                            '1-Day Chg': top_items.iloc[idx]['1-Day Chg'],
                            'Dist': top_items.iloc[idx]['Distance'],
                            'Diff_i': diff_i[idx],
                            'Weight': w_i[idx],
                            'Score': scores[idx],
                            'IsValid': is_valid_str
                        })

        # 存入 D-Score
        type_str = str(type_).lower()
        if 'call' in type_str:
            processed_data[symbol]['Call'] = D
        elif 'put' in type_str:
            processed_data[symbol]['Put'] = D
            
        # ===========================
        # 策略 2: 新 IV 逻辑 (使用 iv_n_config)
        # 1. 取 Top 30
        # 2. 权重 = (1-Day Chg * Last Price) / Sum(1-Day Chg * Last Price)
        # 3. 移除距离惩罚
        
        top_iv_items = group.head(iv_n_config).copy()
        
        # 确保 Price 列是数值类型
        top_iv_items['Price'] = pd.to_numeric(top_iv_items['Price'], errors='coerce').fillna(0)
        
        iv_weighted_sum = 0.0
        # 计算该组（Call 或 Put）前 30 名的总金额
        total_price_iv = top_iv_items['Price'].sum()
        
        strat2_debug_rows = []
        
        for i in range(len(top_iv_items)):
            row_data = top_iv_items.iloc[i]
            dist_val = row_data['Distance'] * 100 
            price_val = row_data['Price']
            
            # 【修改点】基础权重改为基于金额 (Price = 1-Day Chg * Last Price)
            final_weight = price_val / total_price_iv if total_price_iv != 0 else 0.0
            
            # 【修改点】移除 IV_THRESHOLD 惩罚逻辑，直接计算贡献度
            contribution = dist_val * final_weight
            iv_weighted_sum += contribution
            
            # 收集策略2调试信息
            if symbol == target_symbol:
                strat2_debug_rows.append({
                    'Rank': i + 1,
                    'Expiry': row_data['Expiry Date'].strftime('%Y-%m-%d'),
                    'Strike': row_data['Strike'],
                    'Dist_Pct': dist_val,
                    '1-Day Chg': row_data['1-Day Chg'], # 【修复点2】 必须添加这一行，否则后面打印会报错
                    'Price_Val': price_val, # 显示金额
                    'Final_Wt': final_weight,
                    'Contrib': contribution
                })

        # 存入 IV 中间值
        if 'call' in type_str:
            processed_data[symbol]['Call_IV_Sum'] = iv_weighted_sum
        elif 'put' in type_str:
            processed_data[symbol]['Put_IV_Sum'] = iv_weighted_sum

        # ---------------------------
        # 统一写入调试文件 (策略1 + 策略2)
        # ---------------------------
        if symbol == target_symbol:
            log_lines = [f"\n{'='*80}\n正在计算: {symbol} - {type_}"]
            log_lines.append(f"\n[Strategy 1 - D-Score] (Top {n_config})")
            log_lines.append(f"A={a_days}, B={B_val:.4f}, C={C_val:.6f}")
            log_lines.append(f"有效行数(Chg>0且Diff>0)={valid_count}, Final D={D:.6f}")
            
            header1 = f"{'Expiry':<12} | {'Diff_i':<6} | {'Weight':<10} | {'Dist':<8} | {'Chg':<8} | {'Valid?':<6} | {'Score'}"
            log_lines.append(header1 + "\n" + "-"*len(header1))
            for r in strat1_debug_rows:
                log_lines.append(f"{r['Expiry']:<12} | {r['Diff_i']:<6} | {r['Weight']:.6f} | {r['Dist']:.4f} | {r['1-Day Chg']:<8.0f} | {r['IsValid']:<6} | {r['Score']:.6f}")

            log_lines.append(f"\n[Strategy 2 - IV] (Top {iv_n_config})")
            header2 = f"{'Rank':<4} | {'Expiry':<12} | {'Dist(%)':<8} | {'Chg':<8} | {'FinalWt':<8} | {'Contrib'}"
            log_lines.append(header2 + "\n" + "-"*len(header2))
            for r in strat2_debug_rows:
                # 这里的 r['1-Day Chg'] 现在可以正常读取了
                log_lines.append(f"{r['Rank']:<4} | {r['Expiry']:<12} | {r['Dist_Pct']:>7.2f}% | {r['1-Day Chg']:<8.0f} | {r['Final_Wt']:.4f} | {r['Contrib']:.4f}")
            
            with open(debug_path, 'a') as f: f.write('\n'.join(log_lines) + '\n')

    # =========================================================================
    # 循环 2: 基于 Symbol 分组 -> 计算 策略3 (IV2)
    # =========================================================================
    print("正在计算策略 3 (IV2) ...")
    
    grouped_symbol = df.groupby('Symbol')
    
    for symbol, sym_df in grouped_symbol:
        # 1. 获取标的收盘价
        S_close = price_map.get(symbol.upper())
        if S_close is None or S_close == 0:
            continue # 无法计算，跳过
            
        # 2. 按到期日分组
        exp_groups = sym_df.groupby('Expiry Date')
        
        expiry_metrics = [] # 存储每个到期日的 {d, 1/d, p, a, dis}
        strat3_debug_rows = []

        for expiry, exp_df in exp_groups:
            # --- 计算 d (时间差) ---
            # 逻辑：到期日 - (今天 - 1天)
            # 确保 d 为正数
            d_days = (expiry - ref_date_strat3).days
            if d_days <= 0: d_days = 1.0 # 防止除零或负数
            else: d_days = float(d_days)
            
            inv_d = 1.0 / d_days
            
            # --- 计算 p 和 a ---
            # 需将 Call 和 Put 的 Price 合并
            # exp_df 包含该 Symbol 该 Expiry 下所有的 Strike 和 Type
            
            # 按 Strike 聚合 Price (Call Price + Put Price)
            # 结果是一个 Series，Index 是 Strike，Value 是 Sum(Price)
            strike_sums = exp_df.groupby('Strike')['Price'].sum()
            
            # 该到期日下所有 Strike 的 Price 总和
            total_price_expiry = strike_sums.sum()
            
            # 该到期日下的 Strike 数量
            num_strikes = len(strike_sums)
            
            if num_strikes == 0 or total_price_expiry == 0:
                continue
                
            # 计算 p (平均 Price)
            p = total_price_expiry / num_strikes
            
            # 计算 a (加权平均 Strike)
            # 公式：Sum(Strike * (Strike_Price / Total_Price_Expiry))
            # 等价于 Sum(Strike * Strike_Price) / Total_Price_Expiry
            weighted_sum_strike = np.sum(strike_sums.index * strike_sums.values)
            a = weighted_sum_strike / total_price_expiry
            
            # 计算 dis (价外程度)
            dis = (a - S_close) / S_close
            
            expiry_metrics.append({
                'expiry': expiry,
                'd': d_days,
                'inv_d': inv_d,
                'p': p,
                'a': a,
                'dis': dis
            })

        # 3. 计算汇总值 D 和 P
        if not expiry_metrics:
            continue
            
        D_val = sum(m['inv_d'] for m in expiry_metrics)
        P_val = sum(m['p'] for m in expiry_metrics)
        
        # 4. 计算最终 IV2
        # 公式: Sum( dis * [ (1/d)/D * A + p/P * B ] )
        iv2_final = 0.0
        
        for m in expiry_metrics:
            term_time = (m['inv_d'] / D_val) * STRAT3_COEFF_A if D_val != 0 else 0
            term_price = (m['p'] / P_val) * STRAT3_COEFF_B if P_val != 0 else 0
            
            term_val = m['dis'] * (term_time + term_price)
            iv2_final += term_val
            
            if symbol == target_symbol:
                strat3_debug_rows.append({
                    'Expiry': m['expiry'].strftime('%Y-%m-%d'),
                    'd': m['d'],
                    '1/d': m['inv_d'],
                    'p': m['p'],
                    'a': m['a'],
                    'dis': m['dis'],
                    'Term': term_val
                })

        # 存入结果字典
        if symbol not in processed_data:
            processed_data[symbol] = {'Call': 0.0, 'Put': 0.0, 'Call_IV_Sum': 0.0, 'Put_IV_Sum': 0.0, 'IV2': 0.0}
        
        processed_data[symbol]['IV2'] = iv2_final

        # --- 写入调试日志 (策略3) ---
        if symbol == target_symbol:
            log_lines = [f"\n[Strategy 3 - IV2]"]
            log_lines.append(f"Underlying Close: {S_close}")
            log_lines.append(f"Aggregates: D={D_val:.6f}, P={P_val:.2f}")
            log_lines.append(f"Final IV2: {iv2_final:.6f}")
            
            header3 = f"{'Expiry':<12} | {'d':<4} | {'1/d':<8} | {'p':<10} | {'a':<8} | {'dis':<8} | {'Term'}"
            log_lines.append(header3 + "\n" + "-"*len(header3))
            for r in strat3_debug_rows:
                log_lines.append(f"{r['Expiry']:<12} | {r['d']:<4.0f} | {r['1/d']:.4f}   | {r['p']:<10.2f} | {r['a']:<8.2f} | {r['dis']:<8.4f} | {r['Term']:.6f}")
            
            with open(debug_path, 'a') as f: f.write('\n'.join(log_lines) + '\n')

    # =========================================================================
    # 数据库写入逻辑 (已抽取为独立函数)
    # =========================================================================
    # 💡 如果你暂时不想写数据库，只需把下面这行注释掉即可：
    # save_results_to_db(processed_data, db_path, TABLE_NAME, iv_divisor)
    
    return processed_data

# ==========================================
# 工具函数 & Main
# ==========================================

def get_latest_two_files(directory, pattern='Options_*.csv'):
    """自动获取最新的两个文件"""
    search_path = os.path.join(directory, pattern)
    files = glob.glob(search_path)
    
    # 过滤掉文件名中包含 'Change' 或 'History' 的备份文件，防止读入上次的运行结果
    files = [f for f in files if 'Change' not in os.path.basename(f) and 'History' not in os.path.basename(f)]
    files.sort(reverse=True)
    
    # 调试打印，方便确认读到了哪两个文件
    if len(files) >= 2:
        print(f"DEBUG: 自动选中最新文件 (New): {os.path.basename(files[0])}")
        print(f"DEBUG: 自动选中次新文件 (Old): {os.path.basename(files[1])}")
    if len(files) < 2: return None, None
    return files[0], files[1]

def show_alert(message):
    try:
        if sys.platform == 'darwin':
            applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        elif sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "提示", 0)
    except Exception:
        pass

if __name__ == "__main__":
    file_new = None
    file_old = None

    # 1. 确定文件路径
    if USE_MANUAL_MODE:
        print(">>> 模式: 手动指定 (Manual Mode)")
        file_old = MANUAL_FILE_OLD
        file_new = MANUAL_FILE_NEW
        if not (os.path.exists(file_old) and os.path.exists(file_new)):
            print("❌ 错误: 找不到指定的手动文件。")
            file_new = None
    else:
        print(">>> 模式: 自动扫描 (Auto Mode)")
        file_new, file_old = get_latest_two_files(BACKUP_DIR)
        if not file_new:
            print("❌ 错误: 备份目录下文件不足两个。")

    # 2. 开始执行流程
    if file_new and file_old:
        # 第一步：处理并生成 Change 数据
        generated_df = process_options_change(file_old, file_new, TOP_N, INCLUDE_NEW_ROWS)
        
        # 第二步：如果生成成功，直接在内存中传递数据进行入库计算
        if generated_df is not None and not generated_df.empty:
            # 【新增】为了策略3，我们需要在这里获取一次所有涉及 Symbol 的最新价格
            print("正在为策略 3 获取标的资产价格...")
            unique_symbols = generated_df['Symbol'].unique().tolist()
            symbol_map = load_symbol_sector_map(SECTORS_JSON_PATH)
            # 获取价格字典
            current_price_map = get_latest_prices(unique_symbols, symbol_map, DB_PATH)

            # 第二步：计算入库 (传入 price_map)
            calculate_d_score_from_df(
                generated_df, 
                DB_PATH, 
                OUTPUT_DEBUG_PATH, 
                TOP_N, 
                IV_TOP_N, 
                WEIGHT_POWER, 
                DEBUG_SYMBOL,
                IV_DIVISOR,
                IV_THRESHOLD,
                IV_ADJUSTMENT,
                current_price_map # 传入价格字典
            )
            show_alert("流程完成：CSV已生成，数据库已更新")
        else:
            print("\n⚠️ 未生成有效数据，跳过数据库计算步骤。")
    else:
        print("\n程序终止: 未能获取有效的对比文件。")