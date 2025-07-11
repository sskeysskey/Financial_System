import json
import tkinter as tk
from tkinter import simpledialog

# 定义文件路径
SECTORS_FILE = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
DESCRIPTION_FILE = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'

# 读取JSON文件
def load_json_files():
    with open(SECTORS_FILE, 'r', encoding='utf-8') as f:
        sectors = json.load(f)
    with open(DESCRIPTION_FILE, 'r', encoding='utf-8') as f:
        descriptions = json.load(f)
    return sectors, descriptions

# 检查symbol是否存在于stocks中
def check_symbol_exists(symbol, stocks):
    return any(stock['symbol'] == symbol for stock in stocks)

# 创建新的stock项
def create_new_stock(symbol, input_text):
    tags = input_text.split()
    return {
        "symbol": symbol,
        "name": symbol,
        "tag": tags,
        "description1": "",
        "description2": "",
        "description3": [{}],
        "value": ""
    }

def process_all_sectors():
    # 读取JSON文件
    sectors, descriptions = load_json_files()
    
    # 创建tkinter根窗口但不显示
    root = tk.Tk()
    root.withdraw()
    
    modified = False
    
    # 遍历sectors中的所有分组，排除 "ETFs" 分组
    for group, symbols in sectors.items():
        if group == "ETFs":
            print(f"跳过分组: {group}")
            continue
        print(f"正在处理分组: {group} ...")
        for symbol in symbols:
            # 检查symbol是否存在于stocks中
            if not check_symbol_exists(symbol, descriptions['stocks']):
                prompt = f"在'{group}'分组中，Symbol '{symbol}' 不存在于stocks中。\n请输入标签（用空格分隔）："
                user_input = simpledialog.askstring("输入标签", prompt)
                if user_input:
                    # 创建新的stock项并添加到descriptions中
                    new_stock = create_new_stock(symbol, user_input)
                    descriptions['stocks'].append(new_stock)
                    modified = True
                    print(f"已添加新的stock项: {symbol} (分组: {group})")
    
    # 如果有修改，则保存到文件
    if modified:
        try:
            with open(DESCRIPTION_FILE, 'w', encoding='utf-8') as f:
                json.dump(descriptions, f, ensure_ascii=False, indent=2)
                print("文件已更新")
        except Exception as e:
            print("文件写入失败:", str(e))
    else:
        print("所有分组中均无需要添加的项目")
    
    root.destroy()

if __name__ == "__main__":
    process_all_sectors()