import pandas as pd
import numpy as np
import os
import datetime
import glob
import subprocess
import json
import sqlite3
from datetime import timedelta
from pandas.tseries.holiday import USFederalHolidayCalendar

# ==========================================
# 全局配置区域 (Configuration)
# ==========================================

# --- 路径配置 ---
# 备份文件所在的文件夹路径 (自动模式用)
BACKUP_DIR = '/Users/yanzhang/Coding/News/backup'

# 输出文件的配置 (a.py 输出)
OUTPUT_DIR = '/Users/yanzhang/Coding/News'
OUTPUT_FILENAME = 'Options_Change.csv'

# JSON 映射文件路径
SECTORS_JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'

# SQLite 数据库路径 (共用)
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'
TABLE_NAME = 'Options'

# 调试输出路径 (b.py逻辑用)
OUTPUT_DEBUG_PATH = '/Users/yanzhang/Downloads/3.txt'

# --- 算法参数配置 ---
# 每个 Symbol 的 Calls 和 Puts 各保留前多少名 (共用)
TOP_N = 20 

# a.py 逻辑参数: 是否考虑新增的数据 (B有A无)
INCLUDE_NEW_ROWS = True

# b.py 逻辑参数: 权重幂次配置 (1=线性, 2=平方...)
WEIGHT_POWER = 1

# b.py 调试 Symbol
DEBUG_SYMBOL = ""

# --- 模式切换配置 ---
# True:  手动模式 (使用下方指定的两个具体文件)
# False: 自动模式 (自动寻找 BACKUP_DIR 下最新的两个文件)
USE_MANUAL_MODE = False

# 手动模式下的文件路径
MANUAL_FILE_OLD = '/Users/yanzhang/Coding/News/backup/Options_251224.csv'
MANUAL_FILE_NEW = '/Users/yanzhang/Coding/News/backup/Options_251227.csv'


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
    """批量获取 Symbol 的最新价格"""
    if not os.path.exists(db_path):
        print(f"⚠️ 警告: 找不到数据库文件: {db_path}")
        return {}

    price_dict = {}
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=60.0)
        cursor = conn.cursor()
        sector_groups = {}
        
        for sym in symbols:
            sym_upper = sym.upper()
            lookup_sym = 'VIX' if sym_upper == '^VIX' else sym_upper
            
            sector = symbol_sector_map.get(lookup_sym)
            if sector:
                if sector not in sector_groups:
                    sector_groups[sector] = []
                sector_groups[sector].append(lookup_sym)

        print(f"正在从数据库获取 {len(symbols)} 个 Symbol 的最新价格...")
        for sector, sym_list in sector_groups.items():
            if not sym_list: continue
            
            placeholders = ','.join(['?'] * len(sym_list))
            query = f"""
                SELECT t1.name, t1.price
                FROM "{sector}" t1
                JOIN (
                    SELECT name, MAX(date) as max_date
                    FROM "{sector}"
                    WHERE name IN ({placeholders})
                    GROUP BY name
                ) t2 ON t1.name = t2.name AND t1.date = t2.max_date
            """
            try:
                cursor.execute(query, sym_list)
                rows = cursor.fetchall()
                for name, price in rows:
                    name_upper = name.upper()
                    price_dict[name_upper] = price
                    if name_upper == 'VIX':
                        price_dict['^VIX'] = price
            except Exception as e:
                print(f"   ⚠️ 查询表 '{sector}' 出错: {e}")
    except Exception as e:
        print(f"数据库连接或查询总错误: {e}")
    finally:
        if conn: conn.close()
            
    return price_dict

