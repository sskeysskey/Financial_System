import os
import glob
from collections import defaultdict, Counter

def parse_symbol(line: str) -> str | None:
    # 期望格式: "PLTR   : AMC : 2025-11-03"
    # 取第一个冒号前的部分作为 symbol
    if ":" not in line:
        return None
    head = line.split(":", 1)[0].strip()
    # 过滤空行或无效
    return head if head else None

def main():
    directory = "/Users/yanzhang/Coding/News"
    pattern = os.path.join(directory, "Earnings_Release_*.txt")
    files = glob.glob(pattern)

    if not files:
        print(f"未找到匹配文件：{pattern}")
        return

    symbol_counts = Counter()
    # 可选：记录来源文件与行号，便于定位重复
    symbol_sources = defaultdict(list)

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    sym = parse_symbol(line)
                    if not sym:
                        continue
                    symbol_counts[sym] += 1
                    symbol_sources[sym].append((os.path.basename(path), lineno))
        except UnicodeDecodeError:
            # 若不是 utf-8，可尝试其他编码
            with open(path, "r", encoding="latin-1") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    sym = parse_symbol(line)
                    if not sym:
                        continue
                    symbol_counts[sym] += 1
                    symbol_sources[sym].append((os.path.basename(path), lineno))

    duplicates = {s: c for s, c in symbol_counts.items() if c > 1}

    print(f"共解析 symbol 数量：{len(symbol_counts)}，总出现次数：{sum(symbol_counts.values())}")
    if duplicates:
        print("发现重复 symbol：")
        for sym, count in sorted(duplicates.items(), key=lambda x: (-x[1], x[0])):
            print(f"- {sym}: {count} 次")
            # 展示来源，便于定位
            for src_file, lineno in symbol_sources[sym]:
                print(f"  · {src_file}: 第 {lineno} 行")
    else:
        print("未发现重复 symbol")

if __name__ == "__main__":
    main()