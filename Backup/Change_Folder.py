#!/usr/bin/env python3
import os

OLD = '/Users/yanzhang/Coding'
NEW = '/Users/yanzhang/Coding'
EXTS = ('.py',)

# ① 将这里的 '.' 改为目标搜索目录
SEARCH_DIR = '/Users/yanzhang/Coding'

for root, _, files in os.walk(SEARCH_DIR):
    for fname in files:
        if not fname.endswith(EXTS):
            continue
        full = os.path.join(root, fname)
        with open(full, 'r', encoding='utf-8') as f:
            text = f.read()
        if OLD in text:
            new_text = text.replace(OLD, NEW)
            with open(full, 'w', encoding='utf-8') as f:
                f.write(new_text)
            print(f'→ 替换：{full}')