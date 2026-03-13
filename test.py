import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import re

class PolymarketScraper:
    def __init__(self):
        # 配置Chrome选项
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 无头模式,如需调试可注释此行
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)
        self.base_url = "https://polymarket.com"
        
    def clean_text(self, text):
        """清理文本中的多余空格和换行"""
        return ' '.join(text.split()).strip()
    
    def extract_percentage(self, text):
        """提取百分比数值"""
        match = re.search(r'(\d+)%', text)
        return match.group(1) + '%' if match else text
    
    def extract_volume(self, text):
        """提取交易量"""
        match = re.search(r'\$[\d.]+[KMB]', text.upper())
        return match.group(0) if match else text
    
    def scrape_type1_detail(self, event_slug):
        """抓取第一类项目的详情页面"""
        detail_url = f"{self.base_url}/event/{event_slug}"
        
        # 在新标签页打开
        self.driver.execute_script(f"window.open('{detail_url}', '_blank');")
        self.driver.switch_to.window(self.driver.window_handles[-1])
        
        try:
            time.sleep(2)  # 等待页面加载
            
            # 抓取type和subtype
            type_text = ""
            subtype_text = ""
            try:
                breadcrumb_links = self.driver.find_elements(By.CSS_SELECTOR, 
                    'a[href*="/dashboards/"], a[href*="/predictions/"]')
                if len(breadcrumb_links) >= 2:
                    type_text = self.clean_text(breadcrumb_links[0].text)
                    subtype_text = self.clean_text(breadcrumb_links[1].text)
            except:
                pass
            
            # 抓取enddate
            enddate = ""
            try:
                date_element = self.driver.find_element(By.XPATH, 
                    "//span[contains(text(), ',')]")
                enddate = self.clean_text(date_element.text)
            except:
                pass
            
            return {
                "type": type_text,
                "subtype": subtype_text,
                "enddate": enddate
            }
            
        finally:
            # 关闭当前标签页并切换回主页
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
    
    def scrape_type1_projects(self):
        """抓取第一类项目(有多个options的项目)"""
        projects = []
        
        try:
            # 找到所有项目卡片
            cards = self.driver.find_elements(By.CSS_SELECTOR, 
                'div.relative.flex.flex-col.justify-between.rounded-xl.shadow-md')
            
            for card in cards:
                try:
                    # 检查是否为第一类型(有多个选项列表)
                    options_list = card.find_elements(By.CSS_SELECTOR, 
                        'div[data-testid="virtuoso-item-list"] > div')
                    
                    if len(options_list) < 2:
                        continue  # 跳过第二类型
                    
                    # 获取项目名称
                    name_element = card.find_element(By.CSS_SELECTOR, 
                        'h2.text-body-base.text-text')
                    name = self.clean_text(name_element.text)
                    
                    # 获取事件slug用于构建详情页URL
                    link_element = card.find_element(By.CSS_SELECTOR, 
                        'a[href^="/event/"]')
                    event_slug = link_element.get_attribute('href').split('/event/')[-1]
                    
                    # 获取volume
                    volume = ""
                    try:
                        volume_element = card.find_element(By.XPATH, 
                            './/span[@class="uppercase"]')
                        volume = self.extract_volume(volume_element.text)
                    except:
                        pass
                    
                    # 获取所有options
                    options = []
                    option_items = card.find_elements(By.CSS_SELECTOR, 
                        'div[data-index]')
                    
                    for item in option_items[:10]:  # 限制最多10个选项
                        try:
                            option_name = item.find_element(By.CSS_SELECTOR, 
                                'p.line-clamp-1.break-all').text
                            option_value = item.find_element(By.CSS_SELECTOR, 
                                'p.text-\\[15px\\].font-semibold').text
                            
                            if option_name and option_value:
                                options.append({
                                    "name": self.clean_text(option_name),
                                    "value": self.extract_percentage(option_value)
                                })
                        except:
                            continue
                    
                    if not options:
                        continue
                    
                    # 获取详情页信息
                    detail_info = self.scrape_type1_detail(event_slug)
                    
                    # 构建项目数据
                    project = {
                        "name": name,
                        "type": detail_info["type"],
                        "subtype": detail_info["subtype"],
                        "volume": volume,
                        "enddate": detail_info["enddate"]
                    }
                    
                    # 添加options
                    for i, option in enumerate(options, 1):
                        project[f"option{i}"] = option["name"]
                        project[f"value{i}"] = option["value"]
                    
                    projects.append(project)
                    print(f"✓ 已抓取第一类项目: {name}")
                    
                except Exception as e:
                    print(f"× 处理第一类项目时出错: {str(e)}")
                    continue
        
        except Exception as e:
            print(f"× 抓取第一类项目失败: {str(e)}")
        
        return projects
    
    def scrape_type2_projects(self):
        """抓取第二类项目(只有单个概率值的项目)"""
        projects = []
        
        try:
            # 找到所有项目卡片
            cards = self.driver.find_elements(By.CSS_SELECTOR, 
                'div.relative.flex.flex-col.justify-between.rounded-xl.shadow-md')
            
            for card in cards:
                try:
                    # 检查是否为第二类型(有单个大概率值)
                    chance_element = None
                    try:
                        chance_element = card.find_element(By.XPATH, 
                            './/p[@class="font-medium text-heading-lg text-center"]')
                    except:
                        continue  # 跳过第一类型
                    
                    # 获取项目名称
                    name_element = card.find_element(By.CSS_SELECTOR, 
                        'h2.text-body-base.text-text')
                    name = self.clean_text(name_element.text)
                    
                    # 获取概率值
                    value = self.extract_percentage(chance_element.text)
                    
                    # 获取volume
                    volume = ""
                    try:
                        volume_element = card.find_element(By.XPATH, 
                            './/span[@class="uppercase"]')
                        volume = self.extract_volume(volume_element.text)
                    except:
                        pass
                    
                    # 获取事件slug用于构建详情页URL
                    link_element = card.find_element(By.CSS_SELECTOR, 
                        'a[href^="/event/"]')
                    event_slug = link_element.get_attribute('href').split('/event/')[-1]
                    
                    # 获取详情页信息(enddate)
                    detail_info = self.scrape_type1_detail(event_slug)
                    
                    project = {
                        "name": name,
                        "value": value,
                        "volume": volume,
                        "enddate": detail_info["enddate"]
                    }
                    
                    projects.append(project)
                    print(f"✓ 已抓取第二类项目: {name}")
                    
                except Exception as e:
                    print(f"× 处理第二类项目时出错: {str(e)}")
                    continue
        
        except Exception as e:
            print(f"× 抓取第二类项目失败: {str(e)}")
        
        return projects
    
    def scrape_current_page(self):
        """抓取当前激活的标签页"""
        print("开始抓取当前页面...")
        
        # 切换到当前激活的窗口
        self.driver.switch_to.window(self.driver.window_handles[-1])
        
        # 等待页面加载完成
        time.sleep(3)
        
        # 滚动页面以加载所有内容
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        # 抓取两类项目
        type1_projects = self.scrape_type1_projects()
        type2_projects = self.scrape_type2_projects()
        
        return {
            "type1_projects": type1_projects,
            "type2_projects": type2_projects
        }
    
    def save_to_json(self, data, filepath):
        """保存数据到JSON文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✓ 数据已保存到: {filepath}")
    
    def close(self):
        """关闭浏览器"""
        self.driver.quit()


def main():
    scraper = PolymarketScraper()
    
    try:
        # 注意: 你需要先手动打开Polymarket页面并导航到目标页面
        # 然后运行此脚本,它会连接到已打开的浏览器
        
        # 或者直接访问URL
        url = input("请输入要抓取的页面URL(直接回车将使用当前激活页面): ").strip()
        if url:
            scraper.driver.get(url)
        
        # 抓取数据
        data = scraper.scrape_current_page()
        
        # 保存到指定路径
        output_path = "/Users/yanzhang/Downloads/prediction.json"
        scraper.save_to_json(data, output_path)
        
        print(f"\n抓取完成!")
        print(f"第一类项目: {len(data['type1_projects'])} 个")
        print(f"第二类项目: {len(data['type2_projects'])} 个")
        
    except Exception as e:
        print(f"\n× 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        scraper.close()


if __name__ == "__main__":
    main()