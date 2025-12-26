import os
import shutil
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import json
import pyautogui
import random
import time
import sys
import threading

# 判断今天是否为周五（4）或周六（5），否则直接退出
today = datetime.now().weekday()  
if today not in (4, 5):  
    print("今天不是周五或周六，程序退出。")  
    sys.exit(0)  

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
file_path = '/Users/yanzhang/Coding/News/Stock_Splits_next.txt'
backup_dir = '/Users/yanzhang/Coding/News/backup/backup'

# 检查文件是否已经存在
file_already_exists = os.path.exists(file_path)

# 如果文件存在，进行备份
if file_already_exists:
    timestamp = datetime.now().strftime('%y%m%d')
    backup_filename = f'Stock_Splits_next_{timestamp}.txt'
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # 确保备份目录存在
    os.makedirs(backup_dir, exist_ok=True)
    
    # 复制文件到备份目录
    shutil.copy2(file_path, backup_path)

# 读取原有内容（如果文件存在）
existing_content = set()
if file_already_exists:
    with open(file_path, 'r') as file:
        existing_content = set(file.read().splitlines())

chrome_options = Options()
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

# ChromeDriver 设置
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

# 加载JSON文件
with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'r') as file:
    data = json.load(file)

# start_date = datetime(2025, 7, 28)
# end_date = datetime(2025, 8, 3)

# 获取当前系统日期
current_date = datetime.now()
# 计算离当前最近的周天（周日）
start_date = current_date + timedelta(days=(6 - current_date.weekday()))
# 计算往后延6天的日期
end_date = start_date + timedelta(days=6)

new_content_added = False

# 用于存储结果的列表
results = []

change_date = start_date
delta = timedelta(days=1)

while change_date <= end_date:
    formatted_change_date = change_date.strftime('%Y-%m-%d')
    offset = 0
    has_data = True
    
    while has_data:
        url = f"https://finance.yahoo.com/calendar/splits?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
        driver.get(url)
        
        try:
            # 备选方案2：使用更复杂的属性组合
            # rows = WebDriverWait(driver, 4).until(
            #     EC.presence_of_all_elements_located((
            #         By.CSS_SELECTOR, 
            #         "table tbody tr[role='row']"
            #     ))
            # )

            # # 备选方案3：使用XPath（功能更强大但性能略低）
            rows = WebDriverWait(driver, 4).until(
                EC.presence_of_all_elements_located((
                    By.XPATH, 
                    "//table//tbody/tr"
                ))
            )
        except TimeoutException:
            has_data = False
            continue
        
        for row in rows:
            try:
                # 获取股票代码(symbol)
                symbol = row.find_element(
                    By.CSS_SELECTOR, 
                    'a.loud-link.fin-size-small'
                ).text
                
                # 获取公司名称(company)
                company = row.find_element(
                    By.CSS_SELECTOR, 
                    'td.tw-text-left.tw-max-w-xs.tw-whitespace-normal'
                ).text

                # # 获取股票代码：使用更通用的属性选择器
                # symbol = row.find_element(
                #     By.CSS_SELECTOR, 
                #     'td:first-child a[href^="/quote/"]'
                # ).text
                
                # # 获取公司名称：使用位置和语义化属性
                # company = row.find_element(
                #     By.CSS_SELECTOR, 
                #     'td:nth-child(2)'  # 第二列就是公司名称
                # ).text.strip()
            except Exception as e:
                print(f"Error extracting data from row: {e}")
                continue
            
            for category, symbols in data.items():
                if symbol in symbols:
                    entry = f"{symbol}: {formatted_change_date} - {company}"
                    if entry not in existing_content:
                        results.append(entry)
                        new_content_added = True
                    break
        
        offset += 100
    
    change_date += delta

# 关闭浏览器
driver.quit()

# 只有在有新结果时才追加到文件
if results:
    with open(file_path, 'a') as output_file:
        # 如果文件已经存在且不是空的，添加一个换行符分隔
        if os.path.getsize(file_path) > 0:
            output_file.write('\n')
        for result in results:
            output_file.write(result + "\n")
    
    # 移除最后一行的回车换行符
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            lines = file.readlines()
        
        # 去除开头和结尾的空行，保留内容之间的空行
        lines = [line for line in lines if line.strip() or any(lines[i].strip() for i in range(len(lines)) if i != lines.index(line))]
        
        with open(file_path, 'w') as file:
            file.writelines(lines)
else:
    print("没有新内容添加，文件保持不变。")