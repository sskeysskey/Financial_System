import yfinance as yf
import sqlite3
import json

# 读取JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors.json', 'r') as file:
    stock_groups = json.load(file)

today = datetime.date.today()

# 定义时间范围
start_date = "1978-12-14"
end_date = today.strftime('%Y-%m-%d')

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
c = conn.cursor()

# 定义parent_id的映射
parent_ids = {
    "Basic_Materials": 13,
    "Communication_Services": 20,
    "Consumer_Cyclical": 15,
    "Consumer_Defensive": 16,
    "Energy": 12,
    "Financial_Services": 18,
    "Healthcare": 17,
    "Industrials": 14,
    "Real_Estate": 22,
    "Technology": 19,
    "Utilities": 21
}

# 遍历所有组和子组
for group_name, subgroups in stock_groups.items():
    subgroup_counter = {subgroup_name: 0 for subgroup_name in subgroups}  # 初始化计数器
    for subgroup_name, tickers in subgroups.items():
        for ticker_symbol in tickers:
            # 使用 yfinance 下载股票数据
            data = yf.download(ticker_symbol, start=start_date, end=end_date)

            # 插入数据到相应的表中
            table_name = group_name.replace(" ", "_")  # 确保表名没有空格
            for index, row in data.iterrows():
                date = index.strftime('%Y-%m-%d')
                price = round(row['Adj Close'], 2)  # 对价格进行四舍五入保留两位小数
                volume = int(row['Volume'])  # 将交易量转换为整数
                c.execute(f"INSERT INTO {table_name} (date, name, price, volume, parent_id) VALUES (?, ?, ?, ?, ?)",
                          (date, ticker_symbol, price, volume, parent_ids[group_name]))
            subgroup_counter[subgroup_name] += 1  # 更新计数器

    # 使用print输出每个大组的统计信息
    print(f"{group_name} statistics:")
    for subgroup_name, count in subgroup_counter.items():
        print(f"  {subgroup_name}: {count} stocks inserted.")

# 提交事务
conn.commit()

# 关闭连接
conn.close()

print("所有数据已成功写入数据库")