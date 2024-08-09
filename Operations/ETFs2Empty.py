import json

# 文件路径列表
json_file_paths = [
    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json',
    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json',
    '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json'
]
etf_file_path = '/Users/yanzhang/Documents/News/ETFs_new.txt'

# 读取ETF符号
etf_symbols = []
with open(etf_file_path, 'r') as etf_file:
    for line in etf_file:
        symbol = line.split(':')[0].strip()
        etf_symbols.append(symbol)

# 逐个更新JSON文件
for json_file_path in json_file_paths:
    # 读取JSON文件并更新ETFs组
    with open(json_file_path, 'r') as json_file:
        data = json.load(json_file)
        data['ETFs'].extend(etf_symbols)

    # 将更新后的数据写回JSON文件
    with open(json_file_path, 'w') as json_file:
        json.dump(data, json_file, indent=2)

print("所有文件更新完成！")