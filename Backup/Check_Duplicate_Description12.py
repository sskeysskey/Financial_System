import json
# 文件路径
file_path = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'

# 读取JSON文件
with open(file_path, 'r', encoding='utf-8') as file:
    data = json.load(file)
# 存储description1和description2相同的symbol
matching_symbols = []
# 遍历股票
for stock in data['stocks']:
    if stock['description1'] == stock['description2'] and stock['description1'] and stock['description2']:
            matching_symbols.append(stock['symbol'])
# 遍历ETF
for etf in data['etfs']:
    if etf['description1'] == etf['description2'] and etf['description1'] and etf['description2']:
            matching_symbols.append(etf['symbol'])
            # 输出结果
print('Matching symbols:', matching_symbols)