import pandas as pd
import sqlite3
import numpy as np
import os

# ==============================================================================
# 1. 参数与阈值设置 (Configuration and Thresholds)
# ==============================================================================

# 数据库文件路径
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'
# CSV文件路径
CSV_PATH = '/Users/yanzhang/Downloads/recent_3months.csv'

# 需要扫描的数据库中的表名列表
# 您可以根据需要添加或删除表名
# TABLE_NAMES = [
#     'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
#     'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
#     'Communication_Services', 'Financial_Services', 'Healthcare'
# ]
TABLE_NAMES = [
    'Financial_Services'
]

# 定义用于分析的时间窗口（单位：交易日）
ANALYSIS_WINDOW_DAYS = 30

# --- 核心阈值定义 ---
# 这两个阈值是根据对UWMC的分析以及经验设定的。
# 您可以调整这些值来改变扫描的严格程度。

# 变异系数 (CV) 阈值。值越小，筛选条件越严格，要求价格波动越小。
# CV = 标准差 / 平均值
CV_THRESHOLD = 0.0327  # 小于5%的变异系数被认为是低波动

# 价格区间百分比阈值。值越小，筛选条件越严格，要求价格振幅范围越窄。
# Range % = (最高价 - 最低价) / 平均价
PRICE_RANGE_THRESHOLD = 0.1688  # 价格波动范围要求在15%以内

# ==============================================================================
# 2. 核心扫描算法 (The Core Scanner Algorithm)
# ==============================================================================

def is_sideways_consolidation(price_series: pd.Series) -> bool:
    """
    判断一只股票在给定价格序列中是否处于横盘震荡状态。
    
    Args:
        price_series (pd.Series): 包含股票价格的时间序列数据。

    Returns:
        bool: 如果股票符合横盘震荡条件，则返回 True，否则返回 False。
    """
    # 确保有足够的数据进行分析 (至少是窗口期的80%)
    if len(price_series) < ANALYSIS_WINDOW_DAYS * 0.8:
        return False

    # 计算统计指标
    mean_price = price_series.mean()
    std_dev = price_series.std()
    max_price = price_series.max()
    min_price = price_series.min()

    # 避免除以零的错误
    if mean_price == 0:
        return False

    # 计算变异系数 (Coefficient of Variation)
    coeff_variation = std_dev / mean_price
    
    # 计算价格区间百分比
    price_range_pct = (max_price - min_price) / mean_price

    # 判断是否同时满足两个核心条件
    is_low_volatility = coeff_variation < CV_THRESHOLD
    is_narrow_range = price_range_pct < PRICE_RANGE_THRESHOLD

    return is_low_volatility and is_narrow_range

# ==============================================================================
# 3. 功能函数 (Utility Functions)
# ==============================================================================

def analyze_uwmc_from_csv(file_path: str):
    """
    首先从CSV文件中加载UWMC的数据，验证我们的算法和阈值能正确识别它。
    """
    print("--- 步骤 1: 分析并验证基准股票 UWMC ---")
    if not os.path.exists(file_path):
        print(f"错误: CSV文件未找到于 '{file_path}'")
        return

    try:
        df = pd.read_csv(file_path)
        uwmc_data = df[df['name'] == 'UWMC']['price']

        if uwmc_data.empty:
            print("错误: 在CSV文件中未找到 'UWMC' 的数据。")
            return
            
        print(f"成功加载 UWMC 数据，共 {len(uwmc_data)} 条记录。")

        # 使用与主扫描器相同的窗口进行分析
        if len(uwmc_data) >= ANALYSIS_WINDOW_DAYS:
            uwmc_data_window = uwmc_data.tail(ANALYSIS_WINDOW_DAYS)
        else:
            uwmc_data_window = uwmc_data

        # 计算UWMC的指标
        mean_p = uwmc_data_window.mean()
        std_d = uwmc_data_window.std()
        max_p = uwmc_data_window.max()
        min_p = uwmc_data_window.min()
        
        cv = std_d / mean_p
        range_pct = (max_p - min_p) / mean_p

        print(f"\nUWMC 指标分析 (最近 {len(uwmc_data_window)} 天):")
        print(f"  - 平均价格: {mean_p:.2f}")
        print(f"  - 变异系数 (CV): {cv:.4f} (阈值: < {CV_THRESHOLD})")
        print(f"  - 价格区间百分比: {range_pct:.4f} (阈值: < {PRICE_RANGE_THRESHOLD})")

        # 验证算法
        if is_sideways_consolidation(uwmc_data_window):
            print("\n验证成功: 扫描器正确将 UWMC 识别为横盘震荡状态。")
        else:
            print("\n验证失败: 扫描器未能识别 UWMC。您可能需要调整阈值。")
        print("-" * 40 + "\n")

    except Exception as e:
        print(f"分析UWMC时发生错误: {e}")

