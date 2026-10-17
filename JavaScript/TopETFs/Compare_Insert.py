import csv
import json
import logging
import platform
import os
import glob
import time
import subprocess
from datetime import date, datetime, timedelta

# 修复：原来没有配置 logging，所有 logging.info 都不会输出
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

# ================= 全局配置区域 (跨平台) =================
USER_HOME = os.path.expanduser("~")

BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOAD_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")

JSON_FILE_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_All.json")
BLACKLIST_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Blacklist.json")
OUTPUT_DIR = NEWS_DIR
OUTPUT_TXT_FILE = os.path.join(OUTPUT_DIR, 'ETFs_new.txt')
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

FILE_PREFIX = "topetf"
WAIT_TIMEOUT_SEC = 300      # 单次拉起后等待文件的时间（需 > 扩展端 AUTO_RESTART_AFTER_MS=3分钟）
RELAUNCH_MAX = 3            # 最多拉起扩展次数
FILE_STABLE_SEC = 1.5       # 文件多少秒内没再变化才认为写完
NEW_ETF_MIN_VOLUME = 200000


# ================= 工具函数 =================
def open_file_externally(file_path):
    """跨平台打开文件"""
    if not os.path.exists(file_path):
        logging.warning(f"文件不存在，无法打开: {file_path}")
        return
    try:
        if platform.system() == 'Darwin':
            subprocess.run(['open', file_path], check=True)
        elif platform.system() == 'Windows':
            os.startfile(file_path)
        else:
            subprocess.run(['xdg-open', file_path], check=True)
        logging.info(f"已成功打开文件: {file_path}")
    except Exception as e:
        logging.error(f"打开文件失败: {e}")


def display_dialog(message):
    """跨平台弹窗提示"""
    if platform.system() == 'Darwin':
        try:
            safe = str(message).replace('\\', '\\\\').replace('"', '\\"')
            applescript_code = f'display dialog "{safe}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception as e:
            logging.error(f"弹窗失败: {e}")
    else:
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("提示", message)
            root.destroy()
        except Exception as e:
            logging.error(f"弹窗失败: {e}")


def extension_launch():
    """拉起 Chrome 扩展 popup（Option+C / Alt+C）"""
    if platform.system() == 'Darwin':
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
        try:
            import pyautogui
            logging.info("请确保 Chrome 浏览器在前台...")
            time.sleep(2)
            pyautogui.hotkey('alt', 'c')
            logging.info("发送 Alt+C 快捷键成功")
        except Exception as e:
            logging.error(f"发送快捷键失败: {e}")


def purge_old_files(prefix=FILE_PREFIX, downloads_path=DOWNLOAD_DIR):
    """
    启动前清掉所有遗留的 prefix_*.csv。
    正常流程处理完会删除文件，残留只可能是上次中途失败留下的旧数据，必须清掉，避免误用。
    """
    for f in glob.glob(os.path.join(downloads_path, f'{prefix}_*.csv')):
        try:
            os.remove(f)
            logging.info(f"🗑️ 删除遗留文件: {os.path.basename(f)}")
        except Exception as e:
            logging.warning(f"删除 {f} 失败: {e}")


def find_ready_file(pattern):
    """返回已写完的最新文件，否则 None"""
    files = glob.glob(pattern)
    if not files:
        return None
    try:
        newest = max(files, key=os.path.getmtime)
        st = os.stat(newest)
    except FileNotFoundError:
        return None
    if st.st_size > 0 and time.time() - st.st_mtime > FILE_STABLE_SEC:
        return newest
    return None


def wait_for_today_file(prefix=FILE_PREFIX, timeout_sec=WAIT_TIMEOUT_SEC,
                        relaunch_max=RELAUNCH_MAX, downloads_path=DOWNLOAD_DIR):
    """
    等待当天的 prefix_YYMMDD*.csv 出现；超时则重新拉起扩展，超过次数返回 None。
    （Chrome 下载中是 .crdownload，完成后才改名为 .csv，所以 glob 不会匹配到半成品）
    """
    today = datetime.now().strftime('%y%m%d')
    pattern = os.path.join(downloads_path, f'{prefix}_{today}*.csv')
    launches = 0
    start = 0.0
    while True:
        if launches == 0 or (time.time() - start) > timeout_sec:
            if launches >= relaunch_max:
                print()
                return None
            launches += 1
            print(f"\n🚀 第 {launches} 次拉起 Chrome 扩展...")
            extension_launch()
            start = time.time()
            print(f"正在等待 {prefix}_{today}*.csv 文件下载", end="", flush=True)

        f = find_ready_file(pattern)
        if f:
            print()
            return f
        time.sleep(2)
        print(".", end="", flush=True)


def load_existing_new_symbols(path):
    """读取 ETFs_new.txt 里已有的 symbol，避免每天重复追加"""
    symbols = set()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if ':' in line:
                        symbols.add(line.split(':', 1)[0].strip())
        except Exception as e:
            logging.warning(f"读取 {path} 失败（不影响后续）: {e}")
    return symbols


