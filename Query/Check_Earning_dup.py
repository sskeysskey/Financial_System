import os
import glob
import subprocess
from collections import defaultdict, Counter

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def parse_symbol(line: str) -> str | None:
    if ":" not in line:
        return None
    head = line.split(":", 1)[0].strip()
    return head if head else None

def main():
    directory = "/Users/yanzhang/Coding/News"
    pattern = os.path.join(directory, "Earnings_Release_*.txt")
    output_path = os.path.join(directory, "duplication.txt")

    files = glob.glob(pattern)

    # 若无匹配文件：仅提示“无重复内容”，且不生成文件
    if not files:
        show_alert("无earning_release_*.txt文件")
        return

    symbol_counts = Counter()
    symbol_sources = defaultdict(list)

    def process_file(path, encoding):
        with open(path, "r", encoding=encoding) as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                sym = parse_symbol(line)
                if not sym:
                    continue
                symbol_counts[sym] += 1
                symbol_sources[sym].append((os.path.basename(path), lineno))

    for path in files:
        try:
            process_file(path, "utf-8")
        except UnicodeDecodeError:
            process_file(path, "latin-1")

    duplicates = {s: c for s, c in symbol_counts.items() if c > 1}

    # 无重复：仅弹窗，不落地文件
    if not duplicates:
        show_alert("无重复内容")
        return

    # 有重复：生成duplication.txt并弹窗
    lines_out = []
    lines_out.append(f"共解析 symbol 数量：{len(symbol_counts)}，总出现次数：{sum(symbol_counts.values())}")
    lines_out.append("发现重复 symbol：")
    for sym, count in sorted(duplicates.items(), key=lambda x: (-x[1], x[0])):
        lines_out.append(f"- {sym}: {count} 次")
        for src_file, lineno in symbol_sources[sym]:
            lines_out.append(f"  · {src_file}: 第 {lineno} 行")

    # 将结果写入文件
    with open(output_path, "w", encoding="utf-8") as fw:
        fw.write("\n".join(lines_out) + "\n")

    show_alert("有重复内容生成")

if __name__ == "__main__":
    main()