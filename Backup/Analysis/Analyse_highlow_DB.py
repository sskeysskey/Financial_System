import pandas as pd
import sqlite3
from datetime import datetime

def analyze_stock_data(file_path, db_path):
    data = pd.read_csv(file_path, sep=" ", header=None, names=["Industry", "StockCode", "Status"])
    
    coefficients = {
        "Basic_Materials": 72,
        "Communication_Services": 62,
        "Consumer_Cyclical": 155,
        "Consumer_Defensive": 63,
        "Energy": 82,
        "Financial_Services": 187,
        "Healthcare": 131,
        "Industrials": 178,
        "Real_Estate": 62,
        "Technology": 195,
        "Utilities": 48
    }

    # 使用 na=False 处理 NaN 值
    newhigh_counts = data[data['Status'].str.contains('newhigh', na=False)].groupby('Industry').size()
    newlow_counts = data[data['Status'].str.contains('newlow', na=False)].groupby('Industry').size()

    newhigh_adjusted = newhigh_counts.div(pd.Series(coefficients)).fillna(0)
    newlow_adjusted = newlow_counts.div(pd.Series(coefficients)).fillna(0)

    total_newhigh_adjusted = newhigh_adjusted.sum()
    total_newlow_adjusted = newlow_adjusted.sum()

    newhigh_percentage = newhigh_adjusted / total_newhigh_adjusted * 100
    newlow_percentage = newlow_adjusted / total_newlow_adjusted * 100

    # Sorting data
    newhigh_sorted = newhigh_adjusted.sort_values(ascending=False)
    newlow_sorted = newlow_adjusted.sort_values(ascending=False)
    
    # Save to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    date_today = datetime.now().strftime("%Y-%m-%d")
    for industry in newhigh_sorted.index:
        cursor.execute("INSERT OR IGNORE INTO High_low (date, name, rate) VALUES (?, ?, ?)", 
                       (date_today, industry, newhigh_sorted[industry]))
    conn.commit()
    conn.close()

    print("NewHighs:")
    for industry in newhigh_sorted.index:
        print(f"{industry:25s} {newhigh_sorted[industry]:>7.4f} {newhigh_percentage[industry]:>6.2f}%")
    print("\nNewLows:")
    for industry in newlow_sorted.index:
        print(f"{industry:25s} {newlow_sorted[industry]:>7.4f} {newlow_percentage[industry]:>6.2f}%")
    
    return newhigh_sorted, newlow_sorted

def main():
    file_path = '/Users/yanzhang/Coding/News/backup/site/AnalyseStock.txt'
    db_path = '/Users/yanzhang/Coding/Database/Analysis.db'
    newhigh_sorted, newlow_sorted = analyze_stock_data(file_path, db_path)
    print("成功写入数据库")

if __name__ == "__main__":
    main()