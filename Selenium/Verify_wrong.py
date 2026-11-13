# -*- coding: utf-8 -*-
"""
Verify_wrong.py
读取 wrong.txt，用 Yahoo Finance 重抓同一交易日数据做交叉校验。
不一致时按模式自动替换或逐条确认后替换。

用法:
  python3 Verify_wrong.py                    # 使用脚本内 MODE 配置
  python3 Verify_wrong.py --mode confirm     # 每条替换前确认
  python3 Verify_wrong.py --mode auto        # 自动替换（超过阈值的仍会询问）
  python3 Verify_wrong.py --dry-run          # 只比对、不写库、不改 wrong.txt
  python3 Verify_wrong.py --group Indices    # 只校验某个分组
  python3 Verify_wrong.py --unattended       # 无人值守：不询问，需确认的留在 wrong.txt
"""
import argparse
import csv
import datetime
import json
import os
import random
import shutil
import sqlite3
import sys
import time
import urllib.parse

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

import YF_Today as yf   # 复用 YF 的浏览器、解析、写库、分组逻辑

# ================= 配置区 =================
MODE = "confirm"                  # "confirm" 每条确认 | "auto" 自动替换
CONSISTENCY_TOLERANCE = 0.005     # |YF-MW|/MW <= 0.5% 视为一致
AUTO_REPLACE_MAX_DIFF = 0.75      # auto 模式下差异超过 25% 不自动替换，改为询问（防止两边都可能出错）
YF_WAIT_TIMEOUT = 10
YF_REQUEST_DELAY = (2.0, 4.0)
MAX_RETRIES = 2

NEWS_DIR = os.path.join(os.path.expanduser("~"), "Coding", "News")
WRONG_TXT_PATH = os.path.join(NEWS_DIR, "wrong.txt")
WRONG_ARCHIVE_DIR = os.path.join(NEWS_DIR, "wrong_archive")
AUDIT_CSV_PATH = os.path.join(NEWS_DIR, "verify_audit.csv")

RESOLVED = {"consistent", "replaced", "kept_mw"}   # 这些状态的条目从 wrong.txt 中移除
DB_PATH = yf.DB_PATH


# ================= 1. 读取 wrong.txt =================
def load_wrong_entries(path):
    if not os.path.exists(path):
        return []
    entries, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("{"):
                try:
                    d = json.loads(s)
                except json.JSONDecodeError:
                    continue
                e = {"group": d.get("group"), "symbol": d.get("symbol"), "date": d.get("date"),
                     "mw_price": d.get("mw_price")}
            else:                       # 旧格式：只有 symbol
                e = {"group": None, "symbol": s, "date": None, "mw_price": None}
            key = (e["group"], e["symbol"], e["date"])
            if e["symbol"] and key not in seen:
                seen.add(key)
                entries.append(e)
    return entries


# ================= 2. 读取数据库中的 MW 数据 =================
def resolve_group(conn, entry):
    """旧格式条目：在所有表中查找该 name 最近的日期，确定分组"""
    if entry["group"]:
        return entry
    best = None
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tables:
        try:
            r = conn.execute(f'SELECT date FROM "{t}" WHERE name=? ORDER BY date DESC LIMIT 1',
                             (entry["symbol"],)).fetchone()
        except sqlite3.Error:
            continue
        if r and (best is None or r[0] > best[1]):
            best = (t, r[0])
    if best:
        return dict(entry, group=best[0], date=entry["date"] or best[1])
    return entry


def get_mw_row(conn, group, symbol, date):
    if date:
        r = conn.execute(f'SELECT date, price FROM "{group}" WHERE name=? AND date=?',
                         (symbol, date)).fetchone()
    else:
        r = conn.execute(f'SELECT date, price FROM "{group}" WHERE name=? ORDER BY date DESC LIMIT 1',
                         (symbol,)).fetchone()
    if r and r[1] is not None:
        return r[0], float(r[1])
    return None


# ================= 3. Yahoo 抓取（复用 YF_Today） =================
def fetch_yf_rows(driver, symbol, alias_to_symbol):
    yf_sym = alias_to_symbol.get(symbol, symbol)
    driver.get(f"https://finance.yahoo.com/quote/{urllib.parse.quote(yf_sym)}/history/")
    WebDriverWait(driver, YF_WAIT_TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    rows = yf.extract_data_via_js(driver, symbol)   # (date, name, price, volume, open, high, low)
    return sorted(rows, key=lambda x: x[0], reverse=True)


def fetch_with_retry(state, symbol, alias_to_symbol):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_yf_rows(state["driver"], symbol, alias_to_symbol)
        except Exception as e:
            last_err = e
            if isinstance(e, WebDriverException) or yf.is_session_dead(e):
                try:
                    state["driver"].quit()
                except Exception:
                    pass
                state["driver"] = yf.build_driver()
            time.sleep(2 * attempt)
    raise last_err


# ================= 4. 写库 / 审计 / 备份 =================
_db_backed_up = False


def backup_db():
    global _db_backed_up
    if _db_backed_up or not os.path.exists(DB_PATH):
        return
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = f"{DB_PATH}.bak_verify_{ts}"
    shutil.copy2(DB_PATH, dst)
    _db_backed_up = True
    tqdm.write(f"💾 已备份数据库: {dst}")


def write_yf_row(group, row):
    return yf.insert_data_to_db(DB_PATH, group, [row], yf.get_table_type(group))


def audit(r, action, mode):
    os.makedirs(NEWS_DIR, exist_ok=True)
    new = not os.path.exists(AUDIT_CSV_PATH)
    with open(AUDIT_CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "mode", "group", "symbol", "date", "mw_price", "yf_price", "diff", "action"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), mode, r.get("group"),
                    r["symbol"], r.get("date"), r.get("mw_price"), r.get("yf_price"),
                    f"{r['diff']:+.4%}" if r.get("diff") is not None else "", action])


