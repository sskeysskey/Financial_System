import json
from collections import OrderedDict

# 假设您的JSON数据存储在一个名为data.json的文件中
input_filename = '/Users/yanzhang/Documents/Financial_System/Modules/Description.json'
output_filename = '/Users/yanzhang/Documents/Financial_System/Modules/Description_test3.json'

# 读取JSON数据
with open(input_filename, 'r', encoding='utf-8') as file:
    data = json.load(file)

# 遍历stocks和etfs，为每个条目添加tag字段
for category in ['stocks', 'etfs']:
    for item in data[category]:
        # 创建一个新的OrderedDict对象
        new_item = OrderedDict()
        for key, value in item.items():
            new_item[key] = value
            if key == 'symbol':  # 在name后立即插入tag
                new_item['tag'] = []  # 添加空的tag列表
        # 替换原来的字典项
        index = data[category].index(item)
        data[category][index] = new_item

# 将修改后的数据写回到新的JSON文件中
with open(output_filename, 'w', encoding='utf-8') as file:
    json.dump(data, file, ensure_ascii=False, indent=2)

print("JSON数据已成功修改并保存到", output_filename)