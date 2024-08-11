import json

def check_duplicates(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    
    symbol_set = set()
    duplicates = set()

    for color, symbols in data.items():
        for symbol in symbols:
            if symbol in symbol_set:
                duplicates.add(symbol)
            else:
                symbol_set.add(symbol)

    if duplicates:
        print("发现重复的symbol：", duplicates)
    else:
        print("没有重复的symbol。")

# 使用你的文件路径
file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
check_duplicates(file_path)