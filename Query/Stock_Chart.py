import re
import sys
import json
import subprocess
import pyperclip
from functools import lru_cache
import concurrent.futures
import sqlite3
from PyQt5.QtWidgets import QApplication, QInputDialog, QLineEdit

sys.path.append('/Users/yanzhang/Coding/Financial_System/Query')
from Chart_input import plot_financial_data

@lru_cache(maxsize=None)
def lazy_load_data(path, data_type='json'):
    with open(path, 'r', encoding='utf-8') as file:
        if data_type == 'json':
            return json.load(file)
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
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)

# 新增: 从SQLite数据库获取市、盈、股、净数据
def fetch_mnspp_data_from_db(db_path, symbol):
    """
    根据股票代码从MNSPP表中查询 shares, marketcap, pe_ratio, pb。
    """
    with sqlite3.connect(db_path) as conn:
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

def match_and_plot(input_trimmed, sector_data, compare_data, json_data, db_path):
    """
    修改后的匹配与绘图函数。
    - 不再接收 shares 和 marketcap_pe_data 字典。
    - 在找到匹配项后，直接调用数据库查询函数。
    """
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
                    json_data, '10Y', True)
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
        ('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'json'),
        ('/Users/yanzhang/Coding/News/backup/Compare_All.txt', 'compare'),
        ('/Users/yanzhang/Coding/Financial_System/Modules/description.json', 'json')
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
    - 不再需要 root 参数，也不再调用 close_app。
    """
    if not user_input:
        print("未输入任何内容，程序即将退出。")
        return

    input_trimmed = user_input.strip()
    if match_and_plot(input_trimmed, data['/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'],
                      data['/Users/yanzhang/Coding/News/backup/Compare_All.txt'],
                      data['/Users/yanzhang/Coding/Financial_System/Modules/description.json'],
                      db_path):
        # 任务完成，函数返回后程序将自动退出
        pass
    else:
        # 把没找到的符号拷贝到剪贴板，然后用 show_description.py 的 paste 模式来弹 description 界面
        pyperclip.copy(input_trimmed)
        subprocess.run([
            sys.executable,
            '/Users/yanzhang/Coding/Financial_System/Query/show_description.py',
            'paste'
        ], check=True)

# 使用PyQt5重写的用户输入对话框函数
def get_user_input_qt(prompt):
    """
    使用 PyQt5 QInputDialog 显示一个输入对话框。
    - 自动从剪贴板获取内容并填充输入框。
    - QInputDialog 默认就会选中预填充的文本。
    - 窗口会根据操作系统风格自动居中。
    - 如果用户点击 "OK"，返回输入的文本；如果点击 "Cancel" 或关闭窗口，返回 None。
    """
    # 获取剪贴板内容
    clipboard_content = QApplication.clipboard().text()

    # 显示输入对话框
    # QInputDialog.getText() 返回一个元组 (text, ok_pressed)
    user_input, ok = QInputDialog.getText(
        None,           # 父窗口 (无)
        prompt,         # 对话框标题
        f"{prompt}:",   # 对话框内的标签文本
        QLineEdit.Normal, # 输入模式 (正常文本)
        clipboard_content # 默认填充文本
    )

    if ok and user_input:
        return user_input
    else:
        # 如果用户取消或输入为空，则返回None
        return None

if __name__ == '__main__':
    # 任何PyQt5应用都必须创建一个QApplication实例
    # sys.argv 允许Qt处理命令行参数
    app = QApplication(sys.argv)

    data = load_data_parallel()
    db_path = '/Users/yanzhang/Coding/Database/Finance.db'

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "paste":
            # pyperclip.paste() 依然可用，或者使用Qt的剪贴板
            clipboard_content = pyperclip.paste()
            # 调用更新后的 input_mapping
            input_mapping(data, db_path, clipboard_content)
        elif arg == "input":
            # 调用新的Qt输入函数
            user_input = get_user_input_qt("请输入")
            # 调用更新后的 input_mapping
            input_mapping(data, db_path, user_input)
    else:
        print("请提供参数 input 或 paste")
        sys.exit(1)