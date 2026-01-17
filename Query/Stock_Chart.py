import re
import sys
import json
import subprocess
import pyperclip
import platform  # <--- 新增
from functools import lru_cache
import concurrent.futures
import sqlite3
import os
import tkinter as tk
from tkinter import messagebox

from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit

# ================= 配置区域 (跨平台修改) =================

# 1. 动态获取主目录
USER_HOME = os.path.expanduser("~")

# 2. 定义基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_BACKUP_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")

# 3. 具体业务文件路径
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_ALL_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_All.json")
COMPARE_ALL_TXT = os.path.join(NEWS_BACKUP_DIR, "Compare_All.txt")
DESCRIPTION_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "description.json")
SHOW_DESCRIPTION_SCRIPT = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "show_description.py")

# 4. 模块导入路径
QUERY_DIR = os.path.join(FINANCIAL_SYSTEM_DIR, "Query")
if QUERY_DIR not in sys.path:
    sys.path.append(QUERY_DIR)

# 尝试导入，如果还没有文件则打印警告
try:
    from Chart_input import plot_financial_data
except ImportError:
    print(f"Warning: Failed to import 'plot_financial_data' from {QUERY_DIR}")
    # 定义一个空函数防止程序崩溃
    def plot_financial_data(*args, **kwargs):
        print("Mock: plot_financial_data called")

# ========================================================

@lru_cache(maxsize=None)
def lazy_load_data(path, data_type='json'):
    if not os.path.exists(path):
        # 即使文件不存在也返回空字典，防止崩溃
        return {}
    
    with open(path, 'r', encoding='utf-8') as file:
        if data_type == 'json':
            try:
                return json.load(file)
            except json.JSONDecodeError:
                return {}
        else:
            data = {}
            for line in file:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                key, value = map(str.strip, line.split(':', 1))
                data[key] = value
            return data

def display_dialog(message):
    """跨平台弹窗提示"""
    if platform.system() == 'Darwin':
        try:
            applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception:
            pass
    else:
        root = tk.Tk()
        root.withdraw()
        # 置顶窗口
        root.attributes("-topmost", True)
        messagebox.showinfo("提示", message)
        root.destroy()

# 新增: 从SQLite数据库获取市、盈、股、净数据
def fetch_mnspp_data_from_db(db_path, symbol):
    """
    根据股票代码从MNSPP表中查询 shares, marketcap, pe_ratio, pb。
    """
    if not os.path.exists(db_path):
        return "N/A", None, "N/A", "--"
        
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            query = "SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?"
            cursor.execute(query, (symbol,))
            result = cursor.fetchone()
        
        if result:
            # 数据库查到了数据，返回实际值
            shares, marketcap, pe, pb = result
            return shares, marketcap, pe, pb
        else:
            # 数据库没查到，返回默认值
            return "N/A", None, "N/A", "--"
    except sqlite3.Error:
        return "N/A", None, "N/A", "--"

def match_and_plot(input_trimmed, sector_data, compare_data, json_data, db_path):
    """
    修改后的匹配与绘图函数。
    - 不再接收 shares 和 marketcap_pe_data 字典。
    - 在找到匹配项后，直接调用数据库查询函数。
    """
    if not sector_data: # 如果 sector_data 加载失败
        return False

    search_keys = [input_trimmed, input_trimmed.capitalize(), input_trimmed.upper()]
    for input_variant in search_keys:
        for sector, names in sector_data.items():
            if input_variant in names:
                # 找到匹配项，从数据库获取数据
                shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(db_path, input_variant)
                
                plot_financial_data(
                    db_path, sector, input_variant,
                    compare_data.get(input_variant, "N/A"),
                    (shares_val, pb),  # 将 shares 和 pb 组合成元组传入
                    marketcap,
                    pe,
                    json_data, '1Y', True)
                return True

    input_lower = input_trimmed.lower()
    for sector, names in sector_data.items():
        for name in names:
            if re.search(input_lower, name.lower()):
                # 找到匹配项，从数据库获取数据
                shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(db_path, name)
                plot_financial_data(
                    db_path, sector, name,
                    compare_data.get(name, "N/A"),
                    (shares_val, pb), # 将 shares 和 pb 组合成元组传入
                    marketcap,
                    pe,
                    json_data, '10Y', True)
                return True
    return False

