import json
import glob
import os
import sys
import time
import random
import pyautogui
import threading
import sqlite3
import subprocess
from datetime import datetime, timedelta

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def insert_screener_records(db_file, screener_data, prices, volumes):
    """
    把 screener 抓到的 price/volume 写入到对应 sector 表，
    date = 昨天(系统时间-1天)。
    如果昨天已有同一只票的记录，则跳过不插入。
    """
    # 计算“昨天”的日期字符串
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    conn = sqlite3.connect(db_file, timeout=60.0)
    cur = conn.cursor()

    # 取出数据库中已有的表名，避免 typo 或 SQL 注入
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    valid_tables = {row[0] for row in cur.fetchall()}

    inserted = 0
    skipped  = 0

    for sector, symbols in screener_data.items():
        if sector not in valid_tables:
            print(f"⚠️ 警告：数据库中不存在表 `{sector}`，已跳过该 sector 的写入")
            continue

        for symbol in symbols:
            price = prices.get(symbol)
            vol   = volumes.get(symbol)
            if price is None or vol is None:
                # 不该发生，保证 read_screener_file 一定把 price/volume 都解析了
                continue

            # 检查昨天同一只票的记录是否已存在
            cur.execute(
                f'SELECT 1 FROM "{sector}" WHERE date=? AND name=? LIMIT 1;',
                (yesterday, symbol)
            )
            if cur.fetchone():
                skipped += 1
                continue

            # 不存在则插入
            cur.execute(
                f'''INSERT INTO "{sector}" (date, name, price, volume)
                    VALUES (?, ?, ?, ?);''',
                (yesterday, symbol, price, vol)
            )
            inserted += 1

    conn.commit()
    conn.close()

    print(f"✅ 插入完成：{inserted} 条新纪录，跳过 {skipped} 条已有记录（日期：{yesterday}）")

# 读取screener数据文件
def read_screener_file(filepath, blacklist):
    screener_data = {}
    market_caps = {}
    prices = {}
    volumes = {}
    screener_blacklist_symbols = set(blacklist.get('screener', [])) # 提前获取黑名单符号集合，提高效率
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line: 
                continue
            parts = line.split(', ')
            # parts 示例: ['MSFT: 3340000000000', 'Technology', '449.26', '17094000']
            # 我们只关心前两项
            sym_cap, sector = parts[0], parts[1]
            
            # 提取 symbol
            try:
                symbol, cap_str = sym_cap.split(': ')
            except ValueError:
                print(f"⚠️ 警告：无法解析行 '{line}' 中的 symbol 和 market cap，已跳过。")
                continue

            # 在这里检查 symbol 是否在黑名单的 screener 分组中
            if symbol in screener_blacklist_symbols:
                # print(f"ℹ️ Symbol '{symbol}' 在黑名单的 screener 分组中，已从文件 '{filepath}' 的读取中跳过。") # 可选的日志输出
                continue # 如果在黑名单中，则跳过当前行的后续处理

            try:
                market_cap = float(cap_str)
                price = float(parts[2])
                vol = int(round(float(parts[3])))
            except (ValueError, IndexError) as e:
                print(f"⚠️ 警告：解析行 '{line}' 的数值数据失败 (symbol: {symbol}) - {e}，已跳过。")
                continue
            
            # 如果你以后需要 price/volume，可以这样解析：
            screener_data.setdefault(sector, []).append(symbol)
            market_caps[symbol] = market_cap
            prices[symbol] = price
            volumes[symbol] = vol
    return screener_data, market_caps, prices, volumes

