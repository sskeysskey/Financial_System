import json
import subprocess
import os
from datetime import datetime

def display_dialog(message):
    # AppleScript 代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def is_valid():
    """检查当前日期是否为星期日(6)、星期一(0)或星期二(1)"""
    return datetime.now().weekday() in {6, 0, 1}

def update_sectors_panel():
    """更新sectors_panel的主要逻辑"""
    # 文件路径
    path_new  = '/Users/yanzhang/Coding/News/Economic_Events_new.txt'
    path_next = '/Users/yanzhang/Coding/News/Economic_Events_next.txt'
    sectors_panel_path   = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'
    symbol_mapping_path  = '/Users/yanzhang/Coding/Financial_System/Modules/Symbol_mapping.json'

    # 按顺序收集存在的事件文件
    event_files = []
    if os.path.exists(path_new):
        event_files.append(('new', path_new))
    if os.path.exists(path_next):
        event_files.append(('next', path_next))

    if not event_files:
        display_dialog("未找到 Economic_Events_new.txt 和 Economic_Events_next.txt，未执行更新。")
        return

    try:
        # 读取 symbol_mapping 和 原 sectors_panel
        with open(symbol_mapping_path, 'r', encoding='utf-8') as f:
            symbol_mapping = json.load(f)

        with open(sectors_panel_path, 'r', encoding='utf-8') as f:
            sectors_panel = json.load(f)

        # 清空 Economics 分组
        sectors_panel['Economics'] = {}

        # 依次处理 new、next
        for tag, filepath in event_files:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    event = line.strip()
                    if ' : ' not in event:
                        print(f"Warning: 跳过格式不对的行：{event}")
                        continue

                    # 拆分 "YYYY-MM-DD : 描述 [区域]" -> day_field, description
                    date_part, desc_part = event.split(' : ', 1)
                    day_field = date_part.split('-')[-1].strip()
                    description = desc_part.split(' [')[0].strip()

                    if description not in symbol_mapping:
                        # 如果描述不在映射表中，跳过
                        continue

                    economics_key = symbol_mapping[description]
                    combined_value = f"{day_field} {economics_key}"

                    existing = sectors_panel['Economics'].get(economics_key)
                    if existing is None:
                        # 之前未写入过，直接写
                        sectors_panel['Economics'][economics_key] = combined_value
                    else:
                        if existing == combined_value:
                            # 完全重复，跳过
                            continue
                        else:
                            if tag == 'next':
                                # 如果是 next 文件，优先覆盖 new 的值
                                sectors_panel['Economics'][economics_key] = combined_value
                            # 如果 tag == 'new'，且 new 里出现了两次同 key 的不同值，
                            # 这里默认保留第一次，也可以根据需要改成覆盖

        # 写回 sectors_panel.json
        with open(sectors_panel_path, 'w', encoding='utf-8') as f:
            json.dump(sectors_panel, f, ensure_ascii=False, indent=4)

        print("更新已完成！")

    except Exception as e:
        error_message = f"更新过程中发生错误: {e}"
        print(error_message)
        display_dialog(error_message)

def main():
    if is_valid():
        update_sectors_panel()
    else:
        display_dialog("今天不是周日、周一或周二，不执行更新操作。")

if __name__ == "__main__":
    main()