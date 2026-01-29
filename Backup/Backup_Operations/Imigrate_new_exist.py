import os
import json
from datetime import datetime

# 文件路径配置
files = {
    'ETFs': '/Users/yanzhang/Coding/News/backup/ETFs.txt',
}

new_files = {
    'ETFs': '/Users/yanzhang/Coding/News/ETFs_new.txt',
    '10Y_newhigh': '/Users/yanzhang/Coding/News/10Y_newhigh_stock.txt',
}

# 新的 10Y_newhigh JSON 目标文件路径
TENY_JSON = '/Users/yanzhang/Coding/Financial_System/Modules/10Y_newhigh.json'

# 获取当前星期几，0是周一，6是周日
current_day = datetime.now().weekday()

def process_etf_file(new_file, existing_file):
    if not os.path.exists(new_file):
        return
    # 读取现有文件的所有内容（不使用 readlines 以避免自动添加换行符）
    with open(existing_file, 'r') as f:
        existing_content = f.read()
    
    # 获取现有的符号集
    existing_symbols = {line.split(':', 1)[0].strip() 
                       for line in existing_content.split('\n') if line.strip()}
    
    # 读取新文件的所有内容
    with open(new_file, 'r') as f:
        new_content = f.read()
    
    # 处理新内容
    new_lines_to_add = []
    for line in new_content.split('\n'):
        if not line.strip():
            continue
        symbol = line.split(':', 1)[0].strip()
        if symbol not in existing_symbols:
            new_lines_to_add.append(line)
            existing_symbols.add(symbol)
    
    # 写入合并后的内容
    if new_lines_to_add:
        with open(existing_file, 'w') as f:
            if existing_content and existing_content.strip():
                # 如果现有内容非空，添加新内容时需要换行符分隔
                content_to_write = existing_content + '\n' + '\n'.join(new_lines_to_add)
            else:
                # 如果现有内容为空，直接写入新内容
                content_to_write = '\n'.join(new_lines_to_add)
            
            # 写入内容，确保末尾没有换行符
            f.write(content_to_write.rstrip('\n'))
    
    os.remove(new_file)

def process_10y_json(new_file, json_file):
    """
    读取 new_file，提取 Symbol 和 Price。
    将其与 json_file 中的 "stocks" 部分合并：
      - 不存在则新增
      - 存在则当且仅当 new_price > old_price 时更新
    最终将更新后的 "stocks" 和原有的 "others" 一起写回 JSON 文件。
    处理完删除 new_file。
    """
    if not os.path.exists(new_file):
        return
    # 确保目标目录存在
    target_dir = os.path.dirname(json_file)
    if target_dir and not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    
    # 初始化用于存储 "stocks" 和 "others" 的变量
    stock_data = {}
    other_data = []
    full_json_data = {}

    if os.path.exists(json_file):
        try:
            with open(json_file, 'r') as jf:
                content = jf.read().strip()
                if content:
                    # 加载整个JSON对象
                    full_json_data = json.loads(content)
                    if not isinstance(full_json_data, dict):
                        print("警告：JSON 顶层结构不是字典，将重置。")
                        full_json_data = {}
                    # 提取 "stocks" 数据
                    if 'stocks' in full_json_data and isinstance(full_json_data['stocks'], list) and full_json_data['stocks']:
                        for item in full_json_data['stocks']:
                            if isinstance(item, dict):
                                stock_data.update({str(k): str(v) for k, v in item.items()})
                    # 提取 "others" 数据
                    if 'others' in full_json_data and isinstance(full_json_data['others'], list):
                        other_data = full_json_data['others']
        except Exception as e:
            print(f"警告：读取或解析 JSON 时出错，将以空数据结构继续。错误：{e}")
            stock_data = {}
            other_data = []

    updates = 0
    inserts = 0
    with open(new_file, 'r') as fin:
        for raw in fin:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 4:
                print(f"跳过异常行（少于4段）：{line}")
                continue
            sector, symbol, change, price_str = parts[:4]
            price_clean = price_str.replace(',', '')
            try:
                new_price = float(price_clean)
            except ValueError:
                print(f"跳过价格不可解析的行：{line}")
                continue
            sym = symbol.strip()
            if not sym:
                print(f"跳过空 symbol 的行：{line}")
                continue
            
            if sym not in stock_data:
                stock_data[sym] = f"{new_price}"
                inserts += 1
            else:
                old_str = str(stock_data[sym]).replace(',', '')
                try:
                    old_price = float(old_str)
                except ValueError:
                    old_price = float('-inf')
                
                if new_price > old_price:
                    stock_data[sym] = f"{new_price}"
                    updates += 1

    # 重构要写回的完整JSON结构
    final_json_to_write = {
        "stocks": [stock_data],
        "others": other_data
    }
    
    try:
        with open(json_file, 'w') as jf:
            json.dump(final_json_to_write, jf, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"错误：写入 JSON 失败：{e}")
        return

    try:
        os.remove(new_file)
    except Exception as e:
        print(f"警告：删除 new 文件失败：{e}")
        return
    print(f"10Y_newhigh JSON 处理完成：新增 {inserts} 条，更新 {updates} 条。")

if __name__ == "__main__":
    # 周二到周天允许运行
    if 1 <= current_day <= 6:
        print("开始执行 ETF 模式逻辑...")
        process_etf_file(new_files['ETFs'], files['ETFs'])
        process_10y_json(new_files['10Y_newhigh'], TENY_JSON)
    else:
        print("Not right date. ETF 模式只在周二到周天运行。")
