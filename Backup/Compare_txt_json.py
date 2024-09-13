import json

# 读取etf.txt文件内容
with open('/Users/yanzhang/Documents/News/backup/ETFs.txt', 'r', encoding='utf-8') as file:
    etf_lines = file.readlines()

# 提取etf.txt中的symbols
etf_txt_symbols = {line.split(':')[0].strip() for line in etf_lines}

# 读取a.json文件内容
with open('/Users/yanzhang/Documents/Financial_System/Modules/description.json', 'r', encoding='utf-8') as file:
    json_data = json.load(file)

# 提取a.json中的etf symbols
json_etf_symbols = {etf['symbol'] for etf in json_data['etfs']}

# 找出txt中有但json中没有的symbols
txt_not_in_json = etf_txt_symbols - json_etf_symbols

# 找出json中有但txt中没有的symbols
json_not_in_txt = json_etf_symbols - etf_txt_symbols

# 输出结果
print("在etf.txt中出现但在a.json中没有的symbols:")
for symbol in txt_not_in_json:
    print(symbol)

print("\n在a.json中出现但在etf.txt中没有的symbols:")
for symbol in json_not_in_txt:
    print(symbol)