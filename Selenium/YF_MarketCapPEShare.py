from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from tqdm import tqdm
import os
import re
import json
import time
import pyperclip
import subprocess
import tkinter as tk
from tkinter import ttk
import argparse
import sqlite3  # 新增：导入sqlite3库

# --- 数据库操作函数 ---
def create_db_connection(db_file):
    """ 创建一个到SQLite数据库的连接 """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        # 让查询结果可以像字典一样通过列名访问
        conn.row_factory = sqlite3.Row
        print("成功连接到数据库。")
    except sqlite3.Error as e:
        print(f"数据库连接错误: {e}")
        show_alert(f"数据库连接错误: {e}")
    return conn

def get_stock_from_db(conn, symbol):
    """ 从MNSPP表中根据symbol查询股票数据 """
    try:
        cur = conn.cursor()
        # 使用 upper() 进行不区分大小写的比较
        cur.execute("SELECT * FROM MNSPP WHERE upper(symbol) = ?", (symbol.upper(),))
        row = cur.fetchone()
        return row  # 返回一个sqlite3.Row对象或None
    except sqlite3.Error as e:
        print(f"从数据库查询 {symbol} 时出错: {e}")
        return None

def should_update_field(db_value, scraped_value_str):
    """
    根据您的更新规则，判断一个字段是否需要更新。
    返回 (是否更新_bool, 转换后的新值_float_or_int)
    """
    # 规则：如果抓取到的是空、0或'--'，则认为无效
    is_scraped_valid = False
    scraped_value = 0
    
    if scraped_value_str not in ('N/A', '-', '--', None):
        try:
            # 尝试将抓取到的值转为浮点数
            val = float(scraped_value_str)
            if val != 0:
                is_scraped_valid = True
                scraped_value = val
        except (ValueError, TypeError):
            is_scraped_valid = False

    # 规则：如果数据库中的值是空或0，则认为无效
    is_db_valid = db_value is not None and float(db_value) != 0

    # 如果抓取到的数据无效，则不更新
    if not is_scraped_valid:
        return False, None

    # 如果抓取到的数据有效，但数据库数据无效，则更新
    if not is_db_valid:
        return True, scraped_value

    # 如果两者都有效，但值不相同（处理浮点数精度问题），则更新
    if abs(float(db_value) - scraped_value) > 1e-9: # 比较浮点数差异
        return True, scraped_value

    # 其他情况（两者都无效，或两者都有效且值相同）不更新
    return False, None

# --- 修改点 1: 移除 update_stock_in_db 中关于 name 的部分 ---
def update_stock_in_db(conn, symbol, scraped_data, db_record):
    """
    根据新抓取的数据更新数据库中的记录。
    scraped_data: 包含新数据的字典。
    db_record: 从数据库查询到的旧数据（sqlite3.Row对象）。
    """
    updates = []
    params = []

    # 移除了对 'name' 字段的检查和更新逻辑

    # 检查 'shares' 字段
    update_shares, new_shares = should_update_field(db_record['shares'], scraped_data['shares'])
    if update_shares:
        updates.append("shares = ?")
        params.append(int(new_shares)) # Shares应该是整数

    # 检查 'marketcap' 字段
    update_marketcap, new_marketcap = should_update_field(db_record['marketcap'], scraped_data['marketcap'])
    if update_marketcap:
        updates.append("marketcap = ?")
        params.append(new_marketcap)

    # 检查 'pe_ratio' 字段
    update_pe, new_pe = should_update_field(db_record['pe_ratio'], scraped_data['pe'])
    if update_pe:
        updates.append("pe_ratio = ?")
        params.append(new_pe)

    # 检查 'pb' 字段
    update_pb, new_pb = should_update_field(db_record['pb'], scraped_data['pb'])
    if update_pb:
        updates.append("pb = ?")
        params.append(new_pb)

    if not updates:
        print(f"数据库中 {symbol} 的数据已是最新，无需更新。")
        return

    try:
        sql = f"UPDATE MNSPP SET {', '.join(updates)} WHERE upper(symbol) = ?"
        params.append(symbol.upper())
        
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        conn.commit()
        print(f"已更新数据库中 {symbol} 的记录: {', '.join(field.split(' ')[0] for field in updates)}")
    except sqlite3.Error as e:
        print(f"更新数据库中 {symbol} 的记录时出错: {e}")

