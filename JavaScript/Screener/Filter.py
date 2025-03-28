import json
import glob
import os
import time
import sqlite3
import subprocess
from datetime import datetime

# 读取screener数据文件
def read_screener_file(filepath):
    screener_data = {}
    market_caps = {}
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split(', ')
                symbol_part = parts[0].split(': ')
                symbol = symbol_part[0]
                # 提取market cap并转换为浮点数
                market_cap_str = symbol_part[1]
                market_cap = float(market_cap_str)
                sector = parts[-1]
                screener_data.setdefault(sector, []).append(symbol)
                market_caps[symbol] = market_cap
    return screener_data, market_caps

# 读取sectors配置文件
def read_sectors_file(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

# 保存sectors配置文件
def save_sectors_file(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

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

# 比较差异并更新sectors文件
def compare_and_update_sectors(screener_data, sectors_all_data, sectors_today_data, sectors_empty_data, blacklist, db_file):
    differences = {}
    added_symbols = []
    moved_symbols = []  # 新增：记录移动的symbols
    db_delete_logs = []
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
                differences[sector] = {
                    'in_screener_not_in_sectors': filtered_screener_not_in_sectors
                }
                
                # 对每个新symbol检查是否存在于其他sector中
                for symbol in filtered_screener_not_in_sectors:
                    # 检查symbol是否在其他sector中
                    found_in_other_sector = False
                    
                    for other_sector, other_symbols in sectors_all_data.items():
                        if other_sector != sector and symbol in other_symbols:
                            found_in_other_sector = True
                            
                            # 在移动symbol之前，先删除数据库中的记录
                            delete_logs = delete_records_by_names(db_file, other_sector, [symbol])
                            db_delete_logs.extend(delete_logs)
                            
                            # 从原sector中删除
                            sectors_all_data[other_sector].remove(symbol)
                            if other_sector in sectors_today_data and symbol in sectors_today_data[other_sector]:
                                sectors_today_data[other_sector].remove(symbol)
                            moved_symbols.append(f"将symbol '{symbol}' 从 '{other_sector}' 中移除")
                            break
                    
                    # 添加到新的sector
                    sectors_all_data[sector].append(symbol)
                    added_symbols.append(f"将symbol '{symbol}' 添加到 '{sector}' 部门")
                    
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
    
    return differences, sectors_all_data, sectors_today_data, sectors_empty_data, added_symbols, moved_symbols, db_delete_logs

def count_files(prefix):
    """
    计算Downloads目录中指定前缀开头的文件数量
    """
    download_dir = "/Users/yanzhang/Downloads/"
    files = glob.glob(os.path.join(download_dir, f"{prefix}_*.txt"))
    return len(files)

def extension_launch():
    script = '''
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
    for sector, symbols in sectors_5000.items():
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
                        changes_5000.append(f"将{symbol}从5000.json的{other_sector}组中删除")
                        break
                
                # 添加到新sector
                sectors_5000[sector].append(symbol)
                changes_5000.append(f"向5000.json的{sector}组中添加了{symbol}(市值: {market_caps[symbol]})")
            # 移除了在黑名单中的记录
    
    return sectors_5000, changes_5000

# 处理Sectors_500.json，包括移除小于500亿的symbol和添加大于500亿的新symbol
def process_sectors_500(sectors_500, screener_data, market_caps, blacklist):
    changes_500 = []
    
    # 第三步：从500.json中剔除小于500亿的symbol
    for sector, symbols in sectors_500.items():
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
                        changes_500.append(f"将{symbol}从500.json的{other_sector}组删除")
                        break
                
                # 添加到新sector
                sectors_500[sector].append(symbol)
                changes_500.append(f"向500.json的{sector}组中添加了{symbol}(市值: {market_caps[symbol]})")
            # 移除了在黑名单中的记录
    
    return sectors_500, changes_500

# 修改write_log_file函数来包含移动的symbols信息
def write_log_file(output_file, added_symbols, changes_5000, changes_500, moved_symbols, db_delete_logs):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(output_file, 'w') as f:
        f.write(f"=== Sectors_All变更: {timestamp} ===\n\n")
        
        # 写入移动的symbols信息
        if moved_symbols:
            for move in moved_symbols:
                f.write(f"- {move}\n")
        
        # 写入添加到sectors的symbols信息
        if added_symbols:
            for change in added_symbols:
                f.write(f"- {change}\n")
                
        # 写入数据库删除记录
        if db_delete_logs:
            f.write("\n=== 数据库删除记录 ===\n")
            for log in db_delete_logs:
                f.write(f"- {log}\n")
        
        # 写入5000.json变更信息
        f.write("\n=== Sectors_5000.json 变更 ===\n")
        if changes_5000:
            for change in changes_5000:
                f.write(f"- {change}\n")
        else:
            f.write("没有变更\n")
        
        # 写入500.json变更信息
        f.write("\n=== Sectors_500.json 变更 ===\n")
        if changes_500:
            for change in changes_500:
                f.write(f"- {change}\n")
        else:
            f.write("没有变更\n")

def delete_records_by_names(db_file, table_name, stock_names):
    """从数据库中删除记录"""
    delete_log = []
    if not stock_names:
        print("没有提供要删除的股票代码")
        return delete_log
        
    conn = sqlite3.connect(db_file)
    
    try:
        cur = conn.cursor()
        placeholders = ', '.join('?' for _ in stock_names)
        sql = f"DELETE FROM {table_name} WHERE name IN ({placeholders});"
        cur.execute(sql, stock_names)
        conn.commit()
        if cur.rowcount > 0:
            log_msg = f"成功从表 {table_name} 中删除 {stock_names} 的 {cur.rowcount} 条记录"
            print(log_msg)
            delete_log.append(log_msg)
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        conn.close()
        return delete_log

# 主函数
def main():
    extension_launch()
    
    while count_files("screener") < 1:
        time.sleep(2)
        print(".", end="", flush=True)
    
    # 查找Downloads目录下最新的screener_开头的txt文件
    downloads_path = '/Users/yanzhang/Downloads/'
    screener_files = glob.glob(os.path.join(downloads_path, 'screener_*.txt'))
    
    # 按文件修改时间排序，获取最新的文件
    screener_file = max(screener_files, key=os.path.getmtime)
    print(f"使用文件: {screener_file}")
    
    db_file = '/Users/yanzhang/Documents/Database/Finance.db'
    sectors_all_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    sectors_today_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_Today.json'
    sectors_empty_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
    sectors_5000_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_5000.json'
    sectors_500_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_500.json'
    blacklist_file = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'
    
    # 读取数据
    screener_data, market_caps = read_screener_file(screener_file)
    sectors_all_data = read_sectors_file(sectors_all_file)
    sectors_today_data = read_sectors_file(sectors_today_file)
    sectors_empty_data = read_sectors_file(sectors_empty_file)
    sectors_5000_data = read_sectors_file(sectors_5000_file)
    sectors_500_data = read_sectors_file(sectors_500_file)
    blacklist = read_blacklist_file(blacklist_file)
    
    # 比较差异并更新sectors文件
    differences, updated_sectors_all, updated_sectors_today, updated_sectors_empty, added_symbols, moved_symbols, db_delete_logs = compare_and_update_sectors(
        screener_data, sectors_all_data, sectors_today_data, sectors_empty_data, blacklist, db_file
    )
    
    # 保存更新后的sectors文件
    save_sectors_file(sectors_all_file, updated_sectors_all)
    save_sectors_file(sectors_today_file, updated_sectors_today)
    save_sectors_file(sectors_empty_file, updated_sectors_empty)
    
    # 处理Sectors_5000.json
    updated_sectors_5000, changes_5000 = process_sectors_5000(sectors_5000_data, screener_data, market_caps, blacklist)
    save_sectors_file(sectors_5000_file, updated_sectors_5000)
    
    # 处理Sectors_500.json
    updated_sectors_500, changes_500 = process_sectors_500(sectors_500_data, screener_data, market_caps, blacklist)
    save_sectors_file(sectors_500_file, updated_sectors_500)
    
    # 写入汇总日志文件
    output_file = '/Users/yanzhang/Documents/News/screener_sectors.txt'
    write_log_file(output_file, added_symbols, changes_5000, changes_500, moved_symbols, db_delete_logs)

    # 等待1秒
    time.sleep(1)

    # 打开文件
    # 在 macOS 系统下使用 open 命令打开文件
    os.system(f"open {output_file}")

if __name__ == "__main__":
    main()