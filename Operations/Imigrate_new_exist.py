import os
import re
import sys
import json
import argparse
# 修改：额外导入 timedelta 用于计算日期差
from datetime import datetime, timedelta

# 锁文件，用于记录上次执行日期
LOCK_FILE = os.path.join(os.path.dirname(__file__), '.last_run_date')

# 文件路径
files = {
    'ETFs': '/Users/yanzhang/Coding/News/backup/ETFs.txt',
    'Earnings_Release': '/Users/yanzhang/Coding/News/backup/Earnings_Release.txt',
    'Economic_Events': '/Users/yanzhang/Coding/News/backup/Economic_Events.txt'
}

new_files = {
    'ETFs': '/Users/yanzhang/Coding/News/ETFs_new.txt',
    '10Y_newhigh': '/Users/yanzhang/Coding/News/10Y_newhigh_stock.txt',
    'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_new.txt',
    'Economic_Events': '/Users/yanzhang/Coding/News/Economic_Events_new.txt'
}

next_files = {
    'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_next.txt',
    'Economic_Events': '/Users/yanzhang/Coding/News/Economic_Events_next.txt'
}

# 新增：定义 third_files 字典，为未来扩展（如 fourth_files）做好准备
third_files = {
    'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_third.txt',
    # 如果 Economic_Events 将来也有 third 文件，可在此处添加
}


# 新的 10Y_newhigh JSON 目标文件路径
TENY_JSON = '/Users/yanzhang/Coding/Financial_System/Modules/10Y_newhigh.json'

# 获取当前星期几，0是周一，6是周日
current_day = datetime.now().weekday()

# 修改：函数重命名并更新逻辑
def check_run_conditions():
    """
    检查脚本是否可以运行。
    规则：
    1. 如果今天已经运行过，则退出。
    2. 如果昨天运行过，则退出。
    如果可以运行，则将上次运行日期更新为今天。
    """
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 新增：计算昨天的日期字符串
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')

    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, 'r') as lf:
            last_run_date = lf.read().strip()
        
        # 检查是否今天已执行
        if last_run_date == today_str:
            print(f"脚本今天 ({today_str}) 已执行过，退出。")
            sys.exit(1)
            
        # 新增：检查是否昨天已执行
        if last_run_date == yesterday_str:
            print(f"脚本昨天 ({yesterday_str}) 已执行过，今天不能执行，退出。")
            sys.exit(1)

    # 如果检查通过，更新锁文件为今天
    with open(LOCK_FILE, 'w') as lf:
        lf.write(today_str)
    print(f"脚本执行条件检查通过，最后运行日期已更新为 {today_str}。")


def format_line(line):
    parts = re.split(r'\s*:\s*', line.strip(), 2)
    if len(parts) == 3:
        symbol, _, rest = parts
        return f"{symbol:<7}: {rest}"
    elif len(parts) == 2:
        symbol, rest = parts
        return f"{symbol:<7}: {rest}"
    else:
        return line.strip()

# 修改：更新 process_and_rename_files 函数以包含 third -> next 的重命名逻辑
def process_and_rename_files():
    # 检查 Earnings_Release 的 new 和 next 文件是否存在
    earnings_files_exist = all(os.path.exists(f) for f in [
        new_files['Earnings_Release'],
        next_files['Earnings_Release']
    ])

    events_files_exist = all(os.path.exists(f) for f in [
        new_files['Economic_Events'],
        next_files['Economic_Events']
    ])

    if earnings_files_exist:
        # 1. 处理 Earnings_Release 的 new 文件，并将其内容追加到主文件中
        print(f"处理文件: {new_files['Earnings_Release']}")
        process_earnings(new_files['Earnings_Release'], files['Earnings_Release'])

        # 2. 重命名 Earnings_Release 的 next 文件为 new 文件
        print(f"重命名: {next_files['Earnings_Release']} -> {new_files['Earnings_Release']}")
        os.rename(next_files['Earnings_Release'], new_files['Earnings_Release'])
        
        # 3. 新增：检查 third 文件是否存在，如果存在则将其重命名为 next 文件
        # 使用 .get() 方法安全地获取路径，即使 'Earnings_Release' 不在 third_files 中也不会报错
        third_earnings_file = third_files.get('Earnings_Release')
        if third_earnings_file and os.path.exists(third_earnings_file):
            print(f"重命名: {third_earnings_file} -> {next_files['Earnings_Release']}")
            os.rename(third_earnings_file, next_files['Earnings_Release'])
        else:
            print(f"未找到 {third_earnings_file}，跳过 third -> next 的重命名步骤。")

    else:
        print("Earnings_Release 相关文件（new/next）缺失，未执行任何操作。")

    if events_files_exist:    
        # 如果 Economic_Events 的 new 文件存在，则处理它
        if os.path.exists(new_files['Economic_Events']):
            print(f"处理文件: {new_files['Economic_Events']}")
            process_file(new_files['Economic_Events'], files['Economic_Events'])

        # 如果 Economic_Events 的 next 文件存在，则重命名它
        if os.path.exists(next_files['Economic_Events']):
            print(f"重命名: {next_files['Economic_Events']} -> {new_files['Economic_Events']}")
            os.rename(next_files['Economic_Events'], new_files['Economic_Events'])
        
        # 将来如果 Economic_Events 也有 third 文件，可以在此添加类似上面的重命名逻辑
        
    else:
        print("Economic_Events 相关文件（new/next）缺失，未执行任何操作。")

