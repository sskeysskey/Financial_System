import json
import glob
import os
import time
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

# 比较差异
def compare_differences(screener_data, sectors_data, blacklist):
    differences = {}
    
    # 遍历screener数据中的每个部门
    for sector, symbols in screener_data.items():
        if sector in sectors_data:
            # 在screener中有，但在sectors_all中没有的symbols
            in_screener_not_in_sectors = set(symbols) - set(sectors_data[sector])
            
            # 过滤掉黑名单中的screener符号
            filtered_screener_not_in_sectors = filter_screener_symbols(in_screener_not_in_sectors, blacklist)
            
            if filtered_screener_not_in_sectors:
                differences[sector] = {
                    'in_screener_not_in_sectors': filtered_screener_not_in_sectors
                }
    
    return differences

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
                sectors_500[sector].append(symbol)
                changes_500.append(f"向500.json的{sector}组中添加了{symbol}(市值: {market_caps[symbol]})")
            # 移除了在黑名单中的记录
    
    return sectors_500, changes_500

# 写入日志文件
def write_log_file(output_file, original_differences, changes_5000, changes_500):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(output_file, 'w') as f:
        f.write(f"=== 更新时间: {timestamp} ===\n\n")
        
        # 写入原有差异信息
        if not original_differences:
            f.write("没有发现原有差异！\n\n")
        else:
            f.write("发现原有差异：\n")
            for sector, diff in original_differences.items():
                f.write(f"\n部门: {sector}\n")
                if diff['in_screener_not_in_sectors']:
                    f.write("在screener文件中有，但在sectors_all中没有的符号 (已过滤screener黑名单):\n")
                    f.write(str(diff['in_screener_not_in_sectors']) + "\n")
        
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
    
    sectors_all_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    sectors_5000_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_5000.json'
    sectors_500_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_500.json'
    blacklist_file = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'
    
    # 读取数据
    screener_data, market_caps = read_screener_file(screener_file)
    sectors_all_data = read_sectors_file(sectors_all_file)
    sectors_5000_data = read_sectors_file(sectors_5000_file)
    sectors_500_data = read_sectors_file(sectors_500_file)
    blacklist = read_blacklist_file(blacklist_file)
    
    # 比较差异并过滤黑名单
    differences = compare_differences(screener_data, sectors_all_data, blacklist)
    
    # 处理Sectors_5000.json
    updated_sectors_5000, changes_5000 = process_sectors_5000(sectors_5000_data, screener_data, market_caps, blacklist)
    save_sectors_file(sectors_5000_file, updated_sectors_5000)
    
    # 处理Sectors_500.json
    updated_sectors_500, changes_500 = process_sectors_500(sectors_500_data, screener_data, market_caps, blacklist)
    save_sectors_file(sectors_500_file, updated_sectors_500)
    
    # 写入汇总日志文件
    output_file = '/Users/yanzhang/Documents/News/screener_sectors.txt'
    write_log_file(output_file, differences, changes_5000, changes_500)
    
    # 准备弹窗消息
    message = ""
    
    # 添加原有差异信息
    if not differences:
        message += "没有发现原有差异！\n\n"
    else:
        message += "发现原有差异并已写入文件！\n\n"
    
    # 添加5000.json变更信息
    if changes_5000:
        message += "Sectors_5000.json 变更:\n"
        for change in changes_5000[:10]:  # 限制显示数量避免弹窗过大
            message += f"- {change}\n"
        if len(changes_5000) > 10:
            message += f"- 以及其他 {len(changes_5000) - 10} 项变更...\n"
        message += "\n"
    else:
        message += "Sectors_5000.json 没有变更\n\n"
    
    # 添加500.json变更信息
    if changes_500:
        message += "Sectors_500.json 变更:\n"
        for change in changes_500[:10]:  # 限制显示数量避免弹窗过大
            message += f"- {change}\n"
        if len(changes_500) > 10:
            message += f"- 以及其他 {len(changes_500) - 10} 项变更...\n"
    else:
        message += "Sectors_500.json 没有变更\n"
    
    message += "\n所有变更已写入日志文件！"
    
    # 显示弹窗
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK" with title "处理结果"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

if __name__ == "__main__":
    main()