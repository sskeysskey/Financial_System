from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import json

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--disable-gpu')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def fetch_data(url):
    driver = setup_driver()
    driver.get(url)
    results = []
    quote_links = driver.find_elements(By.XPATH, '//a[@data-test="quoteLink"]')
    
    for quote_link in quote_links:
        symbol = quote_link.text
        symbol_xpath = f'//fin-streamer[@data-symbol="{symbol}"]'
        try:
            market_cap_element = driver.find_element(By.XPATH, f'{symbol_xpath}[@data-field="marketCap"]')
            market_cap = float(market_cap_element.get_attribute('value'))
            if market_cap >= 200000000000:
                category = "Mega"
            elif 10000000000 <= market_cap < 200000000000:
                category = "Large"
            elif 2000000000 <= market_cap < 10000000000:
                category = "Middle"
            else:
                continue
            results.append((symbol, market_cap, category))
        except Exception as e:
            print(f"Error fetching data for symbol {symbol}: {str(e)}")

    driver.quit()
    return results

def update_json(data, sector):
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors.json', 'r+') as file:
        json_data = json.load(file)
        
        # 创建一个反向映射，用于查找符号当前所在的类别
        current_categories = {}
        for category in json_data[sector]:
            for symbol in json_data[sector][category]:
                current_categories[symbol] = category

        for symbol, _, category in data:
            current_category = current_categories.get(symbol)
            if current_category and current_category != category:
                # 如果符号已存在于其他类别中，则删除
                json_data[sector][current_category].remove(symbol)
                print(f"Removed '{symbol}' from {current_category} as it belongs to {category}.")
            
            if symbol not in json_data[sector][category]:
                # 添加到正确的类别
                json_data[sector][category].append(symbol)
                print(f"Added '{symbol}' to {category}.")

        file.seek(0)
        file.truncate()
        json.dump(json_data, file, indent=2)

def process_sector(url, sector):
    data = fetch_data(url)
    update_json(data, sector)

urls = [
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_basic-materials/?offset=0&count=100',
    'Basic_Materials'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_basic-materials/?count=100&offset=100',
    'Basic_Materials'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_communication-services/?offset=0&count=100',
    'Communication_Services'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_communication-services/?count=100&offset=100',
    'Communication_Services'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_consumer-cyclical/?offset=0&count=100',
    'Consumer_Cyclical'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_consumer-cyclical/?count=100&offset=100',
    'Consumer_Cyclical'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_consumer-cyclical/?count=100&offset=200',
    'Consumer_Cyclical'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_consumer-defensive/?offset=0&count=100',
    'Consumer_Defensive'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_consumer-defensive/?count=100&offset=100',
    'Consumer_Defensive'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_energy/?offset=0&count=100',
    'Energy'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_energy/?count=100&offset=100',
    'Energy'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_financial-services/?offset=0&count=100',
    'Financial_Services'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_financial-services/?count=100&offset=100',
    'Financial_Services'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_financial-services/?count=100&offset=200',
    'Financial_Services'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_healthcare/?offset=0&count=100',
    'Healthcare'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_healthcare/?count=100&offset=100',
    'Healthcare'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_healthcare/?count=100&offset=200',
    'Healthcare'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_industrials/?offset=0&count=100',
    'Industrials'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_industrials/?count=100&offset=100',
    'Industrials'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_industrials/?count=100&offset=200',
    'Industrials'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_real-estate/?offset=0&count=100',
    'Real_Estate'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_real-estate/?count=100&offset=100',
    'Real_Estate'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_technology/?offset=0&count=100',
    'Technology'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_technology/?count=100&offset=100',
    'Technology'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_technology/?count=100&offset=200',
    'Technology'),
    ('https://finance.yahoo.com/screener/predefined/sec-ind_sec-largest-equities_utilities/?offset=0&count=100',
    'Utilities'),
]

for url, sector in urls:
    process_sector(url, sector)