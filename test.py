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

# 检查是否存在于stocks中
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

def process_bonds_sector():
    # 读取JSON文件
    sectors, descriptions = load_json_files()
    
    # 创建tkinter根窗口但不显示
    root = tk.Tk()
    root.withdraw()
    
    # 只处理Bonds分组
    modified = False
    bonds_symbols = sectors.get('Commodities', [])
    
    print("开始处理Bonds分组...")
    for symbol in bonds_symbols:
        # 检查symbol是否存在于stocks中
        if not check_symbol_exists(symbol, descriptions['stocks']):
            # 弹出输入框
            prompt = f"Symbol '{symbol}' 不存在于stocks中。请输入标签（用空格分隔）："
            user_input = simpledialog.askstring("输入标签", prompt)
            
            if user_input:
                # 创建新的stock项并添加到descriptions中
                new_stock = create_new_stock(symbol, user_input)
                descriptions['stocks'].append(new_stock)
                modified = True
                print(f"已添加新的stock项: {symbol}")
    
    # 如果有修改，保存到文件
    if modified:
        try:
            with open(DESCRIPTION_FILE, 'w', encoding='utf-8') as f:
                json.dump(descriptions, f, ensure_ascii=False, indent=2)
                print("文件已更新")
        except Exception as e:
            print("文件写入失败:", str(e))
    else:
        print("Bonds分组中没有需要添加的项目")

    root.destroy()

if __name__ == "__main__":
    process_bonds_sector()