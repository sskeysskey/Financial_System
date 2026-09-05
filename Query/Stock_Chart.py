import re
import sys
import json
import subprocess
import pyperclip
import platform
from functools import lru_cache
import concurrent.futures
import sqlite3
import os
import tkinter as tk
from tkinter import messagebox

from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_BACKUP_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")

DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_ALL_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_All.json")
COMPARE_ALL_TXT = os.path.join(NEWS_BACKUP_DIR, "Compare_All.txt")
DESCRIPTION_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "description.json")
SHOW_DESCRIPTION_SCRIPT = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "show_description.py")

QUERY_DIR = os.path.join(FINANCIAL_SYSTEM_DIR, "Query")
if QUERY_DIR not in sys.path:
    sys.path.append(QUERY_DIR)

try:
    from Chart_input import plot_financial_data
except ImportError:
    def plot_financial_data(*args, **kwargs):
        print("Mock: plot_financial_data called")

@lru_cache(maxsize=None)
def lazy_load_data(path, data_type='json'):
    if not os.path.exists(path):
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
    if platform.system() == 'Darwin':
        try:
            applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception:
            pass
    else:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo("提示", message)
        root.destroy()

def fetch_mnspp_data_from_db(db_path, symbol):
    if not os.path.exists(db_path):
        return "N/A", None, "N/A", "--"
        
    try:
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            # 兼容点号与中划线双向查找
            alt_sym = symbol.replace('.', '-') if '.' in symbol else symbol.replace('-', '.')
            query = "SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ? OR symbol = ? LIMIT 1"
            cursor.execute(query, (symbol, alt_sym))
            result = cursor.fetchone()
        
        if result:
            shares, marketcap, pe, pb = result
            return shares, marketcap, pe, pb
        else:
            return "N/A", None, "N/A", "--"
    except sqlite3.Error:
        return "N/A", None, "N/A", "--"

def match_and_plot(input_trimmed, sector_data, compare_data, json_data, db_path):
    if not sector_data:
        return False

    # 生成候选检索词（兼容 BRK.B 和 BRK-B）
    alt_variant = input_trimmed.replace('.', '-') if '.' in input_trimmed else input_trimmed.replace('-', '.')
    search_keys = [
        input_trimmed, input_trimmed.capitalize(), input_trimmed.upper(),
        alt_variant, alt_variant.capitalize(), alt_variant.upper()
    ]

    for input_variant in search_keys:
        for sector, names in sector_data.items():
            if input_variant in names:
                shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(db_path, input_variant)
                plot_financial_data(
                    db_path, sector, input_variant,
                    compare_data.get(input_variant, "N/A"),
                    (shares_val, pb),
                    marketcap,
                    pe,
                    json_data, '1Y', True, display_name=input_trimmed)
                return True

    input_lower = input_trimmed.lower()
    for sector, names in sector_data.items():
        for name in names:
            if re.search(r'\b' + re.escape(input_lower) + r'\b', name.lower()) or (alt_variant and re.search(r'\b' + re.escape(alt_variant.lower()) + r'\b', name.lower())):
                shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(db_path, name)
                plot_financial_data(
                    db_path, sector, name,
                    compare_data.get(name, "N/A"),
                    (shares_val, pb),
                    marketcap,
                    pe,
                    json_data, '10Y', True, display_name=input_trimmed)
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
    if not user_input:
        return
    input_trimmed = user_input.strip().upper()
    
    if match_and_plot(input_trimmed,
                      data.get(SECTORS_ALL_JSON, {}),
                      data.get(COMPARE_ALL_TXT, {}),
                      data.get(DESCRIPTION_JSON, {}),
                      db_path):
        pass
    else:
        pyperclip.copy(input_trimmed)
        try:
            subprocess.run([
                sys.executable,
                SHOW_DESCRIPTION_SCRIPT,
                'paste'
            ], check=True)
        except subprocess.CalledProcessError:
            new_input = get_user_input_qt("请输入")
            if new_input:
                input_mapping(data, db_path, new_input)

def get_user_input_qt(prompt):
    clipboard = QApplication.clipboard()
    clipboard_content = clipboard.text().strip() if clipboard else ""
    user_input, ok = QInputDialog.getText(
        None, prompt, f"{prompt}:",
        QLineEdit.EchoMode.Normal,
        clipboard_content
    )
    if ok and user_input:
        return user_input.strip()
    return None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    data = load_data_parallel()
    db_path = DB_PATH
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg == "paste":
            clipboard_content = pyperclip.paste().strip().upper()
            input_mapping(data, db_path, clipboard_content)
        elif arg == "input":
            user_input = get_user_input_qt("请输入")
            input_mapping(data, db_path, user_input.upper() if user_input else None)
        else:
            input_mapping(data, db_path, arg.upper())
    else:
        sys.exit(1)