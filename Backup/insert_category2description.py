import json

# 定义文件路径
file_path = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'

# 第一步：读取 JSON 文件
with open(file_path, 'r', encoding='utf-8') as file:
    data = json.load(file)  # 加载JSON数据

# 第二步：修改 JSON 数据
for group in ['stocks', 'etfs']:
    for item in data[group]:
        item['value'] = ""  # 在description2之后添加value为空字符串

# 第三步：将修改后的数据保存回文件
with open(file_path, 'w', encoding='utf-8') as file:
    json.dump(data, file, ensure_ascii=False, indent=2)  # 保存修改后的JSON数据，并保持缩进格式