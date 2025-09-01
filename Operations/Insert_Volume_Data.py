import json

# 读取三个JSON文件
with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json', 'r') as f:
    panel_data = json.load(f)

with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'r') as f:
    all_data = json.load(f)

with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json', 'r') as f:
    empty_data = json.load(f)

# 需要处理的分组
target_groups = ["Today", "Watching", "Next Week", "2 Weeks", "3 Weeks", 
                "Strategy12", "Strategy34", "PE_valid", "PE_invalid"]

# 收集所有符号并去重
symbols = set()
for group in target_groups:
    if group in panel_data:
        symbols.update(panel_data[group].keys())

# 创建符号到分组的映射
symbol_to_sector = {}
for sector, symbols_list in all_data.items():
    for symbol in symbols_list:
        symbol_to_sector[symbol] = sector

# 将符号按分组放入empty_data
for symbol in symbols:
    if symbol in symbol_to_sector:
        sector = symbol_to_sector[symbol]
        if symbol not in empty_data[sector]:
            empty_data[sector].append(symbol)

# 写入更新后的empty.json
with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json', 'w') as f:
    json.dump(empty_data, f, indent=2)