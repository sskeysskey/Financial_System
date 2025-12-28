import pandas as pd
import numpy as np
from pandas.tseries.holiday import USFederalHolidayCalendar
import sqlite3
from datetime import timedelta

# ================= 配置区域 =================

# 1. 输入路径
INPUT_CSV_PATH = '/Users/yanzhang/Coding/News/Options_Change.csv' 

# 2. 数据库配置
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db' # 数据库路径
TABLE_NAME = 'Options' # 表名

# 3. 调试输出 (验证过程)
OUTPUT_DEBUG_PATH  = '/Users/yanzhang/Downloads/3.txt'

# 4. 算法参数
TOP_N = 20

# 【新功能】权重幂次配置
# 1 = 线性 (原版逻辑), 2 = 平方, 3 = 立方 ...
WEIGHT_POWER = 1

# 5. 调试配置
DEBUG_SYMBOL = "WELL" 

# ===========================================

def calculate_d_score_to_db(df_path, db_path, debug_path, n_config, power_config, target_symbol):
    print(f"正在读取文件: {df_path} ...")
    print(f"当前配置: Top N = {n_config}, 权重幂次 = {power_config}")

    # 清空旧的调试文件
    if target_symbol:
        try:
            with open(debug_path, 'w') as f:
                f.write(f"=== {target_symbol} 计算过程追踪日志 ===\n")
                f.write(f"运行时间: {pd.Timestamp.now()}\n")
                f.write(f"权重幂次 (Power): {power_config}\n\n")
        except Exception as e:
            print(f"无法创建调试文件: {e}")

    try:
        df = pd.read_csv(df_path)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {df_path}")
        return

    # --- 数据预处理 ---
    # 1. Distance 去百分号
    try:
        df['Distance'] = df['Distance'].astype(str).str.rstrip('%').astype(float) / 100
    except:
        pass # 可能是纯数字

    # 2. 确保数值列格式正确
    # 替换可能存在的千分位逗号等字符
    for col in ['Open Interest', '1-Day Chg']:
        if df[col].dtype == object:
             df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 3. 解析日期 (修复报错的关键步骤)
    # 不指定 format，让 pandas 自动推断 (支持 yyyy/mm/dd 和 dd/mm/yyyy 等多种格式)
    # errors='coerce' 会将无法解析的日期设为 NaT，防止程序直接崩溃
    df['Expiry Date'] = pd.to_datetime(df['Expiry Date'], errors='coerce')
    
    # 检查是否有日期解析失败
    if df['Expiry Date'].isnull().any():
        print("警告: 有部分日期无法解析，这些行将被忽略。请检查CSV中的日期列。")
        df = df.dropna(subset=['Expiry Date'])

    # 准备工作日计算 (排除周末和美国节假日)
    us_cal = USFederalHolidayCalendar()
    #以此处为起点向后预留足够的年份范围
    holidays = us_cal.holidays(start='2024-01-01', end='2030-12-31')
    
    # 获取当前日期 (今天)
    today = pd.Timestamp.now().normalize()

    # --- 准备存储数据的字典 ---
    # 结构: { 'NVDA': {'Call': 0.0, 'Put': 0.0}, 'AAPL': {'Call':...} }
    processed_data = {}

    grouped = df.groupby(['Symbol', 'Type'])
    
    print(f"开始计算... (调试目标: {target_symbol})")
    
    for (symbol, type_), group in grouped:
        # 1. 以 1-Day Chg 大小排序 (降序)
        # 注意：这里按数值大小排序。如果需要按绝对值排序，请修改为 key=abs
        group = group.sort_values(by='1-Day Chg', ascending=False)
        
        # 2. 取前 N 项 (不足 N 项则取全部)
        top_items = group.head(n_config).copy()
        
        if top_items.empty:
            continue
            
        # 【修改 1】获取实际参与计算的条目数
        # 如果 group 只有 7 条，这里 actual_n 就是 7；如果有 100 条，这里就是 20
        actual_n = len(top_items)

        # 3. 找到 Expiry Date 最远的那个
        max_expiry = top_items['Expiry Date'].max()
        
        # 4. 计算 A (今天到最远日期的工作日天数)
        # 向量化计算需要转为 datetime64[D]
        a_days = np.busday_count(
            np.array([today], dtype='datetime64[D]'),
            np.array([max_expiry], dtype='datetime64[D]'),
            holidays=holidays.values.astype('datetime64[D]')
        )[0]
        
        # 5. 计算每行的 Expiry 到今天的时间差
        expiry_dates = top_items['Expiry Date'].values.astype('datetime64[D]')
        today_arr = np.full(expiry_dates.shape, today).astype('datetime64[D]')
        
        # 计算 days_i (Today 到 Expiry)
        # 注意 busday_count 需要 start <= end，否则返回负数
        days_i = np.busday_count(
            today_arr, 
            expiry_dates, 
            holidays=holidays.values.astype('datetime64[D]')
        )
        
        # 6. 计算差值 (diff_i = A - days_i)
        diff_i = a_days - days_i
        
        # --- 【新功能实现】统计 diff_i 为 0 的数量 ---
        # 逻辑：如果有 3 行的日期都是 Max Expiry，那么它们的 diff_i 都是 0
        # 它们对 C 的贡献为 0，所以在放大系数时应该把这 3 行都减掉
        zero_diff_count = np.sum(diff_i == 0)
        # ----------------------------------------

        # 【修改重点】计算差值的 N 次方
        # 使用配置项 power_config
        diff_pow = diff_i ** power_config
        
        # 7. 加总 B (所有 diff_pow 的和)
        B = np.sum(diff_pow)
        
        # 计算 D 的逻辑
        total_oi = top_items['Open Interest'].sum()
        C = 0
        D = 0
        
        # 临时存储该组的详细行数据用于调试
        row_details = []

        if B != 0 and total_oi != 0:
            # 权重 w_i = (diff_i ^ n) / B
            w_i = diff_pow / B
            
            # 质量分数 Score
            scores = w_i * top_items['Distance'].values * top_items['Open Interest'].values
            
            # C
            C = np.sum(scores)
            
            # D
            # 【修改 2 - 修正版】使用 actual_n 减去 diff_i 为 0 的实际数量
            # 原逻辑: D = C * (actual_n - 1) / total_oi
            # 新逻辑: D = C * (actual_n - zero_diff_count) / total_oi
            if actual_n > zero_diff_count:
                D = C * (actual_n - zero_diff_count) / total_oi
            else:
                D = 0 # 理论上 B!=0 进不来这里，但也做个保护
            
            # 仅在调试目标匹配时收集详细数据
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

        # --- 这里的逻辑修改了：不再存字符串，而是存入字典 ---
        if symbol not in processed_data:
            processed_data[symbol] = {'Call': 0.0, 'Put': 0.0}
        
        # 根据 Type 判断是 Call 还是 Put
        # 假设 CSV 中 Type 列包含 "Call" 或 "Put" (不区分大小写)
        type_str = str(type_).lower()
        if 'call' in type_str:
            processed_data[symbol]['Call'] = D
        elif 'put' in type_str:
            processed_data[symbol]['Put'] = D

        # ================= 调试日志核心逻辑 =================
        if symbol == target_symbol:
            log_lines = []
            log_lines.append("-" * 80)
            log_lines.append(f"正在计算: {symbol} - {type_}")
            log_lines.append(f"当前参考日期: {today.strftime('%Y-%m-%d')}")
            # 【修改 3】日志中显示实际使用的行数
            log_lines.append(f"实际条目数 (Actual N): {actual_n} (配置上限: {n_config})")
            log_lines.append(f"权重计算规则: Diff_i 的 {power_config} 次方 (Power={power_config})")
            log_lines.append("-" * 80)
            
            log_lines.append(f"步骤 1: Max Expiry -> {max_expiry.strftime('%Y-%m-%d')}")
            log_lines.append(f"步骤 2: 参数 A -> {a_days} 天")
            log_lines.append(f"步骤 3: 逐行计算:\n")
            
            # 动态调整表头，显示 Diff^2, Diff^3 等
            pow_header = f"Diff^{power_config}"
            header = f"{'Expiry':<12} | {'Diff_i':<6} | {pow_header:<10} | {'Weight':<10} | {'Dist':<8} | {'OI':<8} | {'Score'}"
            log_lines.append(header)
            log_lines.append("-" * len(header))
            
            for row in row_details:
                line = (f"{row['Expiry']:<12} | {row['Diff_i']:<6} | {row['Diff_Pow']:<10} | "
                        f"{row['Weight']:.6f}   | {row['Dist']:.4f}   | {row['OI']:<8} | {row['Score']:.6f}")
                log_lines.append(line)
            
            log_lines.append("-" * len(header))
            log_lines.append(f"步骤 4: 计算 B (Diff^{power_config} 之和) -> {B}")
            log_lines.append(f"步骤 5: 计算 C (Score 之和)  -> {C:.6f}")
            log_lines.append(f"步骤 6: Total Open Interest -> {total_oi}")
            log_lines.append(f"步骤 7: 计算最终 D 值")
            log_lines.append(f"       Diff_i为0的行数: {zero_diff_count}")
            # 【修改 4 - 修正版】日志公式更新
            log_lines.append(f"       D = ({C:.6f} * ({actual_n} - {zero_diff_count})) / {total_oi}")
            log_lines.append(f"       D = {D:.6f}")
            log_lines.append("\n\n")

            # 写入调试文件
            with open(debug_path, 'a') as f:
                f.write('\n'.join(log_lines))
            print(f"  -> {symbol} {type_} 调试日志已更新")
        # ==================================================

    # ================= 数据库写入逻辑 =================
    print(f"\n正在连接数据库: {db_path} ...")
    
    # 获取需要写入的日期：今天的前一天
    target_date = (pd.Timestamp.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"写入日期设定为: {target_date}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. 创建表 (如果不存在)
    # UNIQUE(date, name) 用于防止同一天同一个Symbol重复插入
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        call TEXT,
        put TEXT,
        price REAL,
        UNIQUE(date, name)
    )
    """
    cursor.execute(create_table_sql)

    # 2. 遍历字典并写入
    insert_sql = f"INSERT INTO {TABLE_NAME} (date, name, call, put, price) VALUES (?, ?, ?, ?, ?)"
    
    count_success = 0
    count_skip = 0

    for symbol, values in processed_data.items():
        raw_call_d = values['Call']
        raw_put_d = values['Put']

        # 检查是否已存在
        check_sql = f"SELECT 1 FROM {TABLE_NAME} WHERE date=? AND name=?"
        cursor.execute(check_sql, (target_date, symbol))
        if cursor.fetchone():
            print(f"提示: [{target_date}] Symbol: {symbol} 数据已存在，跳过写入。")
            count_skip += 1
            continue

        # 数据格式化
        # Call: 保留两位小数百分数
        call_str = f"{raw_call_d * 100:.2f}%"
        
        # Put: 保留原始符号，直接乘以 100
        put_str = f"{raw_put_d * 100:.2f}%"

        # Price: (Call raw + Put raw) * 100, 保留两位小数
        # 逻辑：直接相加，如果是负数+负数，结果自然是负数
        final_price = round((raw_call_d + raw_put_d) * 100, 2)

        try:
            cursor.execute(insert_sql, (target_date, symbol, call_str, put_str, final_price))
            count_success += 1
        except sqlite3.IntegrityError:
            print(f"提示: [{target_date}] Symbol: {symbol} 写入冲突。")
            count_skip += 1
        except Exception as e:
            print(f"错误: 写入 {symbol} 时发生异常: {e}")

    conn.commit()
    conn.close()
    
    print(f"\n全部完成！")
    print(f"成功写入: {count_success} 条")
    print(f"跳过重复: {count_skip} 条")

if __name__ == "__main__":
    calculate_d_score_to_db(INPUT_CSV_PATH, DB_PATH, OUTPUT_DEBUG_PATH, TOP_N, WEIGHT_POWER, DEBUG_SYMBOL)