def process_earnings(new_file, backup_file):
    if not os.path.exists(new_file):
        return
    with open(new_file, 'r') as fin, open(backup_file, 'a') as fout:
        fout.write('\n')
        lines = [L.rstrip('\n') for L in fin]
        for idx, line in enumerate(lines):
            parts = [p.strip() for p in line.split(':')]
            if len(parts) == 3:
                symbol, _, date = parts
                out = f"{symbol:<7}: {date}"
            elif len(parts) == 2:
                symbol, date = parts
                out = f"{symbol:<7}: {date}"
            else:
                out = line.strip()

            # 最后一行不加换行
            if idx < len(lines) - 1:
                fout.write(out + "\n")
            else:
                fout.write(out)
    os.remove(new_file)

def process_file(new_file, existing_file):
    if os.path.exists(new_file):
        with open(new_file, 'r') as file_a, open(existing_file, 'a') as file_b:
            file_b.write('\n')  # 在迁移内容前首先输入一个回车
            lines = file_a.readlines()
            for i, line in enumerate(lines):
                if 'Earnings_Release' in new_file:
                    # 使用正则表达式去除 " : 数字" 部分
                    processed_line = re.sub(r'\s*:\s*\d+\s*', '', line, count=1)
                    formatted_line = format_line(processed_line)
                    if i == len(lines) - 1:  # 如果是最后一行
                        file_b.write(formatted_line.rstrip())  # 移除行尾的空白字符，但不添加新行
                    else:
                        file_b.write(formatted_line + '\n')
                else:
                    if i == len(lines) - 1:  # 如果是最后一行
                        file_b.write(line.rstrip())  # 移除行尾的空白字符，但不添加新行
                    else:
                        file_b.write(line)
        os.remove(new_file)

def process_etf_file(new_file, existing_file):
    if not os.path.exists(new_file):
        return

    # 读取现有文件的所有内容（不使用 readlines 以避免自动添加换行符）
    with open(existing_file, 'r') as f:
        existing_content = f.read()
    
    # 获取现有的符号集
    existing_symbols = {line.split(':', 1)[0].strip() 
                       for line in existing_content.split('\n') if line.strip()}
    
    # 读取新文件的所有内容
    with open(new_file, 'r') as f:
        new_content = f.read()
    
    # 处理新内容
    new_lines_to_add = []
    for line in new_content.split('\n'):
        if not line.strip():
            continue
        symbol = line.split(':', 1)[0].strip()
        if symbol not in existing_symbols:
            new_lines_to_add.append(line)
            existing_symbols.add(symbol)
    
    # 写入合并后的内容
    if new_lines_to_add:
        with open(existing_file, 'w') as f:
            if existing_content and existing_content.strip():
                # 如果现有内容非空，添加新内容时需要换行符分隔
                content_to_write = existing_content + '\n' + '\n'.join(new_lines_to_add)
            else:
                # 如果现有内容为空，直接写入新内容
                content_to_write = '\n'.join(new_lines_to_add)
            
            # 写入内容，确保末尾没有换行符
            f.write(content_to_write.rstrip('\n'))
    
    os.remove(new_file)

