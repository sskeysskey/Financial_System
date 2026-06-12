import csv
import json
import logging
import platform
from datetime import date, timedelta
import os
import glob
import time
import subprocess
import tkinter as tk
from tkinter import messagebox

# ================= 全局配置区域 (跨平台修改) =================

# 1. 动态获取主目录
USER_HOME = os.path.expanduser("~")

# 2. 定义基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOAD_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")

# 3. 具体业务文件路径
JSON_FILE_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_All.json")
BLACKLIST_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Blacklist.json")
OUTPUT_DIR = NEWS_DIR
OUTPUT_TXT_FILE = os.path.join(OUTPUT_DIR, 'ETFs_new.txt')
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

def open_file_externally(file_path):
    """跨平台打开文件"""
    if not os.path.exists(file_path):
        logging.warning(f"文件不存在，无法打开: {file_path}")
        return

    try:
        if platform.system() == 'Darwin':       # macOS
            subprocess.run(['open', file_path], check=True)
        elif platform.system() == 'Windows':    # Windows
            os.startfile(file_path)
        else:                                   # Linux
            subprocess.run(['xdg-open', file_path], check=True)
        logging.info(f"已成功打开文件: {file_path}")
    except Exception as e:
        logging.error(f"打开文件失败: {e}")

def count_files(prefix):
    """计算Downloads目录中指定前缀开头的文件数量"""
    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{prefix}_*.csv"))
    return len(files)