def load_data_parallel():
    data_sources = [
        (SECTORS_ALL_JSON, 'json'),
        (COMPARE_ALL_TXT, 'compare'),
        (DESCRIPTION_JSON, 'json')
    ]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_data = {executor.submit(lazy_load_data, path, data_type): (path, data_type) for path, data_type in data_sources}
        results = {}
        for future in concurrent.futures.as_completed(future_to_data):
            path, data_type = future_to_data[future]
            try:
                data = future.result()
                results[path] = data
            except Exception as exc:
                print(f'{path} generated an exception: {exc}')
    
    return results

def input_mapping(data, db_path, user_input):
    """
    修改后的输入映射函数。
    - 统一将用户输入标准化为大写（并 strip）。
    """
    if not user_input:
        print("未输入任何内容，程序即将退出。")
        return
    # 标准化：去空白并转大写
    input_trimmed = user_input.strip().upper()
    
    if match_and_plot(input_trimmed,
                      data.get(SECTORS_ALL_JSON, {}),
                      data.get(COMPARE_ALL_TXT, {}),
                      data.get(DESCRIPTION_JSON, {}),
                      db_path):
        # 任务完成，函数返回后程序将自动退出
        pass
    else:
        # 把没找到的符号拷贝到剪贴板，然后尝试显示 description
        pyperclip.copy(input_trimmed)
        try:
            # 动态路径调用
            subprocess.run([
                sys.executable,
                SHOW_DESCRIPTION_SCRIPT,
                'paste'
            ], check=True)
            # 如果 show_description.py 成功显示了内容，这里就会正常结束
        except subprocess.CalledProcessError:
            # 如果 show_description.py 返回非0状态码，说明也没找到 description
            # 重新调用输入框
            # 在 PyQt 循环中，重新调用输入框需要小心递归深度，但对于 GUI 交互通常问题不大
            new_input = get_user_input_qt("请输入")
            if new_input:  # 如果用户输入了新的内容
                input_mapping(data, db_path, new_input)

# 使用PyQt6重写的用户输入对话框函数
def get_user_input_qt(prompt):
    """
    使用 PyQt6 QInputDialog 显示一个输入对话框。
    """
    # 获取剪贴板内容
    clipboard = QApplication.clipboard()
    clipboard_content = clipboard.text().strip() if clipboard else ""
    
    # 显示输入对话框
    # QInputDialog.getText() 返回一个元组 (text, ok_pressed)
    user_input, ok = QInputDialog.getText(
        None,           # 父窗口 (无)
        prompt,         # 对话框标题
        f"{prompt}:",   # 对话框内的标签文本
        QLineEdit.EchoMode.Normal, # PyQt6: 使用 Scoped Enum
        clipboard_content # 默认填充文本
    )
    
    if ok and user_input:
        return user_input.strip()
    else:
        # 如果用户取消或输入为空，则返回None
        return None

if __name__ == '__main__':
    # 任何PyQt6应用都必须创建一个QApplication实例
    # sys.argv 允许Qt处理命令行参数
    app = QApplication(sys.argv)
    
    data = load_data_parallel()
    db_path = DB_PATH
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "paste":
            # pyperclip.paste() 依然可用，或者使用Qt的剪贴板，去掉两端空白
            clipboard_content = pyperclip.paste().strip().upper()
            # 调用更新后的 input_mapping
            input_mapping(data, db_path, clipboard_content)
        elif arg == "input":
            # 调用新的Qt输入函数
            user_input = get_user_input_qt("请输入")
            # 调用更新后的 input_mapping
            input_mapping(data, db_path, user_input.upper() if user_input else None)
    else:
        print("请提供参数 input 或 paste")
        sys.exit(1)
