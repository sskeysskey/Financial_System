import json
import os
import sys
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

SECTOR_ALL_JSON = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
SECTOR_EMPTY_JSON = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_empty.json")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")

PRIMARY_TXT_DIR = os.path.join(USER_HOME, "Downloads")
FALLBACK_TXT_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")

MARKETCAP_FILENAME = 'marketcap_pe.txt'
SHARES_FILENAME = 'Shares.txt'

# 是否同时检查数据库 MNSPP 中 shares / marketcap 是否完整
CHECK_DATABASE = True

CATEGORIES = [
    'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
    'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
    'Communication_Services', 'Financial_Services', 'Healthcare'
]
INVALID_TOKENS = {'', 'N/A', '-', '--', 'None', 'null'}


def show_alert(message):
    try:
        if sys.platform == 'darwin':
            msg = str(message).replace('\\', '\\\\').replace('"', '\\"')
            code = f'display dialog "{msg}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', code], check=False)
        elif sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(message), "提示", 0)
    except Exception:
        pass


def fail(message):
    print(message)
    show_alert(message)
    sys.exit(1)


# ---------- 与抓取脚本一致的有效性规则 ----------
def parse_number(text):
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace(',', '')
    if s in INVALID_TOKENS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_record_line(line):
    line = line.strip()
    if not line or ':' not in line:
        return None, None
    sym, rest = line.split(':', 1)
    return sym.strip(), [p.strip() for p in rest.split(',')]


def is_valid_shares_fields(fields):
    """0 表示页面确认无股本（Yahoo 显示 --），也视为已检查过的有效记录"""
    if not fields or len(fields) < 2:
        return False
    v = parse_number(fields[0])
    return v is not None and v >= 0


def is_valid_marketcap_fields(fields):
    if not fields or len(fields) < 3:
        return False
    v = parse_number(fields[0])
    return v is not None and v > 0


def analyze_record_file(path, validator):
    """返回 (有效集合, 出现集合, 重复集合)"""
    counts, valid = {}, set()
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            sym, fields = parse_record_line(line)
            if not sym:
                continue
            counts[sym] = counts.get(sym, 0) + 1
            if validator(fields):
                valid.add(sym)
    dup = {s for s, c in counts.items() if c > 1}
    return valid - dup, set(counts), dup


def find_file_path_with_fallback(filename, primary_dir, fallback_dir):
    for d in (primary_dir, fallback_dir):
        p = os.path.join(d, filename)
        if os.path.exists(p):
            print(f"Found '{filename}': {p}")
            return p
    raise FileNotFoundError(
        f"File '{filename}' not found in '{primary_dir}' or '{fallback_dir}'.")


def check_database(symbols):
    """检查 MNSPP 中 shares / marketcap 是否存在且 > 0。数据库不可用时只警告不阻断"""
    problems = {}
    if not os.path.exists(DB_PATH):
        print(f"警告：数据库不存在，跳过数据库检查: {DB_PATH}")
        return problems
    try:
        conn = sqlite3.connect(Path(DB_PATH).as_uri() + "?mode=ro", uri=True, timeout=30)
        rows = conn.execute("SELECT upper(symbol), shares, marketcap FROM MNSPP").fetchall()
        conn.close()
    except sqlite3.Error as e:
        print(f"警告：读取数据库失败，跳过数据库检查: {e}")
        return problems

    db = {r[0]: (r[1], r[2]) for r in rows}
    for s in symbols:
        rec = db.get(s.upper())
        if rec is None:
            problems.setdefault(s, []).append("数据库无记录")
            continue
        mc = parse_number(rec[1])
        if not mc or mc <= 0:
            problems.setdefault(s, []).append("数据库marketcap为空")
    return problems