# 新增：10Y_newhigh 的 JSON 处理逻辑（已更新以适应新的JSON结构）
def process_10y_json(new_file, json_file):
    """
    读取 new_file，提取 Symbol 和 Price。
    将其与 json_file 中的 "stocks" 部分合并：
      - 不存在则新增
      - 存在则当且仅当 new_price > old_price 时更新
    最终将更新后的 "stocks" 和原有的 "others" 一起写回 JSON 文件。
    处理完删除 new_file。
    """
    if not os.path.exists(new_file):
        return

    # 确保目标目录存在
    target_dir = os.path.dirname(json_file)
    if target_dir and not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    # --- 修改开始：调整JSON加载逻辑 ---
    
    # 初始化用于存储 "stocks" 和 "others" 的变量
    stock_data = {}
    other_data = []
    full_json_data = {}

    if os.path.exists(json_file):
        try:
            with open(json_file, 'r') as jf:
                content = jf.read().strip()
                if content:
                    # 加载整个JSON对象
                    full_json_data = json.loads(content)
                    if not isinstance(full_json_data, dict):
                        print("警告：JSON 顶层结构不是字典，将重置。")
                        full_json_data = {}

                    # 提取 "stocks" 数据
                    # 假设 "stocks" 是一个列表，且我们只关心列表中的第一个字典
                    if 'stocks' in full_json_data and isinstance(full_json_data['stocks'], list) and full_json_data['stocks']:
                        # 为了稳健性，合并 "stocks" 列表中的所有字典
                        for item in full_json_data['stocks']:
                            if isinstance(item, dict):
                                stock_data.update({str(k): str(v) for k, v in item.items()})

                    # 提取 "others" 数据，用于后续写回
                    if 'others' in full_json_data and isinstance(full_json_data['others'], list):
                        other_data = full_json_data['others']
                
        except Exception as e:
            print(f"警告：读取或解析 JSON 时出错，将以空数据结构继续。错误：{e}")
            # 如果解析失败，重置所有数据结构
            stock_data = {}
            other_data = []

    # --- 修改结束：调整JSON加载逻辑 ---

    # 解析 new 文件并合并到 stock_data 中 (这部分逻辑不变)
    updates = 0
    inserts = 0
    with open(new_file, 'r') as fin:
        for raw in fin:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 4:
                print(f"跳过异常行（少于4段）：{line}")
                continue
            sector, symbol, change, price_str = parts[:4]

            price_clean = price_str.replace(',', '')
            try:
                new_price = float(price_clean)
            except ValueError:
                print(f"跳过价格不可解析的行：{line}")
                continue

            sym = symbol.strip()
            if not sym:
                print(f"跳过空 symbol 的行：{line}")
                continue

            if sym not in stock_data:
                stock_data[sym] = f"{new_price}"
                inserts += 1
            else:
                old_str = str(stock_data[sym]).replace(',', '')
                try:
                    old_price = float(old_str)
                except ValueError:
                    old_price = float('-inf')
                if new_price > old_price:
                    stock_data[sym] = f"{new_price}"
                    updates += 1

    # --- 修改开始：调整JSON保存逻辑 ---
    
    # 重构要写回的完整JSON结构
    final_json_to_write = {
        "stocks": [stock_data],  # 将更新后的 stock_data 放入 "stocks" 列表
        "others": other_data     # 将之前保存的 "others" 数据加回去
    }

    try:
        with open(json_file, 'w') as jf:
            # 将重构后的完整对象写入文件
            json.dump(final_json_to_write, jf, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"错误：写入 JSON 失败：{e}")
        return

    # --- 修改结束：调整JSON保存逻辑 ---

    # 删除 new 文件
    try:
        os.remove(new_file)
    except Exception as e:
        print(f"警告：删除 new 文件失败：{e}")
        return

    print(f"10Y_newhigh JSON 处理完成：新增 {inserts} 条，更新 {updates} 条。")

def main(mode):
    if mode == 'etf':
        # 周二到周天允许运行
        if 1 <= current_day <= 6:  # 周二到周天
            process_etf_file(new_files['ETFs'], files['ETFs'])
            # 将原来的 process_file(new_files['10Y_newhigh'], files['10Y_newhigh'])
            # 替换为 JSON 更新逻辑
            process_10y_json(new_files['10Y_newhigh'], TENY_JSON)
        else:
            print("Not right date. ETF 模式只在周二到周天运行。")
    elif mode == 'other':
        # 周日或周一允许运行
        if current_day in (6, 0):
            # 修改：调用更新后的函数
            check_run_conditions()
            process_and_rename_files()
        else:
            print("Not right date. Other 模式只在周一运行。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process files based on the given mode.')
    parser.add_argument('mode', choices=['etf', 'other'], help='The processing mode: etf or other')
    args = parser.parse_args()
    main(args.mode)