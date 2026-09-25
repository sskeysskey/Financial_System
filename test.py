from pathlib import Path
from datetime import date

# 定义文件和对应的起止日期
file_configs = [
    {
        "path": Path("/Users/yanzhang/Coding/News/Earnings_Release_new.txt"),
        "start": date(2026,9,21),
        "end": date(2026,9,26)
    },
    {
        "path": Path("/Users/yanzhang/Coding/News/Earnings_Release_next.txt"),
        "start": date(2026,9,28),
        "end": date(2026,10,3)
    },
    {
        "path": Path("/Users/yanzhang/Coding/News/Earnings_Release_third.txt"),
        "start": date(2026,10,5),
        "end": date(2026,10,10)
    },
    {
        "path": Path("/Users/yanzhang/Coding/News/Earnings_Release_fourth.txt"),
        "start": date(2026,10,12),
        "end": date(2026,10,17)
    },
    {
        "path": Path("/Users/yanzhang/Coding/News/Earnings_Release_fifth.txt"),
        "start": date(2026,10,19),
        "end": date(2026,10,24)
    },
]

def parse_date(d_str: str) -> date:
    y,m,d = map(int, d_str.strip().split("-"))
    return date(y,m,d)

bad_records = []

for cfg in file_configs:
    fp = cfg["path"]
    if not fp.exists():
        print(f"⚠️ 文件不存在：{fp}")
        continue
    with open(fp, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(":")]
        if len(parts) <3:
            bad_records.append({
                "file": fp.name,
                "line": line_no,
                "symbol": None,
                "date_str": None,
                "err": f"格式异常，无法拆分: {raw}"
            })
            continue
        sym, broker, dt_str = parts[0], parts[1], parts[2]
        try:
            dt = parse_date(dt_str)
        except Exception as e:
            bad_records.append({
                "file": fp.name,
                "line": line_no,
                "symbol": sym,
                "date_str": dt_str,
                "err": f"日期解析失败: {e}"
            })
            continue
        # 判断日期是否在区间内
        if not (cfg["start"] <= dt <= cfg["end"]):
            bad_records.append({
                "file": fp.name,
                "line": line_no,
                "symbol": sym,
                "date_str": dt_str,
                "err": f"日期不在本文件区间 [{cfg['start']} ~ {cfg['end']}]"
            })

print("===== 校验结果 =====")
if not bad_records:
    print("✅ 所有记录校验通过，没有发现日期不匹配")
else:
    for item in bad_records:
        print(f"[{item['file']}] 行{item['line']} | Symbol:{item['symbol']} | Date:{item['date_str']} | {item['err']}")