def parse_number(s):
    return float(str(s).replace(',', '').strip())


# ================= 主流程 =================
def run_etf_processing():
    logging.info(">>> 开始执行: ETF CSV Processing (Compare_Insert)")

    yesterday_str = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

    # 1. 清理遗留文件 -> 拉起扩展 -> 等待当天文件（带超时重拉）
    purge_old_files()
    topetf_file = wait_for_today_file()
    if not topetf_file:
        msg = f"⚠️ 等待 {FILE_PREFIX} 文件失败，已重试 {RELAUNCH_MAX} 次，退出。"
        logging.error(msg)
        display_dialog(msg)
        return
    logging.info(f"使用 topetf 文件: {topetf_file}")

    # 2. 读取 JSON 配置
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
        known_etfs = set(sectors_data.get('ETFs', []))
        if not known_etfs:
            logging.warning("JSON ETFs 列表为空")
    except Exception as e:
        logging.error(f"读取 JSON 失败: {e}")
        return

    etf_blacklist = set()
    try:
        if os.path.exists(BLACKLIST_JSON_PATH):
            with open(BLACKLIST_JSON_PATH, 'r', encoding='utf-8') as f_bl:
                etf_blacklist = set(json.load(f_bl).get('etf', []))
    except Exception as e:
        logging.warning(f"Blacklist 读取失败，将不使用过滤: {e}")

    # 3. 处理 CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    already_listed = load_existing_new_symbols(OUTPUT_TXT_FILE)
    etfs_to_db = []
    new_etfs_to_file = []
    seen = set()
    total_rows = bad_rows = 0
    try:
        with open(topetf_file, mode='r', encoding='utf-8-sig', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            required = ['Symbol', 'Name', 'Price', 'Volume']
            if not reader.fieldnames or not all(col in reader.fieldnames for col in required):
                logging.error(f"CSV 缺少必要列，实际列: {reader.fieldnames}")
                return
            for row in reader:
                total_rows += 1
                symbol = (row.get('Symbol') or '').strip()
                name = (row.get('Name') or '').strip()
                price_str = row.get('Price')
                volume_str = row.get('Volume')
                if not all([symbol, name, price_str, volume_str]) or symbol in seen:
                    bad_rows += 1
                    continue
                try:
                    price_val = parse_number(price_str)
                    volume_val = int(round(parse_number(volume_str)))
                except ValueError:
                    bad_rows += 1
                    continue
                seen.add(symbol)

                if symbol in known_etfs:
                    etfs_to_db.append((yesterday_str, symbol, round(price_val, 2), volume_val))
                elif (volume_val > NEW_ETF_MIN_VOLUME
                      and symbol not in etf_blacklist
                      and symbol not in already_listed):
                    new_etfs_to_file.append(f"{symbol}: {name}, {volume_val}")
    except Exception as e:
        logging.error(f"处理 CSV 出错: {e}")
        return

    logging.info(f"CSV 共 {total_rows} 行，有效 {len(seen)} 行，跳过 {bad_rows} 行；"
                 f"已知 ETF {len(etfs_to_db)} 个，新 ETF {len(new_etfs_to_file)} 个")

    # 4. 写入数据库（按原配置跳过）
    if etfs_to_db:
        logging.info(f"已准备好 {len(etfs_to_db)} 条 ETF 数据，但根据配置跳过数据库写入。")
        # conn = sqlite3.connect(DB_PATH, timeout=60.0)
        # cursor = conn.cursor()
        # cursor.executemany("INSERT INTO ETFs (date, name, price, volume) VALUES (?, ?, ?, ?)", etfs_to_db)
        # conn.commit(); conn.close()
    else:
        logging.info("无匹配 ETF 数据写入数据库")

    # 5. 写入新 ETF 文件
    if new_etfs_to_file:
        try:
            with open(OUTPUT_TXT_FILE, 'a', encoding='utf-8') as txtfile:
                for line in new_etfs_to_file:
                    txtfile.write(line + '\n')
            logging.info(f"写入 {len(new_etfs_to_file)} 条新 ETF 数据到文件")
        except Exception as e:
            logging.error(f"写入文件失败: {e}")
            return  # 写入失败则保留 CSV，方便排查

    # 6. 删除已处理的 CSV
    try:
        if os.path.exists(topetf_file):
            os.remove(topetf_file)
            logging.info(f"已成功删除临时文件: {topetf_file}")
    except Exception as e:
        logging.error(f"删除文件时发生错误: {e}")

    # 7. 打开结果
    if os.path.exists(OUTPUT_TXT_FILE):
        open_file_externally(OUTPUT_TXT_FILE)
    else:
        display_dialog("所有 ETF 数据已同步，没有发现新的 ETF。")


def main():
    run_etf_processing()


if __name__ == "__main__":
    main()