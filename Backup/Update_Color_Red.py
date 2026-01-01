import json
import subprocess

def display_dialog(message):
    # AppleScript 代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def parse_earnings_release(file_path):
    """解析 Earnings Release 文件，提取 symbol"""
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
        print(f"读取文件时发生错误 ({file_path}): {e}")
    return symbols

def main():
    earnings_release_paths = [
        '/Users/yanzhang/Coding/News/Earnings_Release_new.txt',
        '/Users/yanzhang/Coding/News/Earnings_Release_next.txt',
        '/Users/yanzhang/Coding/News/Earnings_Release_third.txt',
        '/Users/yanzhang/Coding/News/Earnings_Release_fourth.txt',
        '/Users/yanzhang/Coding/News/Earnings_Release_fifth.txt'
    ]
    color_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Colors.json'
    sectors_all_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'

    # 合并三个文件中的 symbols
    earnings_symbols = set()
    for path in earnings_release_paths:
        earnings_symbols |= parse_earnings_release(path)

    # 读取 Sectors_All.json 中的 Economics 部分
    try:
        with open(sectors_all_json_path, 'r', encoding='utf-8') as file:
            sectors_data = json.load(file)
            economics_symbols = set(sectors_data.get('Economics', []))
    except FileNotFoundError:
        print(f"文件未找到: {sectors_all_json_path}")
        economics_symbols = set()
    except json.JSONDecodeError:
        print(f"JSON 解析错误: {sectors_all_json_path}")
        economics_symbols = set()
    except Exception as e:
        print(f"读取文件时发生错误 ({sectors_all_json_path}): {e}")
        economics_symbols = set()

    # 读取 Colors.json
    try:
        with open(color_json_path, 'r', encoding='utf-8') as file:
            colors = json.load(file)
    except FileNotFoundError:
        print(f"文件未找到: {color_json_path}")
        colors = {}
    except json.JSONDecodeError:
        print(f"JSON 解析错误: {color_json_path}")
        colors = {}
    except Exception as e:
        print(f"读取文件时发生错误 ({color_json_path}): {e}")
        colors = {}

    # 确保 'red_keywords' 键存在且为列表
    if 'red_keywords' not in colors:
        colors['red_keywords'] = []

    # 先保留 colors 中已有的、又在 economics_symbols 中的 red_keywords
    colors['red_keywords'] = list(
        set(colors.get('red_keywords', [])) & economics_symbols
    )

    # 将所有新的 earnings_symbols（不在已有 red_keywords 中）加入
    for symbol in earnings_symbols:
        if symbol and symbol not in colors['red_keywords']:
            colors['red_keywords'].append(symbol)

    # 写回 Colors.json
    try:
        with open(color_json_path, 'w', encoding='utf-8') as file:
            json.dump(colors, file, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

if __name__ == "__main__":
    main()