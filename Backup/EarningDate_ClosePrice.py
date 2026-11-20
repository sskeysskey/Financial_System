import csv
import datetime
import json
import os
import sqlite3

# ================= 配置 =================
USER_HOME = os.path.expanduser("~")
CODING_DIR = os.path.join(USER_HOME, "Coding")
CONFIG_DIR = os.path.join(CODING_DIR, "Financial_System", "Modules")
DB_FILE = os.path.join(CODING_DIR, "Database", "Finance.db")
SECTORS_JSON_FILE = os.path.join(CONFIG_DIR, "Sectors_All.json")
OUTPUT_CSV = os.path.join(USER_HOME, "earning_price_check.csv")

TARGET_SECTORS = {
    "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
    "Industrials", "Real_Estate", "Technology", "Utilities"
}

# 检查截止日期 (与主程序一致: 只看 <= 该日期的财报)。留空则使用昨天(自然日)
BASE_DATE = "2026-11-17"


def resolve_base_date():
    if BASE_DATE:
        return BASE_DATE
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def load_sector_map(path, target_sectors):
    """返回 {symbol: sector}，与主程序 load_all_symbols 的规则一致 (后出现的板块覆盖前面的)。"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    sector_map = {}
    for sector, symbols in data.items():
        if sector in target_sectors:
            for sym in symbols:
                sector_map[sym] = sector
    return sector_map


def check_symbol(cursor, sector, symbol, base_date):
    """
    返回 None: 没有财报记录
    返回 {"error": ...}: 查询出错
    否则返回检查结果
    """
    try:
        cursor.execute(
            "SELECT DISTINCT date FROM Earning WHERE name = ? AND date <= ? ORDER BY date ASC",
            (symbol, base_date)
        )
        er_dates = [r[0] for r in cursor.fetchall()]
        if not er_dates:
            return None

        placeholders = ",".join("?" * len(er_dates))
        cursor.execute(
            f'SELECT date FROM "{sector}" WHERE name = ? AND date IN ({placeholders}) '
            f'AND price IS NOT NULL AND price > 0',
            (symbol, *er_dates)
        )
        have = {r[0] for r in cursor.fetchall()}
    except sqlite3.OperationalError as e:
        return {"error": str(e)}

    missing = [d for d in er_dates if d not in have]
    latest = er_dates[-1]
    return {
        "total": len(er_dates),
        "missing": missing,
        "latest": latest,
        "latest_missing": latest not in have,
    }


def is_weekend(date_str):
    try:
        return datetime.date.fromisoformat(date_str).weekday() >= 5
    except ValueError:
        return False


def main():
    base_date = resolve_base_date()
    sector_map = load_sector_map(SECTORS_JSON_FILE, TARGET_SECTORS)
    print(f"检查截止日期: {base_date}")
    print(f"共 {len(sector_map)} 个 symbol 待检查\n")

    flagged = []
    errors = []
    no_earning = 0
    ok_count = 0

    conn = sqlite3.connect(DB_FILE, timeout=60.0)
    try:
        cursor = conn.cursor()
        for sym in sorted(sector_map):
            sector = sector_map[sym]
            info = check_symbol(cursor, sector, sym, base_date)

            if info is None:
                no_earning += 1
                continue
            if "error" in info:
                errors.append((sym, sector, info["error"]))
                continue
            if not info["missing"]:
                ok_count += 1
                continue

            flagged.append({
                "symbol": sym,
                "sector": sector,
                "latest_earning": info["latest"],
                "latest_missing": "是" if info["latest_missing"] else "否",
                "total_earning": info["total"],
                "missing_count": len(info["missing"]),
                "missing_dates": ", ".join(info["missing"]),
                "weekend_missing": sum(1 for d in info["missing"] if is_weekend(d)),
            })
    finally:
        conn.close()

    # 排序: 最新财报缺价的优先，其次缺失数量多的
    flagged.sort(key=lambda r: (r["latest_missing"] != "是", -r["missing_count"], r["symbol"]))

    # 输出控制台
    critical = [r for r in flagged if r["latest_missing"] == "是"]
    minor = [r for r in flagged if r["latest_missing"] == "否"]

    print("=" * 70)
    print(f"【关键】最新财报日无收盘价 (主程序会跳过): {len(critical)} 个")
    print("=" * 70)
    for r in critical:
        print(f"{r['symbol']:<8} {r['sector']:<22} 最新财报 {r['latest_earning']}  "
              f"缺失 {r['missing_count']}/{r['total_earning']} 个财报日: {r['missing_dates']}")

    print()
    print("=" * 70)
    print(f"【次要】仅旧财报日缺价: {len(minor)} 个")
    print("=" * 70)
    for r in minor:
        print(f"{r['symbol']:<8} {r['sector']:<22} 缺失 {r['missing_count']}/{r['total_earning']}: {r['missing_dates']}")

    print()
    print(f"汇总: 有财报且全部有价 {ok_count} 个 | 无财报记录 {no_earning} 个 | "
          f"关键问题 {len(critical)} 个 | 次要问题 {len(minor)} 个 | 查询出错 {len(errors)} 个")
    for sym, sector, err in errors:
        print(f"  [出错] {sym} ({sector}): {err}")

    # 写 CSV
    if flagged:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=list(flagged[0].keys()))
            writer.writeheader()
            writer.writerows(flagged)
        print(f"\n结果已写入: {OUTPUT_CSV}")


if __name__ == '__main__':
    main()