import json
from collections import defaultdict

def check_duplicates(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    
    symbol_to_colors = defaultdict(list)
    duplicates = defaultdict(list)

    for color, symbols in data.items():
        for symbol in symbols:
            symbol_to_colors[symbol].append(color)
            if len(symbol_to_colors[symbol]) > 1:
                duplicates[symbol] = symbol_to_colors[symbol]

    if duplicates:
        print("发现重复的symbol及其所在的颜色分组：")
        for symbol, colors in duplicates.items():
            print(f"  {symbol}: {', '.join(colors)}")
    else:
        print("没有重复的symbol。")

    return duplicates

# 使用文件路径
# file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'
# file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
# file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_500.json'
# file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
file_path = '/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json'
check_duplicates(file_path)