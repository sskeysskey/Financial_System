import json
import os

def load_keys_from_file(path):
    """
    读取 txt 文件，提取每行冒号前面的 symbol，返回一个 set
    """
    keys = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or ':' not in line:
                continue
            symbol = line.split(':', 1)[0].strip()
            keys.add(symbol)
    return keys

# --- 1. 读取 sector_all.json 和 sector_empty.json ---
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', encoding='utf-8') as f:
    sector_all = json.load(f)

with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json', encoding='utf-8') as f:
    sector_empty = json.load(f)

# --- 2. 定义要检查的分类 ---
categories = [
    'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
    'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
    'Communication_Services', 'Financial_Services', 'Healthcare'
]

# --- 3. 收集 sector_all 中所有目标分类的符号 ---
all_symbols = set()
for cat in categories:
    all_symbols.update(sector_all.get(cat, []))

# --- 4. 读取三个 txt 文件，分别得到已有的 symbol 集合 ---
marketcap_keys     = load_keys_from_file('/Users/yanzhang/Downloads/marketcap_pe.txt')
shares_keys        = load_keys_from_file('/Users/yanzhang/Downloads/Shares.txt')
symbol_names_keys  = load_keys_from_file('/Users/yanzhang/Downloads/symbol_names.txt')

# --- 5. 计算每个文件中缺失的 symbol ---
missing_marketcap    = all_symbols - marketcap_keys
missing_shares       = all_symbols - shares_keys
missing_symbol_names = all_symbols - symbol_names_keys

# --- 6. 取三者缺失的并集，作为“所有缺失”的 symbol ---
missing_all = missing_marketcap | missing_shares | missing_symbol_names

# --- 7. 将缺失符号按照原分类，填入 sector_empty ---
for cat in categories:
    original_syms = set(sector_all.get(cat, []))
    # 本分类里原本就有的符号中，哪些是缺失的
    miss_in_cat = original_syms & missing_all
    # 写入 sector_empty，去重并排序
    sector_empty[cat] = sorted(miss_in_cat)

# --- 8. 将更新后的 sector_empty.json 写回磁盘 ---
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json', 'w', encoding='utf-8') as f:
    json.dump(sector_empty, f, ensure_ascii=False, indent=2)

print("已将所有缺失符号按分类写入 sector_empty.json。")