#!/usr/bin/env python3
import os

OLD = '/Users/yanzhang/Documents'
NEW = '/Users/yanzhang/Coding'
EXTS = ('.py',)

for root, _, files in os.walk('.'):
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