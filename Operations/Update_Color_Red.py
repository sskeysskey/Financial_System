import json
import sys
import subprocess
from datetime import datetime

def display_dialog(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def check_day():
    """检查当前日期是否为周日或周一"""
    return datetime.now().weekday() in [6, 0]  # 6 代表周日，0 代表周一

def parse_earnings_release(file_path):
    """解析Earnings Release文件，提取symbol"""
    symbols = set()
    try:
        with open(file_path, 'r') as file:
            for line in file:
                parts = line.strip().split(':')
                if parts and parts[0].strip():
                    symbols.add(parts[0].strip())
    except FileNotFoundError:
        print(f"文件未找到: {file_path}")
    except Exception as e:
        print(f"读取文件时发生错误: {e}")
    return symbols

def main():
    if not check_day():
        message = "今天不是周日或周一，不执行更新操作。"
        display_dialog(message)
        return

    earnings_release_path = '/Users/yanzhang/Documents/News/Earnings_Release_new.txt'
    color_json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
    sectors_all_json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    
    earnings_symbols = parse_earnings_release(earnings_release_path)

    try:
        with open(sectors_all_json_path, 'r', encoding='utf-8') as file:
            sectors_data = json.load(file)
            economics_symbols = set(sectors_data.get('Economics', []))
    except FileNotFoundError:
        print(f"文件未找到: {sectors_all_json_path}")
        economics_symbols = set()
    except json.JSONDecodeError:
        print(f"JSON解析错误: {sectors_all_json_path}")
        economics_symbols = set()
    except Exception as e:
        print(f"读取文件时发生错误: {e}")
        economics_symbols = set()

    # 读取颜色json文件
    try:
        with open(color_json_path, 'r', encoding='utf-8') as file:
            colors = json.load(file)
    except FileNotFoundError:
        print(f"文件未找到: {color_json_path}")
        colors = {}
    except json.JSONDecodeError:
        print(f"JSON解析错误: {color_json_path}")
        colors = {}
    except Exception as e:
        print(f"读取文件时发生错误: {e}")
        colors = {}

    colors['red_keywords'] = list(set(colors.get('red_keywords', [])) & economics_symbols)

    for symbol in earnings_symbols:
        if symbol and symbol not in colors['red_keywords']:
            colors['red_keywords'].append(symbol)

    try:
        with open(color_json_path, 'w', encoding='utf-8') as file:
            json.dump(colors, file, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

if __name__ == "__main__":
    main()