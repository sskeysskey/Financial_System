#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def load_symbols(path):
    """
    从给定的 txt 文件中读取 symbol 列表。
    假设每行格式为 'SYMBOL: 后续内容'，空白行会被忽略。
    """
    symbols = set()
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            symbol = line.split(':', 1)[0].strip()
            if symbol:
                symbols.add(symbol)
    return symbols

def main():
    # ——— 在这里直接写死两个文件的路径 ———
    file_a = '/Users/yanzhang/Documents/News/backup/marketcap_pe.txt'
    file_b = '/Users/yanzhang/Downloads/marketcap_pe.txt'

    syms_a = load_symbols(file_a)
    syms_b = load_symbols(file_b)

    only_in_a = syms_a - syms_b
    only_in_b = syms_b - syms_a

    print(f"在 {file_a} 中出现，但不在 {file_b} 中的 symbols ({len(only_in_a)})：")
    for s in sorted(only_in_a):
        print(s)

    print(f"\n在 {file_b} 中出现，但不在 {file_a} 中的 symbols ({len(only_in_b)})：")
    for s in sorted(only_in_b):
        print(s)

if __name__ == '__main__':
    main()