def run_etf_processing():
    logging.info(">>> 开始执行: ETF CSV Processing (Compare_Insert)")
    
    # 1. 计算昨天日期
    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    
    # 2. 跨平台交互: Mac (AppleScript) / Windows (pyautogui)
    if platform.system() == 'Darwin':
        # Mac 原生逻辑
        script = '''
        delay 1
        tell application "Google Chrome"
            activate
        end tell
        delay 1
        tell application "System Events"
            keystroke "c" using option down
        end tell
        '''
        try:
            subprocess.run(['osascript', '-e', script], check=True)
            logging.info("AppleScript 触发成功")
        except Exception as e:
            logging.error(f"AppleScript 执行失败: {e}")
    else:
        # Windows/Linux 逻辑
        # 假设你已经安装了类似 Tampermonkey 脚本监听快捷键，且快捷键是 Alt+C
        try:
            import pyautogui
            # 尝试切换到 Chrome 窗口 (这一步很难自动化完美，假设用户已经把 Chrome 放在前台)
            logging.info("请确保 Chrome 浏览器在前台...")
            time.sleep(2)
            pyautogui.hotkey('alt', 'c') 
            logging.info("发送 Alt+C 快捷键成功")
        except Exception as e:
            logging.error(f"发送快捷键失败: {e}")

    # 3. 等待文件下载
    print("正在等待 topetf_*.csv 文件下载...", end="")
    waited = 0
    while count_files("topetf") < 1:
        time.sleep(2)
        waited += 2
        print(".", end="", flush=True)
        # 防止死循环，可选设置最大等待时间，例如120秒
        if waited > 120:
             logging.error("\n等待 CSV 文件超时。")
             return
    print("\n文件已找到。")

    # 4. 获取最新文件
    topetf_files = glob.glob(os.path.join(DOWNLOAD_DIR, 'topetf_*.csv'))
    if not topetf_files:
        logging.error("未找到 topetf 文件")
        return
    topetf_file = max(topetf_files, key=os.path.getmtime)
    logging.info(f"使用 topetf 文件: {topetf_file}")

    # 5. 读取 JSON 配置
    known_etfs = set()
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
        known_etfs = set(sectors_data.get('ETFs', []))
        if not known_etfs: logging.warning("JSON ETFs 列表为空")
    except Exception as e:
        logging.error(f"读取 JSON 失败: {e}")
        return 

    etf_blacklist = set()
    try:
        if os.path.exists(BLACKLIST_JSON_PATH):
            with open(BLACKLIST_JSON_PATH, 'r', encoding='utf-8') as f_bl:
                bl_data = json.load(f_bl)
            etf_blacklist = set(bl_data.get('etf', []))
    except Exception as e:
        logging.warning(f"Blacklist 读取失败，将不使用过滤: {e}")

    # 6. 处理 CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    etfs_to_db = []
    new_etfs_to_file = []
    try:
        with open(topetf_file, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            if not reader.fieldnames or not all(col in reader.fieldnames for col in ['Symbol', 'Name', 'Price', 'Volume']):
                logging.error("CSV 缺少必要列")
                return
            for row in reader:
                symbol = row.get('Symbol')
                name = row.get('Name')
                price_str = row.get('Price')
                volume_str = row.get('Volume')
                if not all([symbol, name, price_str, volume_str]): continue
                try:
                    price_val = float(price_str)
                    volume_val = int(volume_str)
                except ValueError: continue
                if symbol in known_etfs:
                    etfs_to_db.append((yesterday_str, symbol, round(price_val, 2), volume_val))
                else:
                    if volume_val > 200000 and symbol not in etf_blacklist:
                        new_etfs_to_file.append(f"{symbol}: {name}, {volume_val}")
    except Exception as e:
        logging.error(f"处理 CSV 出错: {e}")
        return

    # 7. 写入数据库 (修改部分：注释掉数据库插入逻辑)
    if etfs_to_db:
        logging.info(f"已准备好 {len(etfs_to_db)} 条 ETF 数据，但根据配置跳过数据库写入。")
        # conn = None
        # try:
        #     conn = sqlite3.connect(DB_PATH, timeout=60.0)
        #     cursor = conn.cursor()
        #     cursor.executemany("INSERT INTO ETFs (date, name, price, volume) VALUES (?, ?, ?, ?)", etfs_to_db)
        #     conn.commit()
        #     logging.info(f"成功写入 {len(etfs_to_db)} 条 ETF 数据")
        # except Exception as e:
        #     logging.error(f"数据库写入错误: {e}")
        #     if conn: conn.rollback()
        # finally:
        #     if conn: conn.close()
    else:
        logging.info("无匹配 ETF 数据写入数据库")

    # 8. 写入新文件
    if new_etfs_to_file:
        try:
            with open(OUTPUT_TXT_FILE, 'a', encoding='utf-8') as txtfile:
                for line in new_etfs_to_file:
                    txtfile.write(line + '\n')
            logging.info(f"写入 {len(new_etfs_to_file)} 条新 ETF 数据到文件")
        except Exception as e:
            logging.error(f"写入文件失败: {e}")
            return # 如果写入失败，直接返回
        
    # ================= 新增：删除已处理的 CSV 文件 =================
    try:
        if os.path.exists(topetf_file):
            os.remove(topetf_file)
            logging.info(f"已成功删除临时文件: {topetf_file}")
        else:
            logging.warning(f"尝试删除文件失败，文件不存在: {topetf_file}")
    except Exception as e:
        logging.error(f"删除文件时发生错误: {e}")
    # ===========================================================

    # # 9. 调用子脚本 Check_yesterday
    # logging.info("--- 开始执行 Check_yesterday.py ---")
    # try:
    #     # 使用 sys.executable 动态获取 python 路径
    #     result = subprocess.run(
    #         [sys.executable, CHECK_YESTERDAY_SCRIPT_PATH],
    #         check=True, capture_output=True, text=True, encoding='utf-8'
    #     )
    #     logging.info("Check_yesterday 执行成功")
    #     print("--- Subprocess Output ---\n" + result.stdout)
    # except subprocess.CalledProcessError as e:
    #     logging.error(f"Check_yesterday 执行失败 code={e.returncode}")
    #     print(e.stderr)
    # except Exception as e:
    #     logging.error(f"调用 Check_yesterday 失败: {e}")
    
    # 无论刚才是否写入了新数据，现在检查文件是否存在
    if os.path.exists(OUTPUT_TXT_FILE):
        # 如果文件存在（说明有新数据或者之前就有记录），直接打开
        open_file_externally(OUTPUT_TXT_FILE)
    else:
        # 如果文件不存在，说明确实没有新数据
        display_dialog("所有 ETF 数据已同步，没有发现新的 ETF。")

def display_dialog(message):
    """跨平台弹窗提示"""
    if platform.system() == 'Darwin':
        try:
            applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception as e:
            logging.error(f"弹窗失败: {e}")
    else:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("提示", message)
        root.destroy()

def main():
    run_etf_processing()

if __name__ == "__main__":
    main()