import pandas as pd
import numpy as np
from pandas.tseries.holiday import USFederalHolidayCalendar

# ================= 配置区域 =================

# 1. 输入和输出路径
INPUT_CSV_PATH = '/Users/yanzhang/Coding/News/Options_Change.csv' 
OUTPUT_RESULT_PATH = '/Users/yanzhang/Downloads/1.txt' # 最终结果存放
OUTPUT_DEBUG_PATH  = '/Users/yanzhang/Downloads/2.txt' # 验证过程存放

# 2. 算法参数
TOP_N = 20

# 【新功能】权重幂次配置
# 1 = 线性 (原版逻辑)
# 2 = 平方 (Square)
# 3 = 立方 (Cubic)
# 依次类推...
WEIGHT_POWER = 3

# 3. 调试配置
# 输入你想追踪的Symbol名字 (区分大小写，如 "NVDA" 或 "AAPL")
# 如果留空字符串 ""，则不生成调试文件
DEBUG_SYMBOL = "NVDA" 

# ===========================================

# 【修改】函数增加 power_config 参数
def calculate_d_score(df_path, res_path, debug_path, n_config, power_config, target_symbol):
    print(f"正在读取文件: {df_path} ...")
    print(f"当前配置: Top N = {n_config}, 权重幂次 = {power_config}")
    
    # 清空旧的调试文件
    if target_symbol:
        with open(debug_path, 'w') as f:
            f.write(f"=== {target_symbol} 计算过程追踪日志 ===\n")
            f.write(f"运行时间: {pd.Timestamp.now()}\n")
            f.write(f"权重幂次 (Power): {power_config}\n\n")

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

    # 按 Symbol 和 Type 分组计算
    results = []
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
            D = C * (n_config - 1) / total_oi
            
            # 收集每一行的数据方便调试打印
            for idx in range(len(top_items)):
                row_details.append({
                    'Expiry': top_items.iloc[idx]['Expiry Date'].strftime('%Y-%m-%d'),
                    '1-Day Chg': top_items.iloc[idx]['1-Day Chg'],
                    'Dist': top_items.iloc[idx]['Distance'],
                    'OI': top_items.iloc[idx]['Open Interest'],
                    'Days_i': days_i[idx],
                    'Diff_i': diff_i[idx],
                    'Diff_Pow': diff_pow[idx], # 记录计算出的幂次值
                    'Weight': w_i[idx],
                    'Score': scores[idx]
                })

        result_str = f"{symbol} {type_} D: {D:.6f}"
        results.append(result_str)

        # ================= 调试日志核心逻辑 =================
        if symbol == target_symbol:
            log_lines = []
            log_lines.append("-" * 80)
            log_lines.append(f"正在计算: {symbol} - {type_}")
            log_lines.append(f"当前参考日期: {today.strftime('%Y-%m-%d')}")
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
            log_lines.append(f"       D = ({C:.6f} * {n_config - 1}) / {total_oi}")
            log_lines.append(f"       D = {D:.6f}")
            log_lines.append("\n\n")

            # 写入调试文件
            with open(debug_path, 'a') as f:
                f.write('\n'.join(log_lines))
            
            print(f"  -> {symbol} {type_} 调试日志已更新")

        # ==================================================

    # 输出最终结果文件
    try:
        with open(res_path, 'w') as f:
            f.write('\n'.join(results))
        print(f"全部计算完成！结果已保存到: {res_path}")
    except Exception as e:
        print(f"保存文件出错: {e}")

if __name__ == "__main__":
    # 【修改】这里将 WEIGHT_POWER 传入函数
    calculate_d_score(INPUT_CSV_PATH, OUTPUT_RESULT_PATH, OUTPUT_DEBUG_PATH, TOP_N, WEIGHT_POWER, DEBUG_SYMBOL)
