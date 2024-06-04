import json
import pyperclip
import tkinter as tk
from tkinter import messagebox

json_file = "/Users/yanzhang/Documents/Financial_System/Modules/Description.json"
with open(json_file, 'r', encoding='utf-8') as file:
    data = json.load(file)

# 从剪贴板获取第一个新的name字段内容
new_name = pyperclip.paste()
# 去除新name的所有引号
new_name = new_name.replace('"', '').replace("'", "")

# 检查新的name是否已存在于etfs中
exists_etf = any(etf['name'] == new_name for etf in data.get('etfs', []))
exists_stock = any(stock['name'] == new_name for stock in data.get('stocks', []))

if exists_etf or exists_stock:
    messagebox.showerror("错误", "ETF代码已存在！")
    sys.exit()