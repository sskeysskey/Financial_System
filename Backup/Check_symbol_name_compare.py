import json

# 定义文件路径
file_path = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'

# 从文件中读取并解析JSON数据
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
except FileNotFoundError:
    print(f"错误：文件未找到，请检查路径 {file_path}")
    exit()
except json.JSONDecodeError:
    print(f"错误：文件 {file_path} 内容不是有效的JSON格式。")
    exit()

# 2. 初始化一个空列表，用于存放筛选出的 symbol
filtered_symbols = []

# 3. 将 stocks 和 etfs 列表合并，方便统一处理
items_to_check = json_data.get('stocks', []) + json_data.get('etfs', [])

# 4. 遍历所有项目，进行筛选
for item in items_to_check:
  # 检查 'symbol' 和 'name' 字段是否存在且内容完全相同
  if item.get('symbol') and item.get('name') and item['symbol'] == item['name']:
    # 【修改点 1】只将 symbol 字符串添加到列表中
    filtered_symbols.append(item['symbol'])

# 5. 打印最终筛选出的结果
print("筛选出的 Symbol 如下：")
if filtered_symbols:
  # 【修改点 2】遍历列表，逐行打印每个 symbol
  for symbol in filtered_symbols:
    print(symbol)
else:
  print("未找到任何 symbol 与 name 相同的条目。")