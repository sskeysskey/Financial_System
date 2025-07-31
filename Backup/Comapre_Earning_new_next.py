#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

NEXT = "/Users/yanzhang/Documents/News/Earnings_Release_next.txt"
NEW  = "/Users/yanzhang/Documents/News/Earnings_Release_new.txt"
DIFF = "/Users/yanzhang/Documents/News/Earnings_Release_diff.txt"

def load_symbols(path):
    syms = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            parts = line.split(':', 1)
            if parts:
                sym = parts[0].strip()
                if sym:
                    syms.add(sym)
    return syms

def main():
    new_syms = load_symbols(NEW)

    kept_lines = []
    diff_syms  = []

    with open(NEXT, encoding='utf-8') as f:
        for line in f:
            parts = line.split(':', 1)
            sym = parts[0].strip()
            if sym in new_syms:
                diff_syms.append(sym)
            else:
                kept_lines.append(line.rstrip('\n'))

    # 写回过滤后的 NEXT
    with open(NEXT, 'w', encoding='utf-8') as f:
        for line in kept_lines:
            f.write(line + "\n")

    # 写 DIFF
    with open(DIFF, 'w', encoding='utf-8') as f:
        for sym in diff_syms:
            f.write(sym + "\n")

if __name__ == "__main__":
    main()