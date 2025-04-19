import os
import shutil
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import pyautogui
import random
import time
import threading

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

# 在主程序开始前启动鼠标移动线程
mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
mouse_thread.start()

# 文件路径
file_path = '/Users/yanzhang/Documents/News/Economic_Events_next.txt'
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'

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

# start_date = datetime(2024, 12, 2)
# end_date = datetime(2024, 12, 8)

# 获取当前系统日期
current_date = datetime.now()
# 计算离当前最近的周天
start_date = current_date + timedelta(days=(6 - current_date.weekday()))
# 计算往后延6天的周六
end_date = start_date + timedelta(days=6)

Event_Filter = {
    "GDP 2nd Estimate*", "Non-Farm Payrolls*", "Core PCE Price Index MM *",
    "Core PCE Price Index YY*", "ISM Manufacturing PMI",
    "ADP National Employment*", "International Trade $ *",
    "ISM N-Mfg PMI", "CPI YY, NSA*", "Core CPI MM, SA*",
    "CPI MM, SA*", "Core CPI YY, NSA*", "Fed Funds Tgt Rate *",
    "PPI Final Demand YY*", "PPI exFood/Energy MM*", "PPI ex Food/Energy/Tr MM*",
    "PPI Final Demand MM*", "Retail Sales MM *", "GDP Final*", "Core PCE Prices Fnal*",
    "PCE Prices Final *", "GDP Cons Spending Final*", "Pending Homes Index",
    "PCE Price Index MM*", "Unemployment Rate*", "U Mich Sentiment Prelim",
    "New Home Sales-Units *", "New Home Sales Chg MM *",
    "GDP Cons Spending Prelim*", "Core PCE Prices Prelim*",
    "Corporate Profits Prelim*", "Initial Jobless Clm*", "U Mich Sentiment Final",
    "GDP Advance*", "PCE Price Index YY *", "PPI exFood/Energy YY*", "Import Prices MM*",
    "Import Prices YY*"
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
                try:
                    for row in rows:
                        # 跳过可能的表头行
                        if row.get_attribute("role") == "columnheader":
                            continue
                        
                        # 直接获取所有td元素
                        cells = row.find_elements(By.TAG_NAME, "td")

                        # 确保行中至少有足够的单元格
                        if len(cells) < 2:
                            continue
                        # 安全地获取事件和国家信息
                        try:
                            event = cells[0].text.strip()
                            country = cells[1].text.strip()
                            
                            # 只有当事件和国家都符合过滤条件时才处理
                            if event and country and event in Event_Filter and country in target_countries:
                                try:
                                    # 尝试获取事件时间
                                    event_time = next(
                                        (cell.text for cell in cells if cell.get_attribute('aria-label') == 'Event Time'),
                                        "No event time available"
                                    )
                                    
                                    # 构造条目并写入
                                    entry = f"{formatted_change_date} : {event} [{country}]"
                                    if entry not in existing_content:
                                        output_file.write(entry + "\n")
                                        new_content_added = True
                                        
                                except Exception as e:
                                    print(f"处理事件时间时出错: {str(e)}")
                                    continue
                                    
                        except Exception as e:
                            print(f"处理表格行时出错: {str(e)}")
                            continue
                            
                    offset += 100  # 为下一个子页面增加 offset
                    
                except TimeoutException:
                    print(f"日期 {formatted_change_date} 没有找到数据。跳转到下一个日期。")
        change_date += delta

# 关闭浏览器
driver.quit()