# 读取sectors配置文件
def read_sectors_file(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

# 比较两个字典是否相同
def is_dict_changed(old_dict, new_dict):
    """比较两个字典是否有实质变化"""
    if set(old_dict.keys()) != set(new_dict.keys()):
        return True
    
    for key in old_dict:
        if sorted(old_dict[key]) != sorted(new_dict[key]):
            return True
    
    return False

# 修改保存sectors配置文件函数
def save_sectors_file(filepath, new_data, old_data=None):
    """只有当数据真正变化时才保存文件"""
    # 如果没有提供旧数据，则从文件中读取
    if old_data is None:
        try:
            with open(filepath, 'r') as f:
                old_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            old_data = {}
    
    # 检查数据是否真的变化了
    if not is_dict_changed(old_data, new_data):
        print(f"文件 {filepath} 没有变化，跳过保存")
        return False
    
    # 如果有变化，则保存文件
    with open(filepath, 'w') as f:
        json.dump(new_data, f, indent=4)
    print(f"文件 {filepath} 有变化，已保存")
    return True

# 读取黑名单文件
def read_blacklist_file(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

# 检查symbol是否在黑名单中
def is_in_blacklist(symbol, blacklist):
    screener_blacklist = blacklist.get('screener', [])
    return symbol in screener_blacklist

# 过滤黑名单中的screener符号
def filter_screener_symbols(symbols, blacklist):
    screener_symbols = set(blacklist.get('screener', []))
    return [symbol for symbol in symbols if symbol not in screener_symbols]


# 【新增】函数：用于将股票数据从一个数据库表移动到另一个表
def move_stock_data_in_db(db_file, source_sector, dest_sector, symbol):
    """
    将单个股票的所有历史数据从一个 sector 表移动到另一个 sector 表。
    这是一个事务性操作，确保数据要么完全移动，要么在出错时保持原样。
    """
    log_message = ""
    conn = sqlite3.connect(db_file, timeout=60.0)
    try:
        cur = conn.cursor()

        # 1. 从源表中查询该股票的所有记录
        cur.execute(f'SELECT date, name, price, volume FROM "{source_sector}" WHERE name = ?', (symbol,))
        records_to_move = cur.fetchall()

        if not records_to_move:
            log_message = f"信息：在源表 '{source_sector}' 中没有找到 '{symbol}' 的数据，无需移动。"
            print(log_message)
            return log_message

        # 2. 将查询到的记录批量插入到目标表
        # 注意：这里假设目标表已存在。您的代码逻辑似乎能保证这一点。
        cur.executemany(
            f'INSERT INTO "{dest_sector}" (date, name, price, volume) VALUES (?, ?, ?, ?)',
            records_to_move
        )

        # 3. 从源表中删除该股票的所有记录
        cur.execute(f'DELETE FROM "{source_sector}" WHERE name = ?', (symbol,))

        # 4. 提交事务
        conn.commit()
        
        log_message = f"成功将 symbol '{symbol}' 的 {len(records_to_move)} 条历史记录从表 '{source_sector}' 移动到 '{dest_sector}'"
        print(f"✅ {log_message}")

    except sqlite3.Error as e:
        # 如果发生任何数据库错误，回滚所有更改
        conn.rollback()
        log_message = f"❌ 移动 symbol '{symbol}' 从 '{source_sector}' 到 '{dest_sector}' 失败: {e}"
        print(log_message)
    finally:
        conn.close()
    
    return log_message

# 【修改】比较差异并更新sectors文件的函数
def compare_and_update_sectors(screener_data, sectors_all_data, sectors_today_data, sectors_empty_data, blacklist, db_file):
    added_symbols = []
    moved_symbols = []
    db_operation_logs = [] # 日志名修改为更通用的名字
    has_changes = False
    
    # 遍历screener数据中的每个部门
    for sector, symbols in screener_data.items():
        if sector in sectors_all_data:
            # 在screener中有，但在sectors_all中没有的symbols
            in_screener_not_in_sectors = set(symbols) - set(sectors_all_data[sector])
            
            # 过滤掉黑名单中的screener符号
            filtered_screener_not_in_sectors = filter_screener_symbols(in_screener_not_in_sectors, blacklist)
            
            if filtered_screener_not_in_sectors:
                has_changes = True
                
                # 对每个新symbol检查是否存在于其他sector中
                for symbol in filtered_screener_not_in_sectors:
                    moved = False
                    # 检查symbol是否在其他sector中
                    for other_sector, other_symbols in sectors_all_data.items():
                        if other_sector != sector and symbol in other_symbols:
                            # 【修改】核心逻辑：调用移动函数，而不是删除函数
                            # 将数据库中的记录从旧表移动到新表
                            move_log = move_stock_data_in_db(db_file, other_sector, sector, symbol)
                            if move_log:
                                db_operation_logs.append(move_log)
                            
                            # 从原sector的JSON数据中删除
                            sectors_all_data[other_sector].remove(symbol)
                            if other_sector in sectors_today_data and symbol in sectors_today_data[other_sector]:
                                sectors_today_data[other_sector].remove(symbol)
                            
                            moved_symbols.append(f"将 symbol '{symbol}' 从 '{other_sector}' 移动到 '{sector}'")
                            moved = True
                            break
                    
                    # 添加到新的sector
                    sectors_all_data[sector].append(symbol)
                    
                    # 如果不是移动过来的，而是全新的，则添加到 added_symbols 列表
                    if not moved:
                        added_symbols.append(f"将 '{symbol}' 添加到 '{sector}'，先使用Ctrl+Option+9抓取marketcapshare，再到Yahoo页面使用Ctrl+Comamnd+9抓取历史数据。然后使用Ctrl+Option+1和Ctrl+V抓取description，最后使用Ctrl+option+U抓取财报数据。")
                    
                    # 确保sectors_today_data中有该sector
                    if sector not in sectors_today_data:
                        sectors_today_data[sector] = []
                    
                    # 将symbol添加到sectors_today_data中
                    sectors_today_data[sector].append(symbol)

                    # 确保sectors_empty_data中有该sector
                    if sector not in sectors_empty_data:
                        sectors_empty_data[sector] = []
                    
                    # 将symbol添加到sectors_empty_data中（如果不存在）
                    if symbol not in sectors_empty_data[sector]:
                        sectors_empty_data[sector].append(symbol)
    
    if not has_changes:
        added_symbols.append("Sectors_All文件没有需要更新的内容")
    
    return sectors_all_data, sectors_today_data, sectors_empty_data, added_symbols, moved_symbols, db_operation_logs


def count_files(prefix):
    """
    计算Downloads目录中指定前缀开头的文件数量
    """
    download_dir = "/Users/yanzhang/Downloads/"
    files = glob.glob(os.path.join(download_dir, f"{prefix}_*.txt"))
    return len(files)

def extension_launch():
    script = '''
    delay 1
    tell application "Google Chrome"
	    activate
    end tell
    delay 1
    tell application "System Events"
        keystroke "d" using option down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

# 处理Sectors_5000.json，包括移除小于5000亿的symbol和添加大于5000亿的新symbol
def process_sectors_5000(sectors_5000, screener_data, market_caps, blacklist):
    changes_5000 = []
    
    # 第一步：从5000.json中剔除小于5000亿的symbol
    for sector, symbols in list(sectors_5000.items()): # 使用 list() 避免在迭代时修改字典
        to_remove = []
        for symbol in symbols:
            if symbol in market_caps and market_caps[symbol] < 500000000000:  # 5000亿
                to_remove.append(symbol)
                changes_5000.append(f"从5000.json的{sector}组中剔除了{symbol}(市值: {market_caps[symbol]})")
        
        # 从当前部门移除符号
        for symbol in to_remove:
            sectors_5000[sector].remove(symbol)
    
    # 第二步：添加市值大于5000亿但5000.json中没有的symbol，且不在黑名单中
    for sector, symbols in screener_data.items():
        if sector not in sectors_5000:
            sectors_5000[sector] = []
        
        for symbol in symbols:
            if (symbol in market_caps and 
                market_caps[symbol] >= 500000000000 and 
                symbol not in sectors_5000[sector] and
                not is_in_blacklist(symbol, blacklist)):
                
                # 新增：检查symbol是否在其他sector中存在
                for other_sector in sectors_5000:
                    if other_sector != sector and symbol in sectors_5000[other_sector]:
                        sectors_5000[other_sector].remove(symbol)
                        changes_5000.append(f"从5000.json的{other_sector}组中剔除了{symbol} (因板块变更)")
                        break
                
                # 添加到新sector
                sectors_5000[sector].append(symbol)
                changes_5000.append(f"向5000.json的{sector}组中添加了{symbol}(市值: {market_caps[symbol]})")
    
    return sectors_5000, changes_5000

# 处理Sectors_500.json，包括移除小于500亿的symbol和添加大于500亿的新symbol
def process_sectors_500(sectors_500, screener_data, market_caps, blacklist):
    changes_500 = []
    
    # 第三步：从500.json中剔除小于500亿的symbol
    for sector, symbols in list(sectors_500.items()): # 使用 list() 避免在迭代时修改字典
        to_remove = []
        for symbol in symbols:
            if symbol in market_caps and market_caps[symbol] < 50000000000:  # 500亿
                to_remove.append(symbol)
                changes_500.append(f"从500.json的{sector}组中剔除了{symbol}(市值: {market_caps[symbol]})")
        
        # 从当前部门移除符号
        for symbol in to_remove:
            sectors_500[sector].remove(symbol)
    
    # 第四步：添加市值大于500亿但500.json中没有的symbol，且不在黑名单中
    for sector, symbols in screener_data.items():
        if sector not in sectors_500:
            sectors_500[sector] = []
        
        for symbol in symbols:
            if (symbol in market_caps and 
                market_caps[symbol] >= 50000000000 and 
                symbol not in sectors_500[sector] and
                not is_in_blacklist(symbol, blacklist)):
                
                # 新增：检查symbol是否在其他sector中存在
                for other_sector in sectors_500:
                    if other_sector != sector and symbol in sectors_500[other_sector]:
                        sectors_500[other_sector].remove(symbol)
                        changes_500.append(f"从500.json的{other_sector}组中剔除了{symbol} (因板块变更)")
                        break
                
                # 添加到新sector
                sectors_500[sector].append(symbol)
                changes_500.append(f"向500.json的{sector}组中添加了{symbol}(市值: {market_caps[symbol]})")
    
    return sectors_500, changes_500

# 【修改】write_log_file函数来包含移动的symbols信息
def write_log_file(output_file, added_symbols, changes_5000, changes_500, moved_symbols, db_operation_logs):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(output_file, 'w') as f:
        f.write(f"=== Sectors_All 变更日志: {timestamp} ===\n\n")
        
        # 写入移动的symbols信息（JSON文件层面）
        if moved_symbols:
            f.write("--- 板块移动的 Symbols ---\n")
            for move in moved_symbols:
                f.write(f"- {move}\n")
            f.write("\n")

        # 写入新添加的symbols信息
        if added_symbols:
            f.write("--- 新增的 Symbols ---\n")
            for change in added_symbols:
                f.write(f"- {change}\n")
            f.write("\n")
                
        # 写入数据库操作记录
        if db_operation_logs:
            f.write("--- 数据库操作记录 ---\n")
            for log in db_operation_logs:
                f.write(f"- {log}\n")
            f.write("\n")
        
        # 处理5000.json变更信息
        f.write("=== Sectors_5000.json 变更 ===\n")
        if changes_5000:
            # 分离剔除和添加的记录
            removals_5000 = [change for change in changes_5000 if "剔除" in change]
            additions_5000 = [change for change in changes_5000 if "添加" in change]
            
            if removals_5000:
                f.write("\n剔除记录：\n")
                for removal in removals_5000:
                    f.write(f"- {removal}\n")
            
            if additions_5000:
                f.write("\n添加记录：\n")
                for addition in additions_5000:
                    f.write(f"- {addition}\n")
        else:
            f.write("没有变更\n")
        
        # 处理500.json变更信息
        f.write("\n=== Sectors_500.json 变更 ===\n")
        if changes_500:
            # 分离剔除和添加的记录
            removals_500 = [change for change in changes_500 if "剔除" in change]
            additions_500 = [change for change in changes_500 if "添加" in change]
            
            if removals_500:
                f.write("\n剔除记录：\n")
                for removal in removals_500:
                    f.write(f"- {removal}\n")
            
            if additions_500:
                f.write("\n添加记录：\n")
                for addition in additions_500:
                    f.write(f"- {addition}\n")
        else:
            f.write("没有变更\n")

def clean_old_backups(directory, file_patterns, days=4):
    """
    删除超过指定天数的旧备份文件
    """
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    for filename in os.listdir(directory):
        for prefix, date_position in file_patterns:
            if filename.startswith(prefix):
                try:
                    date_str = filename.split('_')[date_position].split('.')[0]
                    file_date = datetime.strptime(date_str, '%y%m%d').replace(year=now.year)
                    if file_date < cutoff:
                        file_path = os.path.join(directory, filename)
                        os.remove(file_path)
                        print(f"删除旧备份文件：{file_path}")
                    break
                except Exception as e:
                    print(f"跳过文件：{filename}，原因：{e}")

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

def main():
    # —— 新增：在周日（6）和周一（0）不运行 —— 
    today_weekday = datetime.now().weekday()  # Monday=0, …, Sunday=6
    if today_weekday in (6, 0):
        day_name = '周日' if today_weekday == 6 else '周一'
        show_alert(f"⚠️ 当前是{day_name}，程序不运行，退出。")
        sys.exit(0)
    # —— 新增结束 —— 

    threading.Thread(target=move_mouse_periodically, daemon=True).start()
    
    extension_launch()

    # ---- 原有等待 screener_above_*.txt 的逻辑，直到文件出现 ---- 
    while count_files("screener_above") < 1:
        time.sleep(2)
        print(".", end="", flush=True)
    print() # 换行
    
    # # 查找Downloads目录下最新的screener_above_开头的txt文件
    downloads_path = '/Users/yanzhang/Downloads/'
    screener_files = glob.glob(os.path.join(downloads_path, 'screener_above_*.txt'))
    
    # # 按文件修改时间排序，获取最新的文件
    screener_file = max(screener_files, key=os.path.getmtime)
    print(f"使用 above 文件: {screener_file}")

    # ---- 你原来的变量初始化 ---- 
    db_file = '/Users/yanzhang/Coding/Database/Finance.db'
    sectors_all_file = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
    sectors_today_file = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_Today.json'
    sectors_empty_file = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json'
    sectors_5000_file = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_5000.json'
    sectors_500_file = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_500.json'
    blacklist_file = '/Users/yanzhang/Coding/Financial_System/Modules/Blacklist.json'
    backup_directory = '/Users/yanzhang/Coding/News/backup/site'
    
    # 读取数据
    blacklist = read_blacklist_file(blacklist_file)
    screener_data, market_caps, prices, volumes = read_screener_file(screener_file, blacklist)
    sectors_all_data = read_sectors_file(sectors_all_file)
    sectors_today_data = read_sectors_file(sectors_today_file)
    sectors_empty_data = read_sectors_file(sectors_empty_file)
    sectors_5000_data = read_sectors_file(sectors_5000_file)
    sectors_500_data = read_sectors_file(sectors_500_file)
    
    # 比较差异并更新sectors文件
    updated_sectors_all, updated_sectors_today, updated_sectors_empty, added_symbols, moved_symbols, db_operation_logs = compare_and_update_sectors(
        screener_data, sectors_all_data, sectors_today_data, sectors_empty_data, blacklist, db_file
    )
    
    # ---- 把“昨天”价格、成交量写到对应 sector 表 ---- 
    insert_screener_records(db_file, screener_data, prices, volumes)
    
    # 保存更新后的sectors文件，只有在有变化时才保存
    save_sectors_file(sectors_all_file, updated_sectors_all)
    save_sectors_file(sectors_today_file, updated_sectors_today)
    save_sectors_file(sectors_empty_file, updated_sectors_empty)
    
    # 处理Sectors_5000.json
    updated_sectors_5000, changes_5000 = process_sectors_5000(sectors_5000_data, screener_data, market_caps, blacklist)
    save_sectors_file(sectors_5000_file, updated_sectors_5000)
    
    # 处理Sectors_500.json
    updated_sectors_500, changes_500 = process_sectors_500(sectors_500_data, screener_data, market_caps, blacklist)
    save_sectors_file(sectors_500_file, updated_sectors_500)
    
    # ---- 新增：处理 screener_below ---- 
    below_files = glob.glob(os.path.join(downloads_path, 'screener_below_*.txt'))
    if below_files:
        screener_below_file = max(below_files, key=os.path.getmtime)
        print(f"使用 below 文件: {screener_below_file}")
        below_data, _, below_prices, below_volumes = read_screener_file(screener_below_file, blacklist)

        # 只保留那些 sector 在 sectors_all_data 中存在，且 symbol 已经在对应列表中
        valid_below_data = {}
        for sector, symbols in below_data.items():
            if sector not in sectors_all_data:
                continue
            # 进一步过滤：symbol 必须已经在 sectors_all_data[sector] 里
            matched = [s for s in symbols if s in updated_sectors_all[sector]] # 使用更新后的 all data
            if matched:
                valid_below_data[sector] = matched

        if valid_below_data:
            insert_screener_records(db_file, valid_below_data, below_prices, below_volumes)
        else:
            print("⚠️ screener_below 中没有匹配到 sectors_all.json 里已有的 symbol，跳过写入")
    
    # 写入汇总日志文件
    output_file = '/Users/yanzhang/Coding/News/screener_sectors.txt'
    write_log_file(output_file, added_symbols, changes_5000, changes_500, moved_symbols, db_operation_logs)

    # 等待2秒
    time.sleep(2)

    # 在 macOS 系统下使用 open 命令打开文件
    os.system(f"open {output_file}")

    file_patterns = [
        ("NewLow_", -1),
        ("NewLow500_", -1),
        ("NewLow5000_", -1)
    ]
    clean_old_backups(backup_directory, file_patterns)

if __name__ == "__main__":
    main()