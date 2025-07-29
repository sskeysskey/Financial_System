import json

def reorder_us_tag(data):
    # 处理 stocks 和 etfs 两个大类
    for category in ['stocks', 'etfs']:
        for item in data[category]:
            # 检查是否存在tag且至少有一个元素
            if 'tag' in item and item['tag']:
                tags = item['tag']
                # 如果"美国"在tags中且不在最后位置
                if "美国" in tags and tags[-1] != "美国":
                    # 移除"美国"标签
                    tags.remove("美国")
                    # 将"美国"添加到末尾
                    tags.append("美国")
    
    return data

# 读取文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/description.json', 'r', encoding='utf-8') as file:
    data = json.loads(file.read())

# 处理数据
modified_data = reorder_us_tag(data)

# 写回文件（使用格式化的JSON，便于阅读）
with open('/Users/yanzhang/Documents/Financial_System/Modules/description.json', 'w', encoding='utf-8') as file:
    json.dump(modified_data, file, ensure_ascii=False, indent=2)