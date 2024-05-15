import re
import sys
import json
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from API_input_Name2Chart import plot_financial_data

def load_sector_data():
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_Stock.json', 'r') as file:
        sector_data = json.load(file)
    return sector_data

def load_compare_data():
    # 根据当前日期生成文件名
    timestamp = datetime.now().strftime("%m_%d")
    file_name = f'/Users/yanzhang/Documents/News/Compare_Stocks_{timestamp}.txt'

    compare_data = {}
    with open(file_name, 'r') as file:
        for line in file.readlines():
            parts = line.split(':')
            key = parts[0].split()[-1].strip()  # 获取最后一个单词，即MTD, GEN等
            value = parts[1].strip()  # 获取冒号后的百分比数据
            compare_data[key] = value
    return compare_data

def load_marketcap_pe_data():
    marketcap_pe_data = {}
    with open('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', 'r') as file:
        for line in file.readlines():
            parts = line.split(':')
            key = parts[0].strip()
            values = parts[1].split(',')
            marketcap = float(values[0].strip())
            pe = values[1].strip()
            marketcap_pe_data[key] = (marketcap, pe)
    return marketcap_pe_data

def load_json_data(json_path):
        with open(json_path, 'r', encoding='utf-8') as file:
            return json.load(file)

def input_mapping(root, sector_data, compare_data, marketcap_pe_data, json_data):
    # 获取用户输入
    prompt = "请输入"
    user_input = get_user_input_custom(root, prompt)
    
    if user_input is None:
        print("未输入任何内容，程序即将退出。")
        close_app(root)
    else:
        input_trimmed = user_input.strip()
        lower_input = input_trimmed.lower()
        upper_input = input_trimmed.upper()
        
        # 先进行完整匹配查找
        exact_match_found_upper = False
        for sector, categories in sector_data.items():
            for category, names in categories.items():
                if upper_input in names:
                    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
                    compare = compare_data.get(upper_input, "N/A")
                    marketcap_pe = marketcap_pe_data.get(upper_input, (None, 'N/A'))
                    marketcap, pe = marketcap_pe
                    plot_financial_data(db_path, sector, upper_input, compare, marketcap, pe, json_data)
                    exact_match_found_upper = True
                    close_app(root)
                    break
            if exact_match_found_upper:
                break

        # 如果没有找到完整匹配，则进行模糊匹配
        if not exact_match_found_upper:
            found = False
            for sector, categories in sector_data.items():
                for category, names in categories.items():
                    for name in names:
                        if re.search(lower_input, name.lower()):
                            db_path = "/Users/yanzhang/Documents/Database/Finance.db"
                            compare = compare_data.get(name, "N/A")
                            marketcap_pe = marketcap_pe_data.get(name, (None, 'N/A'))
                            marketcap, pe = marketcap_pe
                            plot_financial_data(db_path, sector, name, compare, marketcap, pe, json_data)
                            found = True
                            close_app(root)
                            break
                    if found:
                        break
                if found:
                    break

            if not found:
                messagebox.showerror("错误", "未找到匹配的数据项。")
                close_app(root)

def get_user_input_custom(root, prompt):
    # 创建一个新的顶层窗口
    input_dialog = tk.Toplevel(root)
    input_dialog.title(prompt)
    # 设置窗口大小和位置
    window_width = 280
    window_height = 90
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 3 - window_height / 2)  # 将窗口位置提升到屏幕1/3高度处
    input_dialog.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

    # 添加输入框，设置较大的字体和垂直填充
    entry = tk.Entry(input_dialog, width=20, font=('Helvetica', 18))
    entry.pack(pady=20, ipady=10)  # 增加内部垂直填充
    entry.focus_set()

    # 设置确认按钮，点击后销毁窗口并返回输入内容
    def on_submit():
        nonlocal user_input
        user_input = entry.get()
        input_dialog.destroy()

    # 绑定回车键和ESC键
    entry.bind('<Return>', lambda event: on_submit())
    input_dialog.bind('<Escape>', lambda event: input_dialog.destroy())

    # 运行窗口，等待用户输入
    user_input = None
    input_dialog.wait_window(input_dialog)
    return user_input

def close_app(root):
    if root:
        root.quit()  # 更安全的关闭方式
        root.destroy()  # 使用destroy来确保彻底关闭所有窗口和退出

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()  # 隐藏根窗口
    root.bind('<Escape>', close_app)  # 同样绑定ESC到关闭程序的函数

    # plt.rcParams['font.sans-serif'] = ['Songti SC']  # 指定默认字体
    # plt.rcParams['axes.unicode_minus'] = False  # 解决保存图像是负号'-'显示为方块的问题

    sector_data = load_sector_data()
    compare_data = load_compare_data()
    marketcap_pe_data = load_marketcap_pe_data()
    json_data = load_json_data("/Users/yanzhang/Documents/Financial_System/Modules/Description.json")
    input_mapping(root, sector_data, compare_data, marketcap_pe_data, json_data)
    # 加载 JSON 数据
    

    root.mainloop()  # 主事件循环