def process_options_change(file_old, file_new, top_n=50, include_new=True):
    """
    处理期权变化逻辑。
    返回: 处理后的 DataFrame (如果不成功返回 None)
    """
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 开始处理文件比对...")
    print(f"旧文件: {os.path.basename(file_old)}")
    print(f"新文件: {os.path.basename(file_new)}")

    if not os.path.exists(file_old) or not os.path.exists(file_new):
        print("错误: 找不到文件。")
        return None

    try:
        dtype_dict = {'Symbol': str, 'Expiry Date': str, 'Type': str, 'Strike': str}
        df_old = pd.read_csv(file_old, dtype=dtype_dict)
        df_new = pd.read_csv(file_new, dtype=dtype_dict)
    except Exception as e:
        print(f"读取错误: {e}")
        return None

    # 数据清洗
    df_old.columns = df_old.columns.str.strip()
    df_new.columns = df_new.columns.str.strip()
    
    def clean_str_cols(df):
        for col in ['Symbol', 'Expiry Date', 'Type', 'Strike']:
            if col in df.columns:
                df[col] = df[col].str.strip()
        return df
    
    df_old = clean_str_cols(df_old)
    df_new = clean_str_cols(df_new)

    # 过滤全新日期
    print("正在过滤全新出现的 Expiry Date ...")
    valid_old_dates = set(zip(df_old['Symbol'], df_old['Expiry Date']))
    df_new['_date_key'] = list(zip(df_new['Symbol'], df_new['Expiry Date']))
    rows_before = len(df_new)
    df_new = df_new[df_new['_date_key'].isin(valid_old_dates)].copy()
    print(f"已剔除 {rows_before - len(df_new)} 行全新日期数据。")
    df_new.drop(columns=['_date_key'], inplace=True)

    # 处理 Open Interest
    def clean_oi(val):
        if pd.isna(val): return 0
        if isinstance(val, (int, float)): return val
        try: return float(str(val).replace(',', ''))
        except: return 0.0

    df_old['Open Interest'] = df_old.get('Open Interest', pd.Series(0)).apply(clean_oi)
    df_new['Open Interest'] = df_new.get('Open Interest', pd.Series(0)).apply(clean_oi)

    old_expiry_set = set(zip(df_old['Symbol'], df_old['Expiry Date']))
    
    # 合并
    key_columns = ['Symbol', 'Expiry Date', 'Type', 'Strike']
    merged = pd.merge(df_old, df_new, on=key_columns, how='outer', suffixes=('_old', '_new'), indicator=True)
    
    # 过滤逻辑
    merged = merged[merged['_merge'] != 'left_only'].copy()
    if not include_new:
        merged = merged[merged['_merge'] == 'both'].copy()
        
    merged['Open Interest_old'] = merged['Open Interest_old'].fillna(0)
    merged['Open Interest_new'] = merged['Open Interest_new'].fillna(0)
    
    # 剔除旧持仓为0的
    merged = merged[merged['Open Interest_old'] != 0].copy()
    
    # 计算变化
    merged['1-Day Chg'] = merged['Open Interest_new'] - merged['Open Interest_old']
    merged = merged[merged['1-Day Chg'] >= 0].copy()

    # 标记 new
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
    output_cols = ['Symbol', 'Type', 'Expiry Date', 'Strike', 'Distance', 'Open Interest_new', '1-Day Chg']
    final_output = result_df[output_cols].rename(columns={'Open Interest_new': 'Open Interest'})
    final_output['Symbol'] = final_output['Symbol'].replace('^VIX', 'VIX')

    # 保存文件 (原功能)
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
    final_output.to_csv(output_path, index=False)
    print(f"\n✅ 主文件已保存: {output_path}")

    # 保存备份
    date_str = datetime.datetime.now().strftime('%y%m%d')
    backup_path = os.path.join(BACKUP_DIR, f"Options_Change_{date_str}.csv")
    if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
    final_output.to_csv(backup_path, index=False)
    print(f"✅ 备份文件已保存: {backup_path}")

    # 返回 DataFrame 供后续步骤使用
    return final_output

# ==========================================
# [Part B] 计算 D-Score 并入库 (原 b.py)
# ==========================================

