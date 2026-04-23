import os
from playwright.sync_api import sync_playwright

FILE_NAME = "/Users/yanzhang/Coding/News/earning_polymarket.txt"

def load_existing_data(filename):
    """读取本地已有的数据，返回一个字典 { 'MBWM': '93%', ... }"""
    data = {}
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 假设文件格式为: MBWM: 93%
                if ':' in line:
                    ticker, percent = line.split(':', 1)
                    data[ticker.strip()] = percent.strip()
    return data

def save_data(filename, data):
    """将合并后的数据保存回 txt 文件"""
    with open(filename, 'w', encoding='utf-8') as f:
        for ticker, percent in data.items():
            f.write(f"{ticker}: {percent}\n")
    print(f"数据已成功保存至 {filename}，共 {len(data)} 条记录。")

def scrape_polymarket_earnings():
    # 1. 加载本地已有数据
    earnings_data = load_existing_data(FILE_NAME)
    
    with sync_playwright() as p:
        # 启动浏览器 (headless=True 表示无头模式，不弹出浏览器窗口)
        browser = p.chromium.launch(headless=True)
        # 伪装一下 User-Agent，防止被 Cloudflare 拦截
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        print("正在访问 Polymarket 页面...")
        # 移除 networkidle，改为 domcontentloaded，并增加整体超时时间
        page.goto("https://polymarket.com/earnings", wait_until="domcontentloaded", timeout=60000)
        
        # 显式等待包含股票数据的容器出现
        page.wait_for_selector("div.group.cursor-pointer", timeout=30000)
        
        # 获取所有符合条件的卡片容器
        cards = page.locator("div.group.cursor-pointer").all()
        print(f"页面上找到了 {len(cards)} 个股票数据组，正在提取...")
        
        for card in cards:
            try:
                # 提取股票代码 (h4 标签)
                ticker_element = card.locator("h4")
                if ticker_element.count() == 0:
                    continue
                ticker = ticker_element.first.inner_text().strip()
                
                # 提取百分比 (span 标签，包含 font-medium)
                percent_element = card.locator("span.font-medium")
                if percent_element.count() == 0:
                    continue
                # inner_text() 会自动忽略 HTML 注释和 DevTools 的 == $0 等调试字符
                percent = percent_element.first.inner_text().strip()
                
                if ticker and percent:
                    # 更新字典（同名覆盖，异名新增）
                    earnings_data[ticker] = percent
                    print(f"抓取到: {ticker} -> {percent}")
                    
            except Exception as e:
                print(f"解析某个卡片时出错: {e}")
                continue
                
        browser.close()
        
    # 3. 将更新后的数据保存到文件
    save_data(FILE_NAME, earnings_data)

if __name__ == "__main__":
    scrape_polymarket_earnings()