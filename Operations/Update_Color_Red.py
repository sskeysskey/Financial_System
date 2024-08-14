import json

def parse_earnings_release(file_path):
    """解析Earnings Release文件，提取symbol"""
    symbols = set()
    try:
        with open(file_path, 'r') as file:
            for line in file:
                symbol = line.split(':')[0].strip()
                symbols.add(symbol)
    except FileNotFoundError:
        print(f"文件未找到: {file_path}")
    except Exception as e:
        print(f"读取文件时发生错误: {e}")
    return symbols

earnings_release_path = '/Users/yanzhang/Documents/News/Earnings_Release_new.txt'
color_json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Colors.json'
sectors_all_json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
earnings_symbols = parse_earnings_release(earnings_release_path)

# 读取Economics分组内容
economics_symbols = set()
try:
    with open(sectors_all_json_path, 'r', encoding='utf-8') as file:
        sectors_data = json.load(file)
        economics_symbols = set(sectors_data.get('Economics', []))
except FileNotFoundError:
    print(f"文件未找到: {sectors_all_json_path}")
except json.JSONDecodeError:
    print(f"JSON解析错误: {sectors_all_json_path}")
except Exception as e:
    print(f"读取文件时发生错误: {e}")

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

if 'red_keywords' in colors:
    colors['red_keywords'] = [symbol for symbol in colors['red_keywords']
                              if symbol in economics_symbols or symbol in earnings_symbols]
else:
    colors['red_keywords'] = []

for symbol in earnings_symbols:
    if symbol not in colors['red_keywords']:
        colors['red_keywords'].append(symbol)

try:
    with open(color_json_path, 'w', encoding='utf-8') as file:
        json.dump(colors, file, ensure_ascii=False, indent=4)
except Exception as e:
    print(f"写入文件时发生错误: {e}")