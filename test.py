import sqlite3
import pandas as pd
import numpy as np
from scipy import stats

# —— 参数区 —— 
DB_PATH     = "/Users/yanzhang/Coding/Database/Finance.db"
TABLES      = [
    'Basic_Materials','Consumer_Cyclical','Real_Estate','Energy',
    'Technology','Utilities','Industrials','Consumer_Defensive',
    'Communication_Services','Financial_Services','Healthcare'
]
WINDOW        = 30       # 滚动窗口大小（天）
AMP_THRESH    = 0.04     # 振幅阈值，如 0.04 表示 4%
SLOPE_THRESH  = 0.0005   # 斜率阈值

# —— 算法函数 —— 
def detect_sideways(price_series, window, amp_thresh, slope_thresh):
    """
    给定一支股票的收盘价序列 price_series (pd.Series)，
    返回一个布尔 pd.Series，标记每一天是否满足“横盘震荡”。
    """
    df = pd.DataFrame({'price': price_series})
    # 1) 振幅 = (window 期内 max - min) / mean
    df['high_max'] = df['price'].rolling(window).max()
    df['low_min']  = df['price'].rolling(window).min()
    df['mid_price']= df['price'].rolling(window).mean()
    df['amplitude'] = (df['high_max'] - df['low_min']) / df['mid_price']

    # 2) 线性回归斜率
    def _slope(x):
        y = x.values
        t = np.arange(len(y))
        return stats.linregress(t, y).slope

    df['slope'] = df['price'].rolling(window).apply(_slope, raw=False)

    # 3) 同时满足振幅和斜率阈值
    return (df['amplitude'] < amp_thresh) & (df['slope'].abs() < slope_thresh)

# —— 主流程 —— 
def main():
    conn = sqlite3.connect(DB_PATH)
    all_results = []

    for tbl in TABLES:
        # 1) 读表
        sql = f"SELECT date, name, price FROM {tbl}"
        df = pd.read_sql_query(sql, conn, parse_dates=['date'])
        df.sort_values(['name','date'], inplace=True)

        # 2) 按股票分组，逐支股票检测
        for symbol, grp in df.groupby('name'):
            grp = grp.reset_index(drop=True)
            if len(grp) < WINDOW:
                continue  # 数据不够
            sideways_flags = detect_sideways(grp['price'], WINDOW, AMP_THRESH, SLOPE_THRESH)
            # 如果最后一天为 True，就认为它“当前”处于横盘震荡
            if sideways_flags.iloc[-1]:
                all_results.append({
                    'table': tbl,
                    'symbol': symbol,
                    'last_date': grp['date'].iloc[-1],
                    'last_price': grp['price'].iloc[-1]
                })

    conn.close()

    result_df = pd.DataFrame(all_results)
    if result_df.empty:
        print("当前没有股票满足横盘震荡条件。")
    else:
        print("当前处于横盘震荡的股票：")
        print(result_df.sort_values(['table','symbol']).to_string(index=False))

if __name__ == "__main__":
    main()