def scan_database_for_consolidation(db_path: str, tables: list):
    """
    连接到SQLite数据库，遍历所有指定的表和股票，扫描处于横盘震荡状态的股票。
    """
    print(f"--- 步骤 2: 开始扫描数据库 '{db_path}' ---")
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件未找到于 '{db_path}'")
        return

    consolidating_stocks = {}
    
    try:
        conn = sqlite3.connect(db_path)
        
        for table in tables:
            print(f"\n正在扫描表: '{table}'...")
            consolidating_stocks[table] = []
            
            # 使用pandas直接从SQL查询中获取所有唯一的股票名称
            try:
                stock_names_df = pd.read_sql_query(f"SELECT DISTINCT name FROM '{table}'", conn)
                stock_names = stock_names_df['name'].tolist()
            except pd.io.sql.DatabaseError:
                print(f"  - 无法从表 '{table}' 读取数据，可能该表不存在或为空。跳过。")
                continue

            # 遍历表中的每一只股票
            for i, name in enumerate(stock_names):
                # 打印进度
                print(f"  - 正在分析 {i+1}/{len(stock_names)}: {name}", end='\r')
                
                # 查询该股票最近N天的数据
                query = f"""
                SELECT price 
                FROM '{table}' 
                WHERE name = ? 
                ORDER BY date DESC 
                LIMIT {ANALYSIS_WINDOW_DAYS}
                """
                
                stock_df = pd.read_sql_query(query, conn, params=(name,))
                
                if not stock_df.empty:
                    price_series = stock_df['price']
                    if is_sideways_consolidation(price_series):
                        consolidating_stocks[table].append(name)
                        # 清除进度行并打印找到的股票
                        print(f"  - 发现横盘震荡股票: {name} (表: {table})" + " " * 20)


            print(f"\n  - '{table}' 表扫描完成。")

        conn.close()
        return consolidating_stocks

    except sqlite3.Error as e:
        print(f"数据库操作失败: {e}")
        return None
    except Exception as e:
        print(f"扫描过程中发生未知错误: {e}")
        return None

def print_results(results: dict):
    """
    格式化并打印最终的扫描结果。
    """
    print("\n\n--- 最终扫描结果: 横盘震荡的股票 ---")
    total_found = 0
    if not results:
        print("未找到任何符合条件的股票。")
        return

    for table, stocks in results.items():
        if stocks:
            print(f"\n板块: {table}")
            print("-" * (len(table) + 5))
            for stock in stocks:
                print(f"  - {stock}")
            total_found += len(stocks)
        
    if total_found == 0:
        print("\n在所有指定的板块中，未找到符合当前阈值的横盘震荡股票。")
        print("您可以尝试放宽 CV_THRESHOLD 或 PRICE_RANGE_THRESHOLD 的值来扩大搜索范围。")
    else:
        print(f"\n总共发现 {total_found} 只处于横盘震荡状态的股票。")


# ==============================================================================
# 4. 主程序入口 (Main Execution Block)
# ==============================================================================

if __name__ == '__main__':
    # 步骤 1: 验证基准股票UWMC
    # analyze_uwmc_from_csv(CSV_PATH)
    
    # 步骤 2: 扫描整个数据库
    final_results = scan_database_for_consolidation(DB_PATH, TABLE_NAMES)
    
    # 步骤 3: 打印最终结果
    if final_results:
        print_results(final_results)