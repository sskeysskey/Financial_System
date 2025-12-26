import os
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
import pyautogui
import random
import time
import sys
import threading
import json
import subprocess
from datetime import datetime, timedelta

# ==== 1) 星期判断，设置 do_crawl / do_update ====
today = datetime.now().weekday()
if today in (4, 5):        # 周五(4)、周六(5)
    do_crawl, do_update = True, True
elif today in (0, 6):      # 周一(0)、周日(6)
    do_crawl, do_update = False, True
else:                       # 其余时间都退出
    print("今天不是周五/周六/周一/周日，程序退出。")
    sys.exit(0)
# ============================================

# 添加鼠标移动功能的函数
def move_mouse_periodically():
    while True:
        try:
            # 获取屏幕尺寸
            screen_width, screen_height = pyautogui.size()
            
            # 随机生成目标位置，避免移动到屏幕边缘
            x = random.randint(100, screen_width - 100)
            y = random.randint(100, screen_height - 100)
            
            # 缓慢移动鼠标到随机位置
            pyautogui.moveTo(x, y, duration=1)
            
            # 等待30-60秒再次移动
            time.sleep(random.randint(30, 60))
            
        except Exception as e:
            print(f"鼠标移动出错: {str(e)}")
            time.sleep(30)

def display_dialog(message):
    # AppleScript 代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

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

# ==== 2) 如果需要爬虫，就启动鼠标保活线程 + Selenium 爬虫 + 写文件 ====
if do_crawl:
    # 在主程序开始前启动鼠标移动线程
    mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
    mouse_thread.start()

    # 文件路径
    file_path = '/Users/yanzhang/Coding/News/Economic_Events_next.txt'
    backup_dir = '/Users/yanzhang/Coding/News/backup/backup'

    # 检查原始文件是否存在
    original_file_exists = os.path.exists(file_path)

    # 如果原始文件存在，进行备份
    if original_file_exists:
        timestamp = datetime.now().strftime('%y%m%d')
        backup_filename = f'Economic_Events_next_{timestamp}.txt'
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # 确保备份目录存在
        os.makedirs(backup_dir, exist_ok=True)
        
        # 复制文件到备份目录
        shutil.copy2(file_path, backup_path)

        # 读取原有内容
        with open(file_path, 'r') as file:
            existing_content = set(file.read().splitlines())
    else:
        existing_content = set()

    chrome_options = Options()
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

    # ChromeDriver 路径
    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

    # 设置 ChromeDriver
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # start_date = datetime(2025, 8, 4)
    # end_date = datetime(2025, 8, 9)

    # 获取当前系统日期
    current_date = datetime.now()
    # 计算离当前最近的周天
    start_date = current_date + timedelta(days=(6 - current_date.weekday()))
    # 计算往后延6天的周六
    end_date = start_date + timedelta(days=6)

    # <<< 更改开始 >>>
    # ----------------------------------------------------------------------------------
    # 1. 简化事件过滤器，只保留核心事件名称作为“基本名称”
    #    程序将检查从网站获取的事件名称是否以这些基本名称开头。
    Event_Filter_Bases = {
        "GDP 2nd Estimate",
        "GDP Advance",
        "GDP Final",
        "GDP Cons Spending Prelim",
        "GDP Cons Spending Final",
        "Non-Farm Payrolls",
        "ISM N-Mfg PMI",
        "ISM Manufacturing PMI",
        "ADP National Employment",
        "Unemployment Rate",
        "International Trade",
        "Import Prices MM",
        "Import Prices YY",
        "CPI MM, SA",
        "CPI YY, NSA",
        "Core CPI MM, SA",
        "Core CPI YY, NSA",
        "Fed Funds Tgt Rate",
        "PPI Final Demand YY",
        "PPI exFood/Energy MM",
        "PPI exFood/Energy YY",
        "PPI ex Food/Energy/Tr MM",
        "PPI Final Demand MM",
        "PCE Prices Final",
        "PCE Price Index MM",
        "PCE Price Index YY",
        "Core PCE Prices Final",
        "Core PCE Prices Prelim",
        "Core PCE Price Index MM",
        "Core PCE Price Index YY",
        "U Mich Sentiment Prelim",
        "Retail Sales MM",
        "Initial Jobless Clm",
        "U Mich Sentiment Final",
        "New Home Sales Chg MM",
        "New Home Sales-Units",
    }

    # 定义一个包含所有目标国家代码的集合
    target_countries = {
        "US"
    }

    new_content_added = False

    # 使用追加模式打开文件
    with open(file_path, 'a') as output_file:
        # output_file.write('\n')
        change_date = start_date
        delta = timedelta(days=1)
        
        while change_date <= end_date:
            formatted_change_date = change_date.strftime('%Y-%m-%d')
            offset = 0
            has_data = True
            
            while has_data:
                url = f"https://finance.yahoo.com/calendar/economic?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
                driver.get(url)
                
                wait = WebDriverWait(driver, 4)
                try:
                    # 定位包含table的div容器，使用class中稳定的部分
                    table_container = wait.until(EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.table-container")))
                    
                    # 直接选择table下的所有tr
                    rows = table_container.find_elements(By.TAG_NAME, "tr")
                except TimeoutException:
                    rows = []  # 如果超时，则设置 rows 为空列表
                
                if not rows:
                    has_data = False
                else:
                    for row in rows:
                        if row.get_attribute("role") == "columnheader":
                            continue
                        
                        cells = row.find_elements(By.TAG_NAME, "td")

                        if len(cells) < 2:
                            continue
                        
                        try:
                            event = cells[0].text.strip()
                            country = cells[1].text.strip()
                            
                            # 2. 修改匹配和写入逻辑
                            #    不再使用 "in" 进行精确匹配，而是遍历基本名称列表，进行前缀匹配。
                            if event and country and country in target_countries:
                                matched_base_event = None
                                # 遍历所有基本事件名称
                                for base_event in Event_Filter_Bases:
                                    # 如果网站上的事件名称以我们的某个基本名称开头
                                    if event.startswith(base_event):
                                        # 记录这个基本名称，它将用于写入文件
                                        matched_base_event = base_event
                                        # 找到后即可退出内层循环
                                        break
                                
                                # 如果找到了匹配项
                                if matched_base_event:
                                    # 构造条目时，使用 matched_base_event (基本名称) 而不是 event (网站上的完整名称)
                                    entry = f"{formatted_change_date} : {matched_base_event} [{country}]"
                                    if entry not in existing_content:
                                        output_file.write(entry + "\n")
                                        existing_content.add(entry) # 实时更新，防止同一批次内重复写入
                                        new_content_added = True
                            # ----------------------------------------------------------------------------------
                            # <<< 更改结束 >>>
                                        
                        except Exception as e:
                            print(f"处理表格行时出错: {str(e)}")
                            continue
                                
                    offset += 100
                        
            change_date += delta

    # 关闭浏览器
    driver.quit()

else:
    print("今天是周一或周日，跳过爬虫部分。")

# ==== 3) 如果需要更新 JSON，就调用 update_sectors_panel ====
if do_update:
    update_sectors_panel()
else:
    print("今天不更新 JSON。")