def save_json_atomic(path, data):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.tmp_', dir=d)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def backup_txt_files():
    """将 Downloads 下的 txt 移动到 backup（覆盖）"""
    moved, errors = [], []
    os.makedirs(FALLBACK_TXT_DIR, exist_ok=True)
    for filename in (MARKETCAP_FILENAME, SHARES_FILENAME):
        src = os.path.join(PRIMARY_TXT_DIR, filename)
        dst = os.path.join(FALLBACK_TXT_DIR, filename)
        if not os.path.exists(src):
            print(f"Downloads 中没有 {filename}，跳过备份")
            continue
        try:
            try:
                os.replace(src, dst)  # 同一磁盘：原子覆盖
            except OSError:
                shutil.copy2(src, dst)  # 跨磁盘：复制后删除
                os.remove(src)
            moved.append(filename)
            print(f"Successfully moved: {filename} -> {FALLBACK_TXT_DIR}")
        except Exception as e:
            errors.append(f"{filename}: {e}")
            print(f"Failed to move {filename}: {e}")
    return moved, errors


def main():
    # 1. 读取 JSON
    try:
        with open(SECTOR_ALL_JSON, encoding='utf-8') as f:
            sector_all = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        fail(f"Error: 无法读取 {SECTOR_ALL_JSON}: {e}")

    sector_empty = {}
    if os.path.exists(SECTOR_EMPTY_JSON):
        try:
            with open(SECTOR_EMPTY_JSON, encoding='utf-8') as f:
                sector_empty = json.load(f)
        except json.JSONDecodeError as e:
            fail(f"Error: {SECTOR_EMPTY_JSON} 内容损坏: {e}")

    # 2. 目标 symbol
    all_symbols = set()
    for cat in CATEGORIES:
        all_symbols.update(sector_all.get(cat, []))

    # 3. 读取 txt 并按内容校验
    try:
        mc_path = find_file_path_with_fallback(MARKETCAP_FILENAME, PRIMARY_TXT_DIR, FALLBACK_TXT_DIR)
        sh_path = find_file_path_with_fallback(SHARES_FILENAME, PRIMARY_TXT_DIR, FALLBACK_TXT_DIR)
        mc_valid, mc_present, mc_dup = analyze_record_file(mc_path, is_valid_marketcap_fields)
        sh_valid, sh_present, sh_dup = analyze_record_file(sh_path, is_valid_shares_fields)
    except FileNotFoundError as e:
        fail(f"Error: 数据文件缺失. {e}")
    except Exception as e:
        fail(f"读取数据文件时发生错误: {e}")

    reasons = {}

    def add(sym, why):
        reasons.setdefault(sym, []).append(why)

    for s in all_symbols:
        for name, valid, present, dup in (("marketcap_pe", mc_valid, mc_present, mc_dup),
                                          ("Shares", sh_valid, sh_present, sh_dup)):
            if s not in present:
                add(s, f"{name}缺失")
            elif s in dup:
                add(s, f"{name}重复")
            elif s not in valid:
                add(s, f"{name}数据无效")

    if CHECK_DATABASE:
        for s, rs in check_database(all_symbols).items():
            for r in rs:
                add(s, r)

    missing_all = set(reasons)

    # 4. 写回 Sectors_empty（目标板块按原分类填入，其他分组保持不变）
    for cat in CATEGORIES:
        sector_empty[cat] = sorted(set(sector_all.get(cat, [])) & missing_all)
    try:
        save_json_atomic(SECTOR_EMPTY_JSON, sector_empty)
    except OSError as e:
        fail(f"Error writing '{SECTOR_EMPTY_JSON}': {e}")

    # 5. 结果
    if missing_all:
        print("---- 问题明细 ----")
        for s in sorted(missing_all):
            print(f"{s}: {', '.join(reasons[s])}")
        preview = ", ".join(sorted(missing_all)[:15]) + (" ..." if len(missing_all) > 15 else "")
        show_alert(f"检测到 {len(missing_all)} 个缺失/异常符号，已写入：{SECTOR_EMPTY_JSON}\n{preview}")
    else:
        show_alert("未检测到缺失符号，无需更新。即将备份文件。")
        print("--- 开始备份文件 ---")
        moved, errors = backup_txt_files()
        if errors:
            show_alert("备份出错：\n" + "\n".join(errors))
        elif moved:
            show_alert(f"移动文件成功完成！({', '.join(moved)})")
        else:
            show_alert("Downloads 中没有需要备份的文件。")

    print("脚本执行完毕。")


if __name__ == "__main__":
    main()