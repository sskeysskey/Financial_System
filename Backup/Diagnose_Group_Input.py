"""
分组输入来源诊断（只读，不修改任何文件）
目的: 找出 history[分组][D] 与 Sectors_panel[分组] 不一致的分组、具体 symbol，并定位写入它的代码
"""
import os
import re
import sys
import json
import glob
import sqlite3
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import Analyse_Earning_Support as AES

# ================= 配置 =================
DIAG_DATE = "2026-10-16"
FOCUS_SYMBOLS = ["ADBE", "APTV", "ARW", "BEN", "BG", "DD", "DHI", "FCX", "IVZ", "J",
                 "PI", "SAN", "SWK", "TECK", "TKR", "TROW"]
SCAN_DIRS = [
    os.path.join(AES.BASE_CODING_DIR, "Financial_System", "Query"),
    os.path.join(AES.BASE_CODING_DIR, "Financial_System", "Operations"),
]
SKIP_FILES = {"Diagnose_Group_Input.py", "Verify_Support_Consistency.py"}
MERGE_PATTERNS = [r"set\(\s*existing", r"\|\s*set\(", r"\.union\(", r"combined_symbols", r"\|=\s*set\("]
MAX_LIST = 80


def _load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def norm_map(items, known):
    """{规范化 symbol: 原始条目}"""
    if isinstance(items, dict):
        items = list(items.keys())
    out = {}
    for it in items or []:
        s = AES.normalize_symbol(it, known)
        if s:
            out.setdefault(s, it)
    return out


def prev_key(node, D):
    ks = [k for k in node if isinstance(k, str) and len(k) == 10 and k < D]
    return max(ks) if ks else None


def _mtime(p):
    try:
        return datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "N/A"


def main():
    D = DIAG_DATE
    eh = _load(AES.EARNING_HISTORY_PATH)
    panel = _load(AES.SECTORS_PANEL_PATH)
    sa = _load(AES.SECTORS_ALL_PATH)

    conn = sqlite3.connect(f"file:{AES.DB_PATH}?mode=ro", uri=True)
    try:
        s2t, s_latest, _ = AES.build_symbol_index(conn.cursor(), sa, print)
    finally:
        conn.close()
    known = set(s2t)

    print("=" * 100)
    print(f"分组输入诊断  D={D}")
    print("=" * 100)
    print(f"Sectors_panel.json   修改时间: {_mtime(AES.SECTORS_PANEL_PATH)}")
    print(f"Earning_History.json 修改时间: {_mtime(AES.EARNING_HISTORY_PATH)}")
    snaps = sorted(glob.glob(os.path.join(AES.RUN_SNAPSHOT_DIR, "support_run_*.json")))
    print(f"支撑脚本快照: {len(snaps)} 个" + (f"，最新 {os.path.basename(snaps[-1])}" if snaps else "（从下次实盘开始才有）"))

    groups = AES.TARGET_GROUPS
    P = {g: norm_map(panel.get(g, {}), known) for g in groups if g in panel}
    H, HP, PK = {}, {}, {}
    for g in groups:
        node = eh.get(g, {}) or {}
        H[g] = norm_map(node.get(D), known)
        PK[g] = prev_key(node, D)
        HP[g] = norm_map(node.get(PK[g]), known) if PK[g] else {}

    print(f"\n{'分组':<16}{'panel':>7}{'hist@D':>8}{'H有P无':>8}{'P有H无':>8}{'H多出中属于前一日残留':>22}  前一日key")
    diff_groups = []
    for g in groups:
        p = P.get(g)
        hx = sorted(set(H[g]) - set(p or {}))
        px = sorted(set(p or {}) - set(H[g]))
        carry = [s for s in hx if s in HP[g]]
        print(f"{g:<16}{('无' if p is None else len(p)):>7}{len(H[g]):>8}{len(hx):>8}{len(px):>8}"
              f"{f'{len(carry)}/{len(hx)}':>22}  {PK[g]}")
        if hx or px:
            diff_groups.append(g)

    for g in diff_groups:
        p = P.get(g) or {}
        hx = sorted(set(H[g]) - set(p))
        px = sorted(set(p) - set(H[g]))
        print(f"\n---- [{g}] ----")
        if hx:
            print(f"  history@D 有、panel 无 ({len(hx)}):")
            for s in hx[:MAX_LIST]:
                other_p = [x for x in P if x != g and s in P[x]]
                tag = "前一日也在" if s in HP[g] else "前一日不在"
                print(f"    {s:<8} 原始={H[g][s]!r:<14} {tag:<6} DB最新={s_latest.get(s)}  panel其他分组={other_p or '无'}")
        if px:
            print(f"  panel 有、history@D 无 ({len(px)}): {px[:MAX_LIST]}")

    allP = set().union(*P.values()) if P else set()
    allH = set().union(*H.values())
    net = sorted(allH - allP)
    print(f"\n跨所有目标分组: history@D 独有 {len(net)} 个（= 回测比实盘多出的输入）: {net[:MAX_LIST]}")

    if FOCUS_SYMBOLS:
        print("\n---- 重点 symbol 分组归属 ----")
        for s in FOCUS_SYMBOLS:
            pg = [g for g in P if s in P[g]]
            hg = [f"{g}({H[g][s]})" for g in groups if s in H[g]]
            hpg = [f"{g}@{PK[g]}" for g in groups if s in HP[g]]
            print(f"  {s:<6} panel={pg or '无'} | history@D={hg or '无'} | history@前一日={hpg or '无'}")

    print("\n---- 代码扫描：引用差异分组的位置 ----")
    refs = defaultdict(lambda: defaultdict(list))
    merges = []
    for d in SCAN_DIRS:
        for root, _, files in os.walk(d):
            for fn in files:
                if not fn.endswith(".py") or fn in SKIP_FILES:
                    continue
                path = os.path.join(root, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                except Exception:
                    continue
                for i, line in enumerate(lines, 1):
                    for g in diff_groups:
                        if re.search(r"['\"]%s['\"]" % re.escape(g), line):
                            refs[g][path].append((i, line.strip()))
                    if any(re.search(p, line) for p in MERGE_PATTERNS):
                        merges.append((path, i, line.strip()))
    for g in diff_groups:
        files = refs.get(g, {})
        print(f"\n  [{g}] 被 {len(files)} 个文件引用" + ("  ⚠️ 多个文件引用，检查是否有多个脚本都在写它" if len(files) > 1 else ""))
        for path, items in files.items():
            print(f"    {path}")
            for i, l in items[:15]:
                print(f"      L{i}: {l[:150]}")
    print("\n  并集合并写法（会导致同一日期 key 跨多次运行累积）:")
    for path, i, l in merges:
        print(f"    {path}:L{i}: {l[:150]}")
    if not merges:
        print("    未发现")

    print("\n---- 如何解读 ----")
    print("  · 'H多出中属于前一日残留' 比例高 → 写入脚本把旧结果合并进了新日期，或者在数据未更新时跑过一次")
    print("  · 多出的 symbol 原始条目带后缀、而 panel 是另一种形式 → 写入格式不一致")
    print("  · 某分组被多个文件引用且都有写入 → 后跑的覆盖 panel，history 却合并了两次结果")
    print("  · 把本输出 + 扫描出来写 PE_valid 的那个脚本发给我，即可精准修复")


if __name__ == "__main__":
    main()