def rewrite_wrong(results, path):
    """把未解决的条目写回 path（默认 wrong.txt），写前先归档"""
    remaining = [r for r in results if r["status"] not in RESOLVED]
    if os.path.exists(path):
        os.makedirs(WRONG_ARCHIVE_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, os.path.join(WRONG_ARCHIVE_DIR, f"wrong_{ts}.txt"))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in remaining:
            f.write(json.dumps({"group": r.get("group"), "symbol": r["symbol"], "date": r.get("date"),
                                "mw_price": r.get("mw_price"), "status": r["status"],
                                "note": r.get("note", "")}, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return len(remaining)


# ================= 5. 交互确认 =================
def ask_user(r, state):
    if state.get("all"):
        return state["all"]
    print(f"\n[{r['group']}] {r['symbol']}  日期 {r['date']}")
    print(f"   MW: {r['mw_price']}   YF: {r['yf_price']}   差异: {r['diff']:+.2%}")
    while True:
        a = input("   替换为 YF？ [y]替换 [n]保留MW [A]后续全部替换 [N]后续全部保留 [q]退出: ").strip()
        if a == "y":
            return "replace"
        if a == "n":
            return "keep"
        if a == "A":
            state["all"] = "replace"
            return "replace"
        if a == "N":
            state["all"] = "keep"
            return "keep"
        if a == "q":
            raise KeyboardInterrupt


# ================= 6. 主流程 =================
def run(args):
    mode = args.mode or MODE
    wrong_path = args.file or WRONG_TXT_PATH
    interactive = sys.stdin.isatty() and not args.unattended

    entries = load_wrong_entries(wrong_path)
    if not entries:
        print("wrong.txt 为空或不存在，无需校验。", flush=True)
        return 0

    # --limit 只限制本次处理的条数；超出部分标记为 filtered，保留在文件中，不会丢失
    results = []
    for i, e in enumerate(entries):
        over = bool(args.limit) and i >= args.limit
        results.append(dict(e, status="filtered" if over else "pending"))

    n_run = sum(1 for r in results if r["status"] == "pending")
    print(f"共 {len(entries)} 条（本次处理 {n_run} 条）| 模式: {mode} | "
          f"{'DRY-RUN' if args.dry_run else '写库'} | {'交互' if interactive else '无人值守'}", flush=True)

    alias = yf.load_alias_mapping(yf.SYMBOL_MAPPING_PATH)

    # ---- 阶段1：读取 MW 数据 ----
    print("▶ 阶段 1/3：读取数据库中的 MW 数据 ...", flush=True)
    conn = sqlite3.connect(DB_PATH, timeout=60)
    try:
        for r in results:
            if r["status"] != "pending":
                continue
            full = resolve_group(conn, r)
            r.update(full)
            if not r.get("group"):
                r["status"], r["note"] = "unknown_group", "无法在数据库中找到该 symbol"
                continue
            if args.group and r["group"] != args.group:
                r["status"] = "filtered"
                continue
            mw = get_mw_row(conn, r["group"], r["symbol"], r.get("date"))
            if not mw:
                r["status"], r["note"] = "mw_missing", "数据库中没有对应的 MW 记录"
                continue
            r["date"], r["mw_price"] = mw
    finally:
        conn.close()

    pending = [r for r in results if r["status"] == "pending"]
    print(f"   可比对 {len(pending)} 条，跳过 {len(results) - len(pending)} 条", flush=True)

    # ---- 阶段2：Yahoo 抓取（按 symbol 去重） ----
    state, cache = {"driver": None}, {}
    try:
        if pending:
            syms = list(dict.fromkeys(r["symbol"] for r in pending))
            print(f"▶ 阶段 2/3：启动 Chrome，抓取 Yahoo（{len(syms)} 个 symbol，较慢，请耐心等待）",
                  flush=True)
            state["driver"] = yf.build_driver()
            print("   Chrome 已启动", flush=True)
            for k, sym in enumerate(syms, 1):
                t0 = time.time()
                print(f"   [{k}/{len(syms)}] {sym} ...", end="", flush=True)
                try:
                    cache[sym] = fetch_with_retry(state, sym, alias)
                    print(f" {len(cache[sym])} 行 ({time.time() - t0:.1f}s)", flush=True)
                except Exception as e:
                    cache[sym] = e
                    print(f" 失败: {str(e)[:80]}", flush=True)
                if k < len(syms):
                    time.sleep(random.uniform(*YF_REQUEST_DELAY))

        # ---- 比对 ----
        print("▶ 比对结果：", flush=True)
        for r in pending:
            sym = r["symbol"]
            rows = cache.get(sym)
            if isinstance(rows, Exception) or rows is None:
                r["status"], r["note"] = "yf_fail", str(rows)[:120]
                print(f"   {sym} {r['date']}  YF 抓取失败", flush=True)
                continue
            hit = next((x for x in rows if x[0] == r["date"]), None)
            if hit is None:
                latest = rows[0][0] if rows else None
                r["status"] = "yf_no_date"
                r["note"] = f"Yahoo 最新日期 {latest}，缺少 {r['date']}（可能尚未更新，下次再跑）"
                print(f"   {sym} {r['date']}  Yahoo 无此日期（最新 {latest}）", flush=True)
                continue
            yf_price = float(hit[2])
            mw_price = r["mw_price"]
            diff = (yf_price - mw_price) / abs(mw_price) if mw_price else float("inf")
            r.update(yf_price=yf_price, diff=diff, yf_row=hit)
            r["status"] = "consistent" if abs(diff) <= CONSISTENCY_TOLERANCE else "mismatch"
            tag = "一致" if r["status"] == "consistent" else "不一致"
            print(f"   {sym} {r['date']}  MW={mw_price}  YF={yf_price}  {diff:+.3%}  → {tag}", flush=True)
    finally:
        if state["driver"] is not None:
            try:
                state["driver"].quit()
            except Exception:
                pass

    # ---- 阶段3：决策与写库 ----
    print("▶ 阶段 3/3：决策与写库 ...", flush=True)
    for r in results:
        if r["status"] != "mismatch":
            continue
        if mode == "auto" and abs(r["diff"]) <= AUTO_REPLACE_MAX_DIFF:
            r["status"] = "auto_replace"
        else:
            r["status"] = "need_confirm"

    if interactive and not args.dry_run:
        state_ask = {}
        try:
            for r in results:
                if r["status"] != "need_confirm":
                    continue
                choice = ask_user(r, state_ask)
                r["status"] = "replace_confirmed" if choice == "replace" else "kept_mw_by_user"
        except KeyboardInterrupt:
            print("\n⛔ 用户退出确认，未决定的条目保留在 wrong.txt", flush=True)

    to_write = [r for r in results if r["status"] in ("auto_replace", "replace_confirmed")]
    for r in results:
        if r["status"] == "kept_mw_by_user":
            r["status"] = "kept_mw"

    if args.dry_run:
        for r in to_write:
            print(f"🔍 [DRY-RUN] 将替换 [{r['group']}] {r['symbol']} {r['date']}: "
                  f"{r['mw_price']} -> {r['yf_price']}", flush=True)
    else:
        if to_write:
            backup_db()
        for r in to_write:
            ok = write_yf_row(r["group"], r["yf_row"])
            if ok:
                r["status"] = "replaced"
                audit(r, "replaced", mode)
                print(f"✅ [{r['symbol']}] {r['date']} 已用 YF 替换: {r['mw_price']} -> {r['yf_price']}",
                      flush=True)
            else:
                r["status"], r["note"] = "write_fail", "写库失败"
        for r in results:
            if r["status"] == "consistent":
                audit(r, "consistent_keep_mw", mode)
            elif r["status"] == "kept_mw":
                audit(r, "kept_mw_by_user", mode)

    # ---- 汇总 ----
    from collections import Counter
    summary = Counter(r["status"] for r in results)
    print("\n📊 校验结果:", flush=True)
    for k, v in summary.most_common():
        print(f"   {k:<18} {v}", flush=True)
    for r in results:
        if r.get("note") and r["status"] not in RESOLVED:
            print(f"   - [{r['symbol']}] {r['status']}: {r['note']}", flush=True)

    if args.dry_run:
        print("DRY-RUN：未修改 wrong.txt 与数据库。", flush=True)
        return 0

    # ---- 更新 wrong.txt；退出码：0=全部解决，2=仍有剩余 ----
    left = rewrite_wrong(results, wrong_path)
    print(f"wrong.txt 已更新，剩余未解决 {left} 条（可稍后重跑）。", flush=True)
    return 0 if left == 0 else 2


def parse_args():
    p = argparse.ArgumentParser(description="用 Yahoo 交叉校验 wrong.txt 中的 MarketWatch 数据")
    p.add_argument("--mode", choices=["confirm", "auto"], help="覆盖脚本内 MODE")
    p.add_argument("--dry-run", action="store_true", help="只比对，不写库、不改 wrong.txt")
    p.add_argument("--unattended", action="store_true", help="无人值守：不询问")
    p.add_argument("--group", help="只校验指定分组")
    p.add_argument("--file", help="指定 wrong 文件路径")
    p.add_argument("--limit", type=int, help="只处理前 N 条（测试用）")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))