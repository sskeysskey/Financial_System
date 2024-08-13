import json

# 文件路径
event_file_path = '/Users/yanzhang/Documents/News/Economic_Events_new.txt'
sectors_panel_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
symbol_mapping_path = '/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json'

# 读取文件内容
with open(event_file_path, 'r', encoding='utf-8') as file:
    events = file.readlines()

with open(symbol_mapping_path, 'r', encoding='utf-8') as file:
    symbol_mapping = json.load(file)

with open(sectors_panel_path, 'r', encoding='utf-8') as file:
    sectors_panel = json.load(file)

# 清空Economics分组的数据
sectors_panel['Economics'] = {}

# 处理每个事件
for event in events:
    # 提取事件描述和日期中的天字段
    date_part, description_part = event.split(' : ')
    day_field = date_part.split('-')[-1].strip()
    description = description_part.split(' [')[0].strip()

    # 在symbol_mapping中查找匹配
    if description in symbol_mapping:
        economics_key = symbol_mapping[description]
        combined_value = f"{day_field} {economics_key}"

        # 更新sectors_panel中的Economics分组
        sectors_panel['Economics'][economics_key] = combined_value

# 将更新后的内容写回到Sectors_panel.json
with open(sectors_panel_path, 'w', encoding='utf-8') as file:
    json.dump(sectors_panel, file, ensure_ascii=False, indent=4)

print("更新已完成！")