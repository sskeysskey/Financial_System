options.add_argument('--headless')  # 无界面模式
driver = webdriver.Chrome(service=service, options=options)
# ——————————————————————————————————————————————————————————————————————————————————————————
import json # 首先得import json
# 针对data_compare.py文件的配置文件优化
# 创建一个JSON文件，例如命名为 config.json
{
    "databases": [
        {
            "path": "/Users/yanzhang/Finance.db",
            "table": "Stocks",
            "names": ["NASDAQ", "S&P 500", "SSE Composite Index", "Shenzhen Index", "Nikkei 225", "S&P BSE SENSEX", "HANG SENG INDEX"]
        },
        {
            "path": "/Users/yanzhang/Finance.db",
            "table": "Crypto",
            "names": ["Bitcoin", "Ether", "Binance", "Bitcoin Cash", "Solana", "Monero", "Litecoin"]
        }
    ]
}

def load_config():
    """加载配置文件"""
    with open('config.json', 'r') as file:
        config = json.load(file)
    return config

def main():
    config = load_config()
    today = datetime.now()
    output = []

    for db_config in config['databases']:
        db_path = db_config['path']
        table_name = db_config['table']
        index_names = db_config['names']

        with create_connection(db_path) as conn:
            cursor = conn.cursor()

            #for index_name in index_names:
                # 假设对每个指数执行的操作保持不变，这里省略具体操作的代码

# ——————————————————————————————————————————————————————————————————————————————————————————
# ——————————————————————————————————————————————————————————————————————————————————————————