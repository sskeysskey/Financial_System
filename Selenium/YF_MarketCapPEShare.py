from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os
import json
import time
import random
import pyautogui
import pyperclip
import threading
import subprocess
import tkinter as tk
from tkinter import ttk
import argparse

def Copy_Command_C():
    script = '''
    set the clipboard to ""
    delay 0.3
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def show_yes_no_dialog(message):
    """显示是/否对话框并返回用户选择结果"""
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"否", "是"}} default button "是"'
    
    # 使用subprocess调用osascript并获取返回结果
    result = subprocess.run(['osascript', '-e', applescript_code], 
                            capture_output=True, text=True, check=False)
    
    # 检查返回结果是否包含"是"按钮被点击的信息
    return "button returned:是" in result.stdout

# 新增：命令行参数处理
def parse_arguments():
    parser = argparse.ArgumentParser(description='股票数据抓取工具')
    parser.add_argument('--mode', type=str, default='normal', 
                        help='运行模式: normal或empty。默认为normal')
    parser.add_argument('--clear', action='store_true',
                        help='抓取结束后直接清空 Sectors_empty.json，无需弹窗确认')
    return parser.parse_args()

def check_empty_json_has_content(json_file_path):
    """检查empty.json中是否有任何分组包含内容"""
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    
    for group, items in data.items():
        if items:  # 如果该分组有任何项目
            return True
    
    return False

def add_symbol_to_json_files(symbol, group):
    """将symbol添加到指定的JSON文件的对应分组中"""
    base_dir = "/Users/yanzhang/Documents/Financial_System/Modules/"
    json_files = ["Sectors_empty.json", "Sectors_All.json", "Sectors_today.json"]
    
    for json_file in json_files:
        file_path = os.path.join(base_dir, json_file)
        
        # 如果文件不存在，创建一个空的JSON结构
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                json.dump({}, f)
        
        # 读取文件内容
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # 如果组不存在，创建一个空列表
        if group not in data:
            data[group] = []
        
        # 如果symbol不在该组中，添加它
        if symbol not in data[group]:
            data[group].append(symbol)
        
        # 写回文件
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

def show_input_dialog(default_symbol=""):
    """
    修改后的对话框：
    仅用于输入symbol，输入后自动转换为大写，不需要选择分组
    """
    def close_app(event=None):
        root.quit()
    
    root = tk.Tk()
    root.title("输入Symbol")
    root.geometry("400x150")
    root.lift()
    root.focus_force()
    root.bind('<Escape>', close_app)
    
    symbol = ""
    
    # 创建输入框和标签
    tk.Label(root, text="请输入Stock Symbol:").pack(pady=10)
    symbol_entry = tk.Entry(root)
    symbol_entry.pack(pady=5)
    
    if default_symbol:
        symbol_entry.insert(0, default_symbol)
    
    symbol_entry.focus_set()
    
    def on_ok():
        nonlocal symbol
        symbol = symbol_entry.get().strip().upper()  # 自动转换为大写
        root.destroy()
    
    def on_cancel():
        root.destroy()
    
    # 创建按钮
    button_frame = tk.Frame(root)
    button_frame.pack(pady=20)
    
    tk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=10)
    tk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    return symbol

def convert_shares_format(shares_str):
    # 转换股票数量的表示方式，例如 "15.33B" 转换为 15330000000
    if shares_str == 'N/A' or shares_str == '-':
        return 0
    
    if 'T' in shares_str:
        return float(shares_str.replace('T', '')) * 10**12
    elif 'B' in shares_str:
        return float(shares_str.replace('B', '')) * 10**9
    elif 'M' in shares_str:
        return float(shares_str.replace('M', '')) * 10**6
    elif 'K' in shares_str or 'k' in shares_str:
        return float(shares_str.replace('K', '').replace('k', '')) * 10**3
    try:
        return float(shares_str)  # 如果没有单位标识符，直接返回原始字符串
    except ValueError:
        return 0  # 如果无法转换为浮点数，返回0

# 处理公司名称的函数
def clean_company_name(name):
    # 移除常见的公司后缀
    suffixes = [
        ', Inc.', ' Inc.', ', LLC', ' LLC', ', Ltd.', ' Ltd.', ', Limited', ' Limited', ', Corp.', ' Corp.',
        ', Corporation', ' Corporation', ', Co.', ' Co.', ', Company', ' Company', ' Bros', ' plc', ' Group', ' S.A.',
        ' N.V.', ' Holdings', ' S.A.B.', ' C.V.', ' Ltd', ' Holding', ' Companies', ' PLC', '& plc', ' Incorporated',
        ' AG', ' &', ' SE', '- Petrobras', ' L.P.', ', L.P.', ', LP', 'de C.V.', ' Inc', ', Incorporated',
        ' S.p.A.', ' A/S', ' A.S.', ' p.l.c.', ', S. A. B. de C. V.', ' - COPEL', ' - CEMIG', ' - SABESP', ' - Eletrobrás',
        ' Plc'
    ]
    
    cleaned_name = name
    for suffix in suffixes:
        cleaned_name = cleaned_name.replace(suffix, '')
    
    return cleaned_name.strip()

# 读取JSON文件获取股票符号
def get_stock_symbols_from_json(json_file_path):
    with open(json_file_path, 'r') as file:
        sectors_data = json.load(file)
    
    # 只提取指定分类的股票符号，注意这里的target_sectors需与实际分组对应
    target_sectors = [
        'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
        'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
        'Communication_Services', 'Financial_Services', 'Healthcare'
    ]
    
    stock_symbols = []
    for sector in target_sectors:
        if sector in sectors_data:
            stock_symbols.extend(sectors_data[sector])
    
    return stock_symbols

# 获取已处理的股票符号列表
def get_existing_symbols(file_path):
    existing_symbols = set()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if ':' in line:
                    symbol = line.split(':')[0].strip()
                    existing_symbols.add(symbol)
    return existing_symbols

# 添加鼠标移动功能的函数
def move_mouse_periodically():
    while True:
        try:
            # 获取屏幕尺寸
            screen_width, screen_height = pyautogui.size()
            
            # 随机生成目标位置，避免移动到屏幕边缘
            x = random.randint(100, screen_width - 100)
            y = random.randint(100, screen_height - 100)
            
            # 缓慢移动鼠标到随机位置
            pyautogui.moveTo(x, y, duration=1)
            
            # 等待30-60秒再次移动
            time.sleep(random.randint(30, 60))
            
        except Exception as e:
            print(f"鼠标移动出错: {str(e)}")
            time.sleep(30)

# 优化等待策略的函数
def wait_for_element(driver, by, value, timeout=10):
    """等待元素加载完成并返回"""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except Exception as e:
        return None

def clear_empty_json():
    """清空 Sectors_empty.json 文件中的所有股票符号，但保留分组结构"""
    empty_json_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"
    with open(empty_json_path, 'r') as file:
        data = json.load(file)
    
    # 清空每个分组中的内容，但保留分组
    for group in data:
        data[group] = []
    
    # 写回文件
    with open(empty_json_path, 'w') as file:
        json.dump(data, file, indent=2)
    
    print("已清空 Sectors_empty.json 文件中的所有股票符号")

def get_group_for_symbol(symbol):
    """
    从 Sectors_All.json 中自动匹配symbol所属的分组（忽略大小写）
    """
    base_dir = "/Users/yanzhang/Documents/Financial_System/Modules/"
    sectors_all_path = os.path.join(base_dir, "Sectors_All.json")
    with open(sectors_all_path, 'r') as f:
        data = json.load(f)
    
    for group, symbols in data.items():
        # 将比对双方都转换为大写
        symbols_upper = [s.upper() for s in symbols]
        if symbol in symbols_upper:
            return group
    return None

# —— 1. 新增：从 Sectors_All.json 提取所有分组名 —— #
def extract_group_names():
    """
    读取 Sectors_All.json，将所有顶层 key（即分组名）提取为列表返回
    """
    base_dir = "/Users/yanzhang/Documents/Financial_System/Modules/"
    sectors_all_path = os.path.join(base_dir, "Sectors_All.json")
    with open(sectors_all_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return list(data.keys())

# —— 2. 新增：弹出带下拉框的对话，供用户选择分组 —— #
def show_group_selection_dialog(groups):
    """
    弹出一个小窗口，groups 为字符串列表，用户从下拉列表中选一个分组，返回选择的分组名。
    取消或关闭窗口返回空字符串。
    """
    selected = {'group': ''}

    def on_ok():
        selected['group'] = combo.get().strip()
        root.destroy()

    def on_cancel():
        root.destroy()

    root = tk.Tk()
    root.title("请选择分组")
    root.geometry("300x120")
    root.resizable(False, False)
    # 确保窗口置顶
    root.attributes('-topmost', True)

    tk.Label(root, text="在下拉列表中选择一个分组：").pack(pady=(10, 5))

    combo = ttk.Combobox(root, values=groups, state='readonly')
    combo.pack(pady=5, padx=10, fill='x')
    combo.current(0)

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=(10, 5))
    tk.Button(btn_frame, text="确定", width=10, command=on_ok).pack(side='left', padx=5)
    tk.Button(btn_frame, text="取消", width=10, command=on_cancel).pack(side='left', padx=5)

    root.mainloop()
    return selected['group']

def main():
    # 解析命令行参数
    args = parse_arguments()
    
    # 根据命令行参数选择JSON文件路径和输出目录
    if args.mode.lower() == 'empty':
        empty_json_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"
        
        # 检查empty.json是否有内容
        has_content = check_empty_json_has_content(empty_json_path)
        
        # 根据检查结果决定使用哪种模式
        if has_content:
            # empty.json有内容，使用测试模式
            json_file_path = empty_json_path
            shares_file_path = "/Users/yanzhang/Documents/News/backup/Shares.txt"
            symbol_names_file_path = "/Users/yanzhang/Documents/News/backup/symbol_names.txt"
            marketcap_pe_file_path = "/Users/yanzhang/Documents/News/backup/marketcap_pe.txt"
            print("使用空测试文件模式和backup目录...")
        else:
            # 首先尝试从剪贴板获取内容
            Copy_Command_C()
            clipboard_content = (pyperclip.paste() or "").strip()
            
            if clipboard_content:
                symbol = clipboard_content.upper()
            else:
                # 剪贴板无内容则显示输入对话框
                symbol = show_input_dialog(default_symbol="").strip().upper()
            
            if not symbol:
                print("未输入有效的股票Symbol，程序退出")
                return
            
            group = get_group_for_symbol(symbol)
            if not group:
                show_alert(f"在 Sectors_All.json 中未找到 {symbol} 对应的分组，请手动选择。")
                # 自动匹配失败，弹出下拉列表让用户选
                groups = extract_group_names()
                group = show_group_selection_dialog(groups)
                if not group:
                    show_alert("未选择分组，程序退出")
                    return
            if group:
                add_symbol_to_json_files(symbol, group)
                print(f"已将 {symbol} 自动匹配到 {group} 分组并写入 Sectors_empty.json")
            
            json_file_path = empty_json_path
            shares_file_path = "/Users/yanzhang/Documents/News/backup/Shares.txt"
            symbol_names_file_path = "/Users/yanzhang/Documents/News/backup/symbol_names.txt"
            marketcap_pe_file_path = "/Users/yanzhang/Documents/News/backup/marketcap_pe.txt"
            print("使用空测试文件模式和backup目录...")
    else:
        json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
        shares_file_path = "/Users/yanzhang/Downloads/Shares.txt"
        symbol_names_file_path = "/Users/yanzhang/Downloads/symbol_names.txt"
        marketcap_pe_file_path = "/Users/yanzhang/Downloads/marketcap_pe.txt"
        print("使用正常模式和Downloads目录...")
    
    # 在主程序开始前启动鼠标移动线程
    mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
    mouse_thread.start()

    # 设置Chrome选项
    chrome_options = Options()
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

    # 设置ChromeDriver路径
    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # 设置更短的超时时间
    driver.set_page_load_timeout(20)  # 页面加载超时时间
    driver.set_script_timeout(10)  # 脚本执行超时时间

    # 从JSON文件获取股票符号（只提取指定分组）
    stock_symbols = get_stock_symbols_from_json(json_file_path)

    # 获取已处理的股票符号
    existing_shares = get_existing_symbols(shares_file_path)
    existing_names = get_existing_symbols(symbol_names_file_path)
    existing_marketcap_pe = get_existing_symbols(marketcap_pe_file_path)

    try:
        # 逐个抓取股票数据
        for symbol in stock_symbols:
            # 检查是否所有文件都已包含此symbol，如果是则完全跳过
            if symbol in existing_shares and symbol in existing_names and symbol in existing_marketcap_pe:
                print(f"已在所有文件中抓取过 {symbol}，跳过...")
                show_alert(f"{symbol} 已经在三个文件中都存在了！")
                continue
            
            try:
                url = f"https://finance.yahoo.com/quote/{symbol}/key-statistics/"
                driver.get(url)
                
                # 首先等待公司名称出现，这通常是最快加载的元素之一
                company_name_element = wait_for_element(driver, By.XPATH, "//h1[@class='yf-xxbei9']", timeout=5)
                
                if company_name_element:
                    company_name = company_name_element.text.split('(')[0].strip()
                    cleaned_company_name = clean_company_name(company_name)
                    
                    # 保存公司名称到symbol_names.txt（追加模式），先检查是否已存在
                    if symbol not in existing_names:
                        with open(symbol_names_file_path, 'a', encoding='utf-8') as file:
                            file.write(f"{symbol}: {cleaned_company_name}\n")
                        print(f"已保存 {symbol} 的公司名称: {cleaned_company_name}")
                    else:
                        print(f"{symbol} 的公司名称已存在，跳过写入")
                else:
                    print(f"无法获取 {symbol} 的公司名称")
                    cleaned_company_name = symbol  # 如果无法获取公司名称，使用股票符号作为替代
                
                # 查找Shares Outstanding数据
                shares_outstanding = "N/A"
                shares_outstanding_converted = 0

                # 尝试通过XPath获取
                shares_outstanding_element = wait_for_element(driver, By.XPATH, "//td[contains(text(), 'Shares Outstanding')]/following-sibling::td[1]", timeout=5)
                if shares_outstanding_element and shares_outstanding_element.text:
                    shares_outstanding = shares_outstanding_element.text
                    print(f"通过XPath获取到 {symbol} 的股票数量: {shares_outstanding}")
                else:
                    # 尝试其他XPath
                    alternative_xpaths = [
                        "//span[contains(text(), 'Shares Outstanding')]/../../following-sibling::td",
                        "//th[contains(text(), 'Shares Outstanding')]/following-sibling::td"
                    ]
                    
                    for xpath in alternative_xpaths:
                        alt_element = wait_for_element(driver, By.XPATH, xpath, timeout=3)
                        if alt_element and alt_element.text:
                            shares_outstanding = alt_element.text
                            print(f"通过备选XPath获取到 {symbol} 的股票数量: {shares_outstanding}")
                            break
                    
                    # 如果XPath方法都失败，尝试JavaScript方法
                    if shares_outstanding == "N/A":
                        try:
                            js_result = driver.execute_script("""
                                const elements = document.querySelectorAll('td');
                                for (let i = 0; i < elements.length; i++) {
                                    if (elements[i].textContent.includes('Shares Outstanding')) {
                                        return elements[i].nextElementSibling ? elements[i].nextElementSibling.textContent : 'Not found';
                                    }
                                }
                                return 'Not found';
                            """)
                            
                            if js_result and js_result != 'Not found':
                                shares_outstanding = js_result
                                print(f"通过JavaScript获取到 {symbol} 的股票数量: {shares_outstanding}")
                        except Exception as js_error:
                            print(f"JavaScript获取 {symbol} 的股票数量失败: {str(js_error)}")

                # 转换股票数量格式
                if shares_outstanding != "N/A" and shares_outstanding != '-':
                    shares_outstanding_converted = convert_shares_format(shares_outstanding)
                    if shares_outstanding_converted == 0:
                        print(f"警告: {symbol} 的股票数量转换为0，原始值: {shares_outstanding}")
                else:
                    print(f"无法获取 {symbol} 的股票数量，使用默认值0")
                
                # 查找Price/Book数据
                price_book_element = wait_for_element(driver, By.XPATH, "//td[contains(text(), 'Price/Book')]/following-sibling::td[1]", timeout=3)
                price_book_value = "--"  # 默认为--，表示没有Price/Book值
                if price_book_element:
                    price_book_text = price_book_element.text
                    if price_book_text != 'N/A' and price_book_text != '-':
                        try:
                            price_book_value = float(price_book_text)
                            price_book_value = str(price_book_value)
                        except ValueError:
                            pass
                    print(f"已获取 {symbol} 的Price/Book: {price_book_value}")
                else:
                    print(f"无法获取 {symbol} 的Price/Book")
                
                # 保存股票数量和Price/Book到Shares.txt（追加模式），先检查是否已存在
                if symbol not in existing_shares:
                    with open(shares_file_path, 'a', encoding='utf-8') as file:
                        file.write(f"{symbol}: {int(shares_outstanding_converted)}, {price_book_value}\n")
                    print(f"已保存 {symbol} 的股票数量和Price/Book: {int(shares_outstanding_converted)}, {price_book_value}")
                else:
                    print(f"{symbol} 的股票数量和Price/Book已存在，跳过写入")
                
                # 查找Market Cap数据
                market_cap_element = wait_for_element(driver, By.XPATH, "//td[contains(text(), 'Market Cap')]/following-sibling::td[1]", timeout=3)
                market_cap_converted = 0
                if market_cap_element:
                    market_cap = market_cap_element.text
                    market_cap_converted = convert_shares_format(market_cap)
                
                # 查找Trailing P/E数据
                pe_element = wait_for_element(driver, By.XPATH, "//td[contains(text(), 'Trailing P/E')]/following-sibling::td[1]", timeout=3)
                pe_str = "--"  # 默认为--，表示没有PE值
                if pe_element:
                    pe_ratio_text = pe_element.text
                    if pe_ratio_text != 'N/A' and pe_ratio_text != '-':
                        try:
                            pe_ratio = float(pe_ratio_text)
                            pe_str = str(pe_ratio)
                        except ValueError:
                            pass
                
                # 保存市值和PE到marketcap_pe.txt（追加模式），先检查是否已存在
                if symbol not in existing_marketcap_pe:
                    with open(marketcap_pe_file_path, 'a', encoding='utf-8') as file:
                        file.write(f"{symbol}: {market_cap_converted}, {pe_str}, {price_book_value}\n")
                    print(f"已保存 {symbol} 的市值和PE: {market_cap_converted}, {pe_str}")
                else:
                    print(f"{symbol} 的市值和PE已存在，跳过写入")
                
                print(f"成功处理 {symbol} 的所有数据")
            
            except Exception as e:
                print(f"抓取 {symbol} 时发生错误: {str(e)}")
            
            # 添加短暂延迟，避免请求过于频繁
            time.sleep(1)
    
    finally:
        # 关闭浏览器
        driver.quit()
        
        print("数据抓取完成！")

        # 检查sectors_empty.json是否有内容
        empty_json_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"
        has_content = check_empty_json_has_content(empty_json_path)
        
        # 如果有内容，询问是否清空
        if has_content:
            if args.clear:
                if show_yes_no_dialog("抓取结束，是否清空 Sectors_empty.json 中的股票符号？"):
                    clear_empty_json()
                    
if __name__ == "__main__":
    main()