# --- 修改点 2: 移除 insert_stock_into_db 中的 name 参数和相关逻辑 ---
def insert_stock_into_db(conn, symbol, shares, marketcap, pe, pb):
    """ 向MNSPP表中插入一条新的股票记录 (已移除name列) """
    # 修改了SQL语句，去掉了 name 列和对应的占位符
    sql = ''' INSERT INTO MNSPP(symbol, shares, marketcap, pe_ratio, pb)
              VALUES(?,?,?,?,?) '''
    try:
        cur = conn.cursor()
        # 将'--'或无效值转换成数据库的NULL
        pe_to_db = None if pe in ('--', 'N/A', '-') else float(pe)
        pb_to_db = None if pb in ('--', 'N/A', '-') else float(pb)
        
        # 修改了 execute 的参数，移除了 name
        cur.execute(sql, (symbol, int(shares), marketcap, pe_to_db, pb_to_db))
        conn.commit()
        print(f"已将新symbol {symbol} 插入到数据库。")
    except (sqlite3.Error, ValueError) as e:
        print(f"向数据库插入 {symbol} 时出错: {e}")


def resolve_data_path(filename):
    """
    优先返回 ~/Downloads/filename，如果不存在则返回 ~/Documents/News/backup/filename。
    如果两处都不存在，则默认返回 ~/Downloads/filename（后面写文件会自动创建）。
    """
    downloads_dir = os.path.expanduser("~/Downloads")
    backup_dir   = os.path.expanduser("~/Documents/News/backup")
    dl = os.path.join(downloads_dir, filename)
    bu = os.path.join(backup_dir, filename)
    if os.path.exists(dl):
        return dl
    elif os.path.exists(bu):
        return bu
    else:
        # 两处都不存在，默认写到 Downloads
        os.makedirs(downloads_dir, exist_ok=True)
        return dl

