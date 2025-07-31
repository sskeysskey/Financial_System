import json

# 读取a.json文件
with open('/Users/yanzhang/Coding/Financial_System/Modules/description.json', 'r', encoding='utf-8') as f:
    data_a = json.load(f)

# 提取etfs分类下的所有symbol字段
etf_symbols = [etf['symbol'] for etf in data_a.get('etfs', [])]

# 读取b.json文件
with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'r', encoding='utf-8') as f:
    data_b = json.load(f)

# 将提取的symbol字段追加到b.json文件的ETFs分类中
data_b['ETFs'].extend(etf_symbols)

# 保存修改后的b.json文件
with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'w', encoding='utf-8') as f:
    json.dump(data_b, f, ensure_ascii=False, indent=4)

print("ETFs分类下的所有symbol字段已成功追加到b.json文件的ETFs分类中。")