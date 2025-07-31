import json
from collections import Counter

# 指定你的JSON文件路径
json_file_path = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'

# 读取并解析JSON文件
with open(json_file_path, 'r', encoding='utf-8') as file:
    data = json.load(file)

# 检查每个组中的symbol是否有重复
def check_duplicates(group_data, group_name):
    symbols = [item['symbol'] for item in group_data]
    symbol_counts = Counter(symbols)
    duplicates = [symbol for symbol, count in symbol_counts.items() if count > 1]
    
    if duplicates:
        print(f"{group_name} 组中有重复的 symbol: {', '.join(duplicates)}")
    else:
        print(f"{group_name} 组中没有重复的 symbol。")

# 检查 stocks 组
check_duplicates(data['stocks'], 'stocks')

# 检查 etfs 组
check_duplicates(data['etfs'], 'etfs')

# 检查 stocks 和 etfs 组之间的重复
def check_cross_group_duplicates(stocks_data, etfs_data):
    stocks_symbols = set(item['symbol'] for item in stocks_data)
    etfs_symbols = set(item['symbol'] for item in etfs_data)
    
    # 获取两个集合的交集，即重复的symbol
    common_symbols = stocks_symbols & etfs_symbols
    
    if common_symbols:
        print(f"stocks 和 etfs 组之间有重复的 symbol: {', '.join(common_symbols)}")
    else:
        print("stocks 和 etfs 组之间没有重复的 symbol。")

# 检查两个组之间的重复
check_cross_group_duplicates(data['stocks'], data['etfs'])