def calculate_d_score_from_df(df_input, db_path, debug_path, n_config, power_config, target_symbol):
    """
    直接从 DataFrame 计算 Score 并写入数据库 (替代原 read_csv 方式)
    已更新: 增加 change 字段计算 (Current Price - Previous Price)
    """
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 开始执行 Score 计算与入库...")
    print(f"当前配置: Top N = {n_config}, 权重幂次 = {power_config}")
    
    # 这里的 df_input 已经是内存中的 DataFrame，我们需要防止修改原数据
    df = df_input.copy()
    
    # 初始化调试文件
    if target_symbol:
        try:
            with open(debug_path, 'w') as f:
                f.write(f"=== {target_symbol} 计算过程追踪日志 ===\n")
                f.write(f"运行时间: {pd.Timestamp.now()}\n")
                f.write(f"权重幂次 (Power): {power_config}\n\n")
        except Exception as e:
            print(f"无法创建调试文件: {e}")

    # --- 数据预处理 (兼容 a.py 生成的格式) ---
    # 1. Distance 去百分号
    try:
        df['Distance'] = df['Distance'].astype(str).str.rstrip('%').astype(float) / 100
    except:
        pass 
    
    # 2. 确保数值列格式正确
    for col in ['Open Interest', '1-Day Chg']:
        if df[col].dtype == object:
             df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 3. 解析日期
    df['Expiry Date'] = pd.to_datetime(df['Expiry Date'], errors='coerce')
    if df['Expiry Date'].isnull().any():
        print("警告: 有部分日期无法解析，将被忽略。")
        df = df.dropna(subset=['Expiry Date'])

    # 准备工作日
    us_cal = USFederalHolidayCalendar()
    holidays = us_cal.holidays(start='2024-01-01', end='2030-12-31')
    today = pd.Timestamp.now().normalize()
    
    processed_data = {}
    grouped = df.groupby(['Symbol', 'Type'])
    
    print(f"开始计算分数... (调试目标: {target_symbol})")
    
    for (symbol, type_), group in grouped:
        # 按数值降序
        group = group.sort_values(by='1-Day Chg', ascending=False)
        top_items = group.head(n_config).copy()
        
        if top_items.empty: continue
            
        actual_n = len(top_items)
        max_expiry = top_items['Expiry Date'].max()
        
        # 计算 A (今天到最远日期的工作日天数)
        a_days = np.busday_count(
            np.array([today], dtype='datetime64[D]'),
            np.array([max_expiry], dtype='datetime64[D]'),
            holidays=holidays.values.astype('datetime64[D]')
        )[0]
        
        # 计算差值
        expiry_dates = top_items['Expiry Date'].values.astype('datetime64[D]')
        today_arr = np.full(expiry_dates.shape, today).astype('datetime64[D]')
        days_i = np.busday_count(today_arr, expiry_dates, holidays=holidays.values.astype('datetime64[D]'))
        
        diff_i = a_days - days_i
        
        zero_diff_count = np.sum(diff_i == 0)
        diff_pow = diff_i ** power_config
        B = np.sum(diff_pow)
        
        total_oi = top_items['Open Interest'].sum()
        C = 0
        D = 0
        
        row_details = []
        
        if B != 0 and total_oi != 0:
            w_i = diff_pow / B
            scores = w_i * top_items['Distance'].values * top_items['Open Interest'].values
            C = np.sum(scores)
            
            if actual_n > zero_diff_count:
                D = C * (actual_n - zero_diff_count) / total_oi
            
            if symbol == target_symbol:
                for idx in range(len(top_items)):
                    row_details.append({
                        'Expiry': top_items.iloc[idx]['Expiry Date'].strftime('%Y-%m-%d'),
                        '1-Day Chg': top_items.iloc[idx]['1-Day Chg'],
                        'Dist': top_items.iloc[idx]['Distance'],
                        'OI': top_items.iloc[idx]['Open Interest'],
                        'Days_i': days_i[idx],
                        'Diff_i': diff_i[idx],
                        'Diff_Pow': diff_pow[idx],
                        'Weight': w_i[idx],
                        'Score': scores[idx]
                    })
        
        if symbol not in processed_data:
            processed_data[symbol] = {'Call': 0.0, 'Put': 0.0}
        
        type_str = str(type_).lower()
        if 'call' in type_str:
            processed_data[symbol]['Call'] = D
        elif 'put' in type_str:
            processed_data[symbol]['Put'] = D

        # 写入调试日志
        if symbol == target_symbol:
            log_lines = []
            log_lines.append("-" * 80)
            log_lines.append(f"正在计算: {symbol} - {type_}")
            log_lines.append(f"实际条目数: {actual_n}, Diff=0数: {zero_diff_count}")
            log_lines.append(f"A={a_days}, B={B}, C={C:.6f}, D={D:.6f}")
            if row_details:
                header = f"{'Expiry':<12} | {'Diff_i':<6} | {'Weight':<10} | {'Dist':<8} | {'OI':<8} | {'Score'}"
                log_lines.append(header)
                log_lines.append("-" * len(header))
                for row in row_details:
                    log_lines.append(f"{row['Expiry']:<12} | {row['Diff_i']:<6} | {row['Weight']:.6f}   | {row['Dist']:.4f}   | {row['OI']:<8} | {row['Score']:.6f}")
            log_lines.append("\n")
            with open(debug_path, 'a') as f:
                f.write('\n'.join(log_lines))

    # --- 数据库写入逻辑 ---
    print(f"正在连接数据库: {db_path} ...")
    
    # 设定写入日期
    target_date = (pd.Timestamp.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"写入日期设定为: {target_date}")
    
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    # 1. 更新建表语句，增加 change 字段
    # 注意：如果表已存在且无 change 字段，此语句不会自动添加列。
    # 假设用户已处理好数据库结构，或者这是一个新数据库。
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        call TEXT,
        put TEXT,
        price REAL,
        change REAL,
        UNIQUE(date, name)
    )
    """
    cursor.execute(create_table_sql)
    
    # 2. 准备 SQL 语句
    # 查询前一个交易日价格的 SQL
    query_prev_price_sql = f"""
        SELECT price 
        FROM {TABLE_NAME} 
        WHERE name = ? AND date < ? 
        ORDER BY date DESC 
        LIMIT 1
    """

    # 插入或更新的 SQL (包含 change)
    insert_sql = f"""
    INSERT INTO {TABLE_NAME} (date, name, call, put, price, change) 
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(date, name) 
    DO UPDATE SET 
        call=excluded.call,
        put=excluded.put,
        price=excluded.price,
        change=excluded.change
    """
    
    count_success = 0
    
    for symbol, values in processed_data.items():
        raw_call_d = values['Call']
        raw_put_d = values['Put']
        
        call_str = f"{raw_call_d * 100:.2f}%"
        put_str = f"{raw_put_d * 100:.2f}%"
        final_price = round((raw_call_d + raw_put_d) * 100, 2)
        
        # --- 新增逻辑: 计算 Change ---
        change_val = None
        try:
            cursor.execute(query_prev_price_sql, (symbol, target_date))
            row = cursor.fetchone()
            if row and row[0] is not None:
                prev_price = row[0]
                change_val = round(final_price - prev_price, 2)
            else:
                # 之前没有记录，change 设为 None (数据库中为 NULL)
                change_val = None
        except Exception as e:
            print(f"查询 {symbol} 前值失败: {e}")
            change_val = None
        # ---------------------------

        try:
            # 执行 Upsert，传入 change_val
            cursor.execute(insert_sql, (target_date, symbol, call_str, put_str, final_price, change_val))
            count_success += 1
        except Exception as e:
            # 兼容性处理：如果表结构还没改，INSERT 可能会报错缺少列
            # 这里尝试捕获并提示用户
            if "has no column named change" in str(e):
                print(f"❌ 严重错误: 数据库表 '{TABLE_NAME}' 缺少 'change' 列。请先手动修改数据库结构或删除旧表。")
                break
            print(f"错误: 写入/更新 {symbol} 失败: {e}")
            
    conn.commit()
    conn.close()
    
    print(f"入库完成！已处理（插入或更新）: {count_success} 条数据")

# ==========================================
# 工具函数 & Main
# ==========================================

def get_latest_two_files(directory, pattern='Options_*.csv'):
    """自动获取最新的两个文件"""
    search_path = os.path.join(directory, pattern)
    files = glob.glob(search_path)
    
    # [新增] 过滤掉文件名中包含 'Change' 的备份文件，防止读入上次的运行结果
    files = [f for f in files if 'Change' not in os.path.basename(f)]
    
    files.sort(reverse=True)
    
    # 调试打印，方便确认读到了哪两个文件
    if len(files) >= 2:
        print(f"DEBUG: 自动选中最新文件 (New): {os.path.basename(files[0])}")
        print(f"DEBUG: 自动选中次新文件 (Old): {os.path.basename(files[1])}")
        
    if len(files) < 2: return None, None
    return files[0], files[1]

def show_alert(message):
    try:
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
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
            calculate_d_score_from_df(
                generated_df, 
                DB_PATH, 
                OUTPUT_DEBUG_PATH, 
                TOP_N, 
                WEIGHT_POWER, 
                DEBUG_SYMBOL
            )
            show_alert("流程完成：CSV已生成，数据库已更新")
        else:
            print("\n⚠️ 未生成有效数据，跳过数据库计算步骤。")
    else:
        print("\n程序终止: 未能获取有效的对比文件。")