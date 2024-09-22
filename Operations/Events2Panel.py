import json
import subprocess
from datetime import datetime

def display_dialog(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def is_sunday_or_monday():
    """检查当前日期是否为周日或周一"""
    return datetime.now().weekday() in {6, 0} # 6 代表周日，0 代表周一

def update_sectors_panel():
    """更新sectors_panel的主要逻辑"""
    # 文件路径
    event_file_path = '/Users/yanzhang/Documents/News/Economic_Events_new.txt'
    sectors_panel_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
    symbol_mapping_path = '/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json'

    try:
        # 读取文件内容
        with open(event_file_path, 'r', encoding='utf-8') as file:
            events = file.readlines()

        with open(symbol_mapping_path, 'r', encoding='utf-8') as file:
            symbol_mapping = json.load(file)

        with open(sectors_panel_path, 'r', encoding='utf-8') as file:
            sectors_panel = json.load(file)

        # 清空Economics分组的数据
        sectors_panel['Economics'] = {}

        # 处理每个事件
        for event in events:
            event = event.strip()
            if ' : ' not in event:
                print(f"Warning: Skipping malformed event: {event}")
                continue
            # 提取事件描述和日期中的天字段
            date_part, description_part = event.split(' : ', 1)
            day_field = date_part.split('-')[-1].strip()
            description = description_part.split(' [')[0].strip()

            # 在symbol_mapping中查找匹配
            if description in symbol_mapping:
                economics_key = symbol_mapping[description]
                combined_value = f"{day_field} {economics_key}"

                # 更新sectors_panel中的Economics分组
                sectors_panel['Economics'][economics_key] = combined_value

        # 将更新后的内容写回到Sectors_panel.json
        with open(sectors_panel_path, 'w', encoding='utf-8') as file:
            json.dump(sectors_panel, file, ensure_ascii=False, indent=4)

        print("更新已完成！")
    except Exception as e:
        error_message = f"更新过程中发生错误: {str(e)}"
        print(error_message)
        display_dialog(error_message)

def main():
    if is_sunday_or_monday():
        update_sectors_panel()
    else:
        display_dialog("今天不是周日或周一，不执行更新操作。")

if __name__ == "__main__":
    main()