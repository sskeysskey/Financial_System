#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import os

# ========== 配置区域 ==========
# 白名单关键词：标签中包含任一白名单关键词，则符号候选。
keywords = ["半导体", "赋能人工智能", "芯片", "AI"]

# 黑名单关键词：标签中包含任一黑名单关键词，则直接排除该符号。
blacklist = ["传统半导体", "模拟芯片"]

# 输入文件路径（根据实际情况修改）
next_txt_path  = "/Users/yanzhang/Coding/News/Earnings_Release_next.txt"
desc_json_path = "/Users/yanzhang/Coding/Financial_System/Modules/description.json"
# =============================

def load_description(path):
    """读取 description.json，返回 symbol->tags 的映射字典"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    symbol_tags = {}
    for section in ("stocks", "etfs"):
        for item in data.get(section, []):
            sym = item.get("symbol")
            tags = item.get("tag", [])
            if sym:
                symbol_tags[sym] = tags
    return symbol_tags

def parse_next_symbols(path):
    """读取 next.txt，提取每行开头的 symbol"""
    symbols = []
    pat = re.compile(r'^([A-Za-z0-9]+)')
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = pat.match(line)
            if m:
                symbols.append(m.group(1))
    return symbols

def match_symbols(symbols, symbol_tags, keywords, blacklist):
    """
    返回一个 dict：{ symbol: [其所有 tags 列表] }，满足：
      1. 至少有一个标签部分匹配 白名单关键词
      2. 且无任何标签部分匹配 黑名单关键词
    """
    kw_lower = [kw.lower() for kw in keywords]
    bl_lower = [bl.lower() for bl in blacklist]

    matched = {}
    for sym in symbols:
        tags = symbol_tags.get(sym, [])
        # 跳过所有黑名单标签
        if any(any(bl in tag.lower() for bl in bl_lower) for tag in tags):
            continue

        # 若有标签匹配白名单，则保留
        if any(any(kw in tag.lower() for kw in kw_lower) for tag in tags):
            matched[sym] = tags

    return matched

def main():
    # 检查文件存在
    for path in (next_txt_path, desc_json_path):
        if not os.path.exists(path):
            print(f"Error: 找不到文件 {path}")
            return

    symbol_tags = load_description(desc_json_path)
    symbols     = parse_next_symbols(next_txt_path)
    matched      = match_symbols(symbols, symbol_tags, keywords, blacklist)

    if not matched:
        print("没有符号满足条件。")
        return

    print("满足条件的 symbols 及其 tags：")
    for s, tags in matched.items():
        print(f"  - {s}: [{', '.join(tags)}]")

if __name__ == "__main__":
    main()