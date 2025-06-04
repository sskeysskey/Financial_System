import json

# 1. 定义文件路径
empty_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
holiday_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_US_holiday.json'

# 2. 读取原始 JSON (Sectors_empty.json)
try:
    with open(empty_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"警告: 文件 {empty_file_path} 未找到。将使用空字典初始化。")
    data = {}  # 如果文件不存在，则初始化为空字典
except json.JSONDecodeError:
    print(f"警告: 解析文件 {empty_file_path} JSON失败。将使用空字典初始化。")
    data = {}  # 如果JSON解析失败，则初始化为空字典

# 3. 读取 holiday JSON (Sectors_US_holiday.json)
try:
    with open(holiday_file_path, 'r', encoding='utf-8') as f:
        data_holiday = json.load(f)
except FileNotFoundError:
    print(f"警告: 文件 {holiday_file_path} 未找到。将跳过从此文件合并数据。")
    data_holiday = {} # 如果文件不存在，则初始化为空字典
except json.JSONDecodeError:
    print(f"警告: 解析文件 {holiday_file_path} JSON失败。将跳过从此文件合并数据。")
    data_holiday = {} # 如果JSON解析失败，则初始化为空字典

# 4. 将 holiday 文件中的项目按组名添加到 data 中（参考 Crypto 的去重合并方式）
for category, items_from_holiday in data_holiday.items():
    # 确保 holiday 文件中该类别下的项目是一个列表
    if not isinstance(items_from_holiday, list):
        print(f"注意: {holiday_file_path} 中 '{category}' 类别下的项目不是一个列表，已跳过该类别。")
        continue

    # 获取 data 中已有的该类别下的项目，如果不存在或不是列表，则视为空列表
    current_items_in_data = data.get(category, [])
    if not isinstance(current_items_in_data, list):
        print(f"注意: {empty_file_path} 中 '{category}' 类别下的内容不是一个列表 (实际为: {type(current_items_in_data)})。将视为空列表进行合并。")
        current_items_in_data = []
    
    # 使用集合进行合并以自动去重
    set_current_items = set(current_items_in_data)
    set_items_from_holiday = set(items_from_holiday)
    
    # 更新 data 中该类别的内容
    data[category] = list(set_current_items.union(set_items_from_holiday))

# 6. 写回文件
with open(empty_file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# 7. 打印更新确认信息
print(f"✅ '{empty_file_path}' 文件已成功更新。")
# 使用 .get(key, []) 来安全地获取列表，以防某个键不存在
print("✅ 已将 Crypto 更新为：", data.get('Crypto', []))
print("✅ 已将 Commodities 更新为：", data.get('Commodities', []))

# 如果您想查看所有更新后的类别，可以取消以下代码的注释
print("\n--- 所有更新后的类别详情 ---")
for category_name, category_items in data.items():
    if isinstance(category_items, list):
        print(f"  {category_name}: {category_items}")
    else:
        # 这种情况通常不应该发生，除非JSON结构本身有问题
        print(f"  {category_name}: {category_items} (注意: 此类别内容非列表格式)")
print("--------------------------")