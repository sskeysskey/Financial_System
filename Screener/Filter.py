import json
import glob
import os
import time
import subprocess

# 读取screener数据文件
def read_screener_file(filepath):
    screener_data = {}
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split(', ')
                symbol = parts[0].split(': ')[0]
                sector = parts[-1]
                screener_data.setdefault(sector, []).append(symbol)
    return screener_data

# 读取sectors配置文件
def read_sectors_file(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

# 读取黑名单文件
def read_blacklist_file(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

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
    
    sectors_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    blacklist_file = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'
    
    # 读取数据
    screener_data = read_screener_file(screener_file)
    sectors_data = read_sectors_file(sectors_file)
    blacklist = read_blacklist_file(blacklist_file)
    
    # 比较差异并过滤黑名单
    differences = compare_differences(screener_data, sectors_data, blacklist)    
    
    if not differences:
        applescript_code = 'display dialog "没有发现差异！" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    else:
        # 准备写入文件的内容
        output_content = []
        for sector, diff in differences.items():
            output_content.append(f"\n部门: {sector}")
            if diff['in_screener_not_in_sectors']:
                output_content.append("在screener文件中有，但在sectors_all中没有的符号 (已过滤screener黑名单):")
                output_content.append(str(diff['in_screener_not_in_sectors']))
        
        # 写入文件
        output_file = '/Users/yanzhang/Documents/News/screener_sectors.txt'
        with open(output_file, 'w') as f:
            f.write('\n'.join(output_content))
        
        applescript_code = 'display dialog "发现差异并已写入文件！" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)

if __name__ == "__main__":
    main()