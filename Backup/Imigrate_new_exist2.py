import os
import re
import sys
import subprocess
from datetime import datetime, timedelta

# 锁文件，用于记录上次执行日期
LOCK_FILE = os.path.join(os.path.dirname(__file__), '.last_run_date')

# 文件路径
files = {
    'Earnings_Release': '/Users/yanzhang/Coding/News/backup/Earnings_Release.txt',
    'Economic_Events': '/Users/yanzhang/Coding/News/backup/Economic_Events.txt'
}

new_files = {
    'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_new.txt',
    'Economic_Events': '/Users/yanzhang/Coding/News/Economic_Events_new.txt'
}

next_files = {
    'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_next.txt',
    'Economic_Events': '/Users/yanzhang/Coding/News/Economic_Events_next.txt'
}

third_files = {
    'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_third.txt',
}

fourth_files = {
    'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_fourth.txt',
}

fifth_files = {
    'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_fifth.txt',
}

# 获取当前星期几，0是周一，6是周日
current_day = datetime.now().weekday()

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    # 使用subprocess调用osascript
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def check_run_conditions():
    """
    检查脚本是否可以运行。
    规则：
    1. 如果今天已经运行过，则退出。
    2. 如果昨天运行过，则退出。
    如果可以运行，则将上次运行日期更新为今天。
    """
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 计算昨天的日期字符串
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, 'r') as lf:
            last_run_date = lf.read().strip()
        
        # 检查是否今天已执行
        if last_run_date == today_str:
            print(f"脚本今天 ({today_str}) 已执行过，退出。")
            sys.exit(1)
            
        # 检查是否昨天已执行
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
        
        # 3. 检查 third 文件是否存在，如果存在则将其重命名为 next 文件
        third_earnings_file = third_files.get('Earnings_Release')
        if third_earnings_file and os.path.exists(third_earnings_file):
            print(f"重命名: {third_earnings_file} -> {next_files['Earnings_Release']}")
            os.rename(third_earnings_file, next_files['Earnings_Release'])
        else:
            print(f"未找到 {third_earnings_file}，跳过 third -> next 的重命名步骤。")
            
        # 4. 检查 fourth 文件是否存在，如果存在则将其重命名为 third 文件
        fourth_earnings_file = fourth_files.get('Earnings_Release')
        third_earnings_file_target = third_files.get('Earnings_Release')
        
        if fourth_earnings_file and os.path.exists(fourth_earnings_file):
            if third_earnings_file_target:
                print(f"重命名: {fourth_earnings_file} -> {third_earnings_file_target}")
                os.rename(fourth_earnings_file, third_earnings_file_target)
            else:
                print(f"错误：找到了 {fourth_earnings_file} 但未在 third_files 中为其配置目标路径。")
        else:
            print(f"未找到 {fourth_earnings_file}，跳过 fourth -> third 的重命名步骤。")

        # 5. 检查 fifth 文件是否存在，如果存在则将其重命名为 fourth 文件
        fifth_earnings_file = fifth_files.get('Earnings_Release')
        fourth_earnings_file_target = fourth_files.get('Earnings_Release')
        
        if fifth_earnings_file and os.path.exists(fifth_earnings_file):
            if fourth_earnings_file_target:
                print(f"重命名: {fifth_earnings_file} -> {fourth_earnings_file_target}")
                os.rename(fifth_earnings_file, fourth_earnings_file_target)
            else:
                print(f"错误：找到了 {fifth_earnings_file} 但未在 fourth_files 中为其配置目标路径。")
        else:
            print(f"未找到 {fifth_earnings_file}，跳过 fifth -> fourth 的重命名步骤。")

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
    else:
        print("Economic_Events 相关文件（new/next）缺失，未执行任何操作。")

if __name__ == "__main__":
    # 周日或周一允许运行
    if current_day in (6, 0):
        print("开始执行 Other 模式逻辑...")
        check_run_conditions()
        process_and_rename_files()
    else:
        print("Not right date. Other 模式只在周一（或周日）运行。")
