import json
import re

# 读取JSON文件内容
with open('/Users/yanzhang/Documents/Financial_System/Modules/Description.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

# 修改etfs分组中每一个symbol对应的name字段
for etf in data['etfs']:
    etf['name'] = re.sub(r', \d+$', '', etf['name'])

# 将修改后的内容写回到JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Description1.json', 'w', encoding='utf-8') as file:
    json.dump(data, file, ensure_ascii=False, indent=2)

print("修改完成，输出已保存到output.json文件中。")