def Copy_Command_C():
    script = '''
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
    # 1. 先把 " del …" 或 " de …"（前后都要空格，忽略大小写）及其后面所有内容一起去掉
    #    \s           匹配前面的空格
    #    (?:del|de)   匹配 del 或 de
    #    \s+          至少一个空格
    #    .*           后面所有内容
    name = re.sub(r'\s(?:del|de)\s+.*', '', name, flags=re.IGNORECASE)

    # 移除常见的公司后缀
    suffixes = [
        ', Inc.', ' Inc.', ', LLC', ' LLC', ', Ltd.', ' Ltd.', ', Limited', ' Limited', ', Corp.', ' Corp.',
        ', Corporation', ' Corporation', ', Co.', ' Co.', ', Company', ' Company', ' Bros', ' plc', ' Group', ' S.A.',
        ' N.V.', ' Holdings', ' S.A.B.', ' C.V.', ' Ltd', ' Holding', ' Companies', ' PLC', '& plc', ' Incorporated',
        ' AG', ' &', ' SE', '- Petrobras', ' L.P.', ', L.P.', ', LP', ' LP', 'de C.V.', ' Inc', ', Incorporated',
        ' National Information Services', ' American Pipeline,', ' - SABESP', ' - Eletrobrás', ' Solutions',
        ' S.p.A.', ' A/S', ' A.S.', ' p.l.c.', ', S. A. B. de C. V.', ' - COPEL', ' - CEMIG', ' Equities',
        ' Plc', ',B. de', ' Worldwide', ' International', ' Technologies', ' and', ' Bancorp', ' Bancshares',
        ' Bankshares', ' Services', ' Fund', ' Bancorporation', ' Association', ' Management', ' Entertainment',
        ' Interactive Software', ' Technology', ' SA', ' Partners', ' Innovations', ' Brasileiras', ' Properties',
        ' Enterprise', ' DI', ' Alliance', ' Associates', ' Systems,' ' Systems', ' Kaspi.kz', ' Manufacturing',
        ' Participações', ' Partners,', ' Investment Trust'
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

# ---- 1. 新增：从 Sectors_All.json 提取所有分组名 ---- #
def extract_group_names():
    """
    读取 Sectors_All.json，将所有顶层 key（即分组名）提取为列表返回
    """
    base_dir = "/Users/yanzhang/Documents/Financial_System/Modules/"
    sectors_all_path = os.path.join(base_dir, "Sectors_All.json")
    with open(sectors_all_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return list(data.keys())

# ---- 2. 新增：弹出带下拉框的对话，供用户选择分组 ---- #
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
            shares_file_path        = resolve_data_path("Shares.txt")
            # symbol_names_file_path  = resolve_data_path("symbol_names.txt")
            marketcap_pe_file_path  = resolve_data_path("marketcap_pe.txt")
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
            # symbol_names_file_path = "/Users/yanzhang/Documents/News/backup/symbol_names.txt"
            marketcap_pe_file_path = "/Users/yanzhang/Documents/News/backup/marketcap_pe.txt"
            print("使用空测试文件模式和backup目录...")
    else:
        json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
        shares_file_path = "/Users/yanzhang/Downloads/Shares.txt"
        # symbol_names_file_path = "/Users/yanzhang/Downloads/symbol_names.txt"
        marketcap_pe_file_path = "/Users/yanzhang/Downloads/marketcap_pe.txt"
        print("使用正常模式和Downloads目录...")

    # --- 数据库连接 ---
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    db_conn = create_db_connection(db_path)
    if not db_conn:
        print("无法连接到数据库，程序退出。")
        return

    # 设置Chrome选项
    chrome_options = Options()

    # 无头模式：后台运行
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--window-size=1920,1080')

    # 增强性能
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
    # existing_names = get_existing_symbols(symbol_names_file_path)
    existing_marketcap_pe = get_existing_symbols(marketcap_pe_file_path)

    try:
        # 逐个抓取股票数据
        for symbol in tqdm(stock_symbols,
                       desc="Processing symbols",
                       unit="sym"):
            # 检查是否所有文件都已包含此symbol，如果是则完全跳过
            if symbol in existing_shares and symbol in existing_marketcap_pe:
                # if symbol in existing_shares and symbol in existing_names and symbol in existing_marketcap_pe:
                print(f"已在所有文件中抓取过 {symbol}，跳过...")
                show_alert(f"{symbol} 已经在三个文件中都存在了！")
                continue
            
            try:
                url = f"https://finance.yahoo.com/quote/{symbol}/key-statistics/"
                driver.get(url)
                
                # 查找Shares Outstanding数据
                shares_outstanding = "N/A"
                shares_outstanding_converted = 0
                got_shares = False   # 标记是否真正拿到了 shares
                got_price_book = False  # 标记是否真正拿到了 price/book

                # 尝试通过XPath获取
                shares_outstanding_element = wait_for_element(driver, By.XPATH, "//td[contains(text(), 'Shares Outstanding')]/following-sibling::td[1]", timeout=5)
                # if shares_outstanding_element and shares_outstanding_element.text:
                if shares_outstanding_element and shares_outstanding_element.text not in ("N/A", "-"):
                    shares_outstanding = shares_outstanding_element.text
                    got_shares = True
                    print(f"通过XPath获取到 {symbol} 的股票数量: {shares_outstanding}")
                else:
                    # 尝试其他XPath
                    alternative_xpaths = [
                        "//span[contains(text(), 'Shares Outstanding')]/../../following-sibling::td",
                        "//th[contains(text(), 'Shares Outstanding')]/following-sibling::td"
                    ]
                    
                    for xpath in alternative_xpaths:
                        alt_element = wait_for_element(driver, By.XPATH, xpath, timeout=3)
                        # if alt_element and alt_element.text:
                        if alt_element and alt_element.text not in ("N/A", "-"):
                            shares_outstanding = alt_element.text
                            got_shares = True
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
                                got_shares = True
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
                if price_book_element:
                    text = price_book_element.text.strip()
                    if text in ('N/A', '-', '--'):
                        price_book_value = "--"
                        got_price_book = True   # 把“--”也当成“已经取到”
                    else:
                        try:
                            price_book_value = str(float(text))
                            got_price_book = True
                        except:
                            price_book_value = "--"
                            got_price_book = True
                    print(f"已获取 {symbol} 的Price/Book: {price_book_value}")
                else:
                    print(f"无法获取 {symbol} 的Price/Book")
                
                # 保存股票数量和Price/Book到Shares.txt（追加模式），先检查是否已存在
                if symbol not in existing_shares and (got_shares or got_price_book):
                    with open(shares_file_path, 'a', encoding='utf-8') as file:
                        file.write(f"{symbol}: {int(shares_outstanding_converted)}, {price_book_value}\n")
                    print(f"已保存 {symbol} 的股票数量和Price/Book: {int(shares_outstanding_converted)}, {price_book_value}")
                    existing_shares.add(symbol)
                else:
                    print(f"{symbol} 的股票数量和Price/Book已存在或未抓取到，跳过写入")
                
                # 查找Market Cap数据
                market_cap_element = wait_for_element(driver, By.XPATH, "//td[contains(text(), 'Market Cap')]/following-sibling::td[1]", timeout=3)
                market_cap_converted = 0
                got_marketcap = False
                if market_cap_element:
                    text = market_cap_element.text.strip()
                    if text not in ('N/A', '-'):
                        market_cap_converted = convert_shares_format(text)
                        got_marketcap = True
                
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
                if symbol not in existing_marketcap_pe and got_marketcap:
                    with open(marketcap_pe_file_path, 'a', encoding='utf-8') as file:
                        file.write(f"{symbol}: {market_cap_converted}, {pe_str}, {price_book_value}\n")
                    print(f"已保存 {symbol} 的市值和PE: {market_cap_converted}, {pe_str}")
                    existing_marketcap_pe.add(symbol)
                else:
                    print(f"{symbol} 的市值和PE已在文件中存在或页面未抓取到，跳过写入")
                
                print(f"成功处理 {symbol} 的所有数据")

                # --- 新增：数据库操作逻辑 ---
                print(f"--- 开始处理 {symbol} 的数据库操作 ---")
                db_record = get_stock_from_db(db_conn, symbol)
                
                # --- 修改点 3: 构建 scraped_data 时移除 name ---
                scraped_data = {
                    "shares": shares_outstanding_converted,
                    "marketcap": market_cap_converted,
                    "pe": pe_str,
                    "pb": price_book_value
                }

                if db_record:
                    # 数据库中存在该记录，执行更新逻辑
                    update_stock_in_db(db_conn, symbol, scraped_data, db_record)
                else:
                    # 数据库中不存在，弹窗提示并插入新记录
                    show_alert(f"注意：新Symbol '{symbol}' 在数据库中未找到，将添加新记录。")
                    # --- 修改点 4: 调用 insert_stock_into_db 时移除 name 参数 ---
                    insert_stock_into_db(
                        db_conn, symbol, 
                        scraped_data['shares'], 
                        scraped_data['marketcap'], 
                        scraped_data['pe'], 
                        scraped_data['pb']
                    )
                print(f"--- 完成 {symbol} 的数据库操作 ---")

            except Exception as e:
                print(f"处理 {symbol} 时发生主循环错误: {str(e)}")
            
            # 添加短暂延迟，避免请求过于频繁
            time.sleep(1)
    
    finally:
        # 关闭浏览器
        if 'driver' in locals() and driver:
            driver.quit()
        
        # --- 新增：关闭数据库连接 ---
        if db_conn:
            db_conn.close()
            print("数据库连接已关闭。")

        print("数据抓取完成！")

        # 检查sectors_empty.json是否有内容
        empty_json_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"
        has_content = check_empty_json_has_content(empty_json_path)
        
        # 如果有内容，询问是否清空
        if has_content:
            if args.clear:
                # if show_yes_no_dialog("抓取结束，是否清空 Sectors_empty.json 中的股票符号？"):
                    clear_empty_json()
                    
if __name__ == "__main__":
    main()