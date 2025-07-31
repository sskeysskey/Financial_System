import json
from collections import OrderedDict

# 读取 JSON 数据
def read_json_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        data = json.load(file, object_pairs_hook=OrderedDict)
    return data

# 读取并解析 TXT 数据
def parse_txt_file(filename):
    symbol_to_name = {}
    with open(filename, 'r', encoding='utf-8') as file:
        for line in file:
            if ':' in line:
                symbol, name = line.strip().split(':')
                symbol_to_name[symbol.strip()] = name.strip()
    return symbol_to_name

# 更新 JSON 数据
def update_json_data(json_data, symbol_to_name):
    # for category in ['stocks', 'etfs']:
    for category in ['etfs']:
        for item in json_data[category]:
            symbol = item['symbol']
            if symbol in symbol_to_name:
                item['name'] = symbol_to_name[symbol]
            # 确保字段排序
            ordered_item = OrderedDict([
                ('symbol', item['symbol']),
                ('name', item.get('name', '')),
                ('tag', item['tag']),
                ('description1', item['description1']),
                ('description2', item['description2'])
            ])
            json_data[category][json_data[category].index(item)] = ordered_item

# 写入 JSON 数据到文件
def write_json_file(data, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def main():
    json_data = read_json_file('/Users/yanzhang/Coding/Financial_System/Modules/description.json')
    # symbol_to_name = parse_txt_file('/Users/yanzhang/Coding/News/backup/symbol_names.txt')
    symbol_to_name = parse_txt_file('/Users/yanzhang/Coding/News/backup/ETFs.txt')
    update_json_data(json_data, symbol_to_name)
    write_json_file(json_data, '/Users/yanzhang/Coding/Financial_System/Modules/description_new.json')

if __name__ == '__main__':
    main()