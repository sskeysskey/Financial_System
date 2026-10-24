"""
SupportLevel 实盘/回测一致性验证（只读，不修改任何 JSON / 数据库）
六方对比:
  BT   回测复刻   : 输入=history[分组][D]，原回测语义
  LV   实盘复刻   : 输入=当前 Sectors_panel 分组，原实盘语义(now 参照日、滞后数据也参与判定)
  LVF  修复后逻辑 : 输入同 LV，交易日参照 + 跳过滞后数据
  SNAP 实盘快照   : Support_RunLog 里该日期最新一次实盘快照(新功能，以后才有)
  P    面板输出   : Sectors_panel.SupportLevel_Close/Over（早上实盘的直接输出）
  H    历史记录   : Earning_History.SupportLevel_Close/Over[D]
"""
import os
import sys
import json
import glob
import time
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import Analyse_Earning_Support as AES

# ================= 配置 =================
VERIFY_DATES = ["2026-10-16"]          # 可追加历史日期(只能做 BT vs H)，如 "2026-10-07"
LIVE_RUN_DATE = "2026-10-17"           # 早上实盘运行时的自然日(复刻原代码 now() 语义)；留空=今天
VERIFY_TRACE_SYMBOL = ""               # 想看某个 symbol 的完整判定过程就填上
ADJACENT_DAYS = 7                      # 在 history 前后多少天内查找该 symbol 的出现记录
SHOW_MSG = True
REPORT_DIR = AES.RUN_SNAPSHOT_DIR

CAT_KEY = {"close": "SupportLevel_Close", "over": "SupportLevel_Over"}
DESC = OrderedDict([
    ("BT", "回测复刻(history分组@D)"),
    ("LV", "实盘复刻(panel分组,原逻辑)"),
    ("LVF", "修复后逻辑(panel分组)"),
    ("SNAP", "实盘快照"),
    ("P", "面板实际输出"),
    ("H", "历史实际记录"),
])
REASON_CN = {
    "no_table": "数据库无此symbol", "insufficient_rows": "K线不足2条", "not_down": "最新收盘未低于前收",
    "null_price": "价格为空", "earning_day": "当日为财报日", "forced_no_inherit": "强制拉回但未命中顺延",
    "no_hit": "新旧逻辑均未命中", "legacy_abort_no_hit": "旧逻辑中止且支撑区未命中",
    "stale": "数据滞后被跳过", "error": "异常", "hit": "命中", "": "-",
}


def _is_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except Exception:
        return False


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _norm_set(items, known):
    out = set()
    if isinstance(items, dict):
        items = list(items.keys())
    for it in items or []:
        s = AES.normalize_symbol(it, known)
        if s:
            out.add(s)
    return out


def _cat_sets(results, D):
    sets = {"close": set(), "over": set()}
    off = defaultdict(lambda: defaultdict(set))
    for s, r in results.items():
        c = r.get("cat")
        if c in sets:
            if r.get("latest_date") == D:
                sets[c].add(s)
            else:
                off[r.get("latest_date")][c].add(s)
    return sets, off


def check_indexes(cur, tables):
    missing = []
    for t in tables:
        try:
            cur.execute(f"PRAGMA index_list([{t}])")
            ok = False
            for row in cur.fetchall():
                cur.execute(f"PRAGMA index_info([{row[1]}])")
                cols = [r[2] for r in sorted(cur.fetchall())]
                if cols[:2] == ["name", "date"]:
                    ok = True
                    break
            if not ok:
                missing.append(t)
        except Exception:
            pass
    return missing


def scan_history_anomalies(eh, last_n=60, ratio=0.35):
    out = []
    for cat, key in CAT_KEY.items():
        node = eh.get(key, {}) or {}
        dates = sorted(k for k in node if _is_date(k))[-last_n:]
        sizes = [len(node[d] or []) for d in dates]
        for i, d in enumerate(dates):
            neigh = sorted(sizes[max(0, i - 5):i] + sizes[i + 1:i + 6])
            if len(neigh) >= 3:
                med = neigh[len(neigh) // 2]
                if med >= 5 and sizes[i] <= med * ratio:
                    out.append((key, d, sizes[i], med, sorted(node[d] or [])))
    return out


def load_snapshot(D):
    files = sorted(glob.glob(os.path.join(AES.RUN_SNAPSHOT_DIR, f"support_run_{D}_*.json")))
    if not files:
        return None, None
    try:
        return files[-1], _load(files[-1])
    except Exception:
        return files[-1], None


def adjacent_appearances(eh, sym, D, known):
    out = {}
    d0 = datetime.strptime(D, "%Y-%m-%d")
    for cat, key in CAT_KEY.items():
        node = eh.get(key, {}) or {}
        hits = []
        for k, items in node.items():
            if not _is_date(k):
                continue
            if abs((datetime.strptime(k, "%Y-%m-%d") - d0).days) <= ADJACENT_DAYS and sym in _norm_set(items, known):
                hits.append(k)
        out[cat] = sorted(hits)
    return out


def describe(r):
    if r is None:
        return "未纳入分析"
    parts = [f"结果={r['cat'] or '无'}"]
    if r.get("val"):
        parts.append(f"值={r['val']}")
    if r.get("kind"):
        parts.append(f"路径={r['kind']}")
    parts.append(f"原因={REASON_CN.get(r.get('reason', ''), r.get('reason'))}")
    parts.append(f"最新={r.get('latest_date')} 收={r.get('latest_close')} 前收={r.get('prev_close')} low={r.get('latest_low')}")
    if r.get("is_earning_day"):
        parts.append("财报日")
    if r.get("stale"):
        parts.append("⚠滞后")
    if r.get("forced_only"):
        parts.append("强制拉回")
    if r.get("inherit_src"):
        parts.append(f"顺延源={r['inherit_src']}")
    if r.get("interrupted"):
        parts.append("顺延被支撑区中断")
    if r.get("legacy_cat") or r.get("zone_cat"):
        parts.append(f"旧={r.get('legacy_cat')} 支撑区={r.get('zone_cat')}"
                     + (f"(分{r['zone_score']:.0f})" if r.get("zone_score") is not None else ""))
    if r.get("error"):
        parts.append(f"错误={r['error']}")
    return " | ".join(parts)


def make_hints(sym, cat, runs, D):
    h = []
    other = "over" if cat == "close" else "close"

    def has(lbl, c=cat):
        return lbl in runs and sym in runs[lbl]["sets"][c]

    def inp(lbl):
        r = runs.get(lbl)
        return bool(r and "mem" in r and (sym in r["mem"] or sym in r["forced"]))

    def res(lbl):
        r = runs.get(lbl)
        return r["res"].get(sym) if r and "res" in r else None

    bt, lv = res("BT"), res("LV")
    inH, inBT = has("H"), has("BT")

    if inH and not inBT:
        if not inp("BT"):
            h.append("回测输入里没有：history 目标分组在 D 当天不含该 symbol，也不在顺延强制拉回集合 → 回测根本没分析它")
        elif bt:
            h.append(f"回测分析了但未判为 {cat}：{REASON_CN.get(bt['reason'], bt['reason'])}"
                     + ("（按当前 DB 数据不满足条件，若实盘判中了，说明实盘时 DB 数据与现在不同 → 数据被修订/当时未更新完整）"
                        if bt['reason'] in ('not_down', 'earning_day', 'no_hit') else ""))
    if inBT and not inH:
        if has("H", other):
            h.append(f"类别互换：history 把它记在 {CAT_KEY[other]} 里")
        if bt and bt.get("kind") == "inherit":
            h.append(f"回测走的是顺延(源={bt.get('inherit_src')})，检查实盘时的 over_history 是否不同")
    for lbl, r in (("BT", bt), ("LV", lv)):
        if r and r.get("stale"):
            h.append(f"{lbl}: 该 symbol 最新K线={r['latest_date']} ≠ {D}（数据滞后），原代码会把它写进 history[{r['latest_date']}] 覆盖那天的列表")

    if "LV" in runs:
        inLV, inP = has("LV"), has("P")
        if inp("BT") != inp("LV"):
            h.append("输入差异：" + ("history 分组有、当前 panel 分组没有" if inp("BT") else "panel 分组有、history 分组没有")
                     + " → 回测和实盘的输入来源不一致（若 panel 在支撑脚本之后被 ETF_Volume / Imigrate 改过，也会这样）")
        if bt and lv and bt.get("forced_only") != lv.get("forced_only"):
            h.append("顺延强制拉回集合不同：原实盘以 now() 自然日为参照，回测以交易日为参照（已在新代码中修复）")
        if bt and lv and bt.get("inherit_src") != lv.get("inherit_src"):
            h.append(f"顺延源日期不同 BT={bt.get('inherit_src')} LV={lv.get('inherit_src')}")
        if inLV != inP:
            h.append("用当前数据复刻实盘 ≠ 面板实际输出 → 早上运行时的 DB 数据或代码版本与现在不同（数据被修订、当时数据不完整、或之后又跑过一次）")
        if inP and not inH:
            if lv and lv.get("latest_date") and lv["latest_date"] != D:
                h.append(f"面板有、history[D] 没有：它的 latest_date={lv['latest_date']}，原代码写到了 history[{lv['latest_date']}]")
            else:
                h.append("面板有、history[D] 没有 → history 写入后被其他脚本（如 Imigrate_new_exist.py）或同日的另一次运行修改/覆盖")
        if inH and not inP:
            h.append("history 有、面板没有 → history[D] 来自另一次运行或其他脚本写入；也可能面板之后被修改过")
        if inLV == inP and inBT != inLV:
            h.append("实盘复刻与面板一致 → 差异来自回测的输入/顺延窗口，而不是数据")
    if "SNAP" in runs and has("SNAP") != inH:
        h.append("快照与 history 不一致 → 写入之后 history 被修改")
    for lbl in ("BT", "LV"):
        r = runs.get(lbl)
        if r and sym in r.get("norm_syms", set()):
            h.append(f"{lbl}: 输入里该 symbol 带后缀（如甲），原代码会因查不到表而静默跳过（已修复）")
    return h


def run_engine(cur, s2t, eh, over_asof, syms, forced, D, stale_policy):
    eng = AES.SupportEngine(cur, s2t, eh, over_asof, print, VERIFY_TRACE_SYMBOL, verbose=False)
    t0 = time.time()
    res, sess = eng.run(syms | forced, forced, D, stale_policy)
    return res, sess, time.time() - t0


def verify_one(D, cur, s2t, s_latest, known, eh, panel, over_full):
    print("\n" + "=" * 100)
    print(f"🔎 验证日期 {D}")
    print("=" * 100)
    over_asof = {k: v for k, v in over_full.items() if _is_date(k) and k < D}
    runs = OrderedDict()
    gap_max = AES.INHERIT_GAP_MAX_DAYS
    use_forced = AES.ENABLE_OVER_INHERIT and AES.FORCE_KEEP_OVER_CHAIN

    # ---------- BT ----------
    syms, mem, unres, norm = AES.collect_group_symbols(eh, AES.TARGET_GROUPS, D, known)
    if not syms:
        print(f"⚠️ history 里 {D} 没有任何目标分组数据，BT 无法进行")
    forced = AES.collect_forced_symbols(over_asof, syms, D, True, gap_max, known) if use_forced else set()
    res, sess, dt = run_engine(cur, s2t, eh, over_asof, syms, forced, D, "keep")
    sets, off = _cat_sets(res, D)
    runs["BT"] = dict(res=res, sets=sets, off=off, mem=mem, forced=forced, sess=sess,
                      norm_syms={x[2] for x in norm}, unres=unres, secs=dt)
    print(f"[BT] 输入 {len(syms)} 个 + 强制拉回 {len(forced)} 个 | 会话日={sess} | 规范化 {len(norm)} | 不可识别 {len(unres)} | 耗时 {dt:.1f}s")
    if sess and sess != D:
        print(f"⚠️ 数据库中 ≤{D} 的最新交易日是 {sess}，{D} 可能不是交易日")

    # ---------- LV / LVF / P ----------
    p_syms, p_mem, p_unres, p_norm = AES.collect_group_symbols(panel, AES.TARGET_GROUPS, None, known)
    panel_session = max((s_latest[s] for s in p_syms if s_latest.get(s)), default=None)
    if panel_session == D:
        live_ref = LIVE_RUN_DATE or datetime.now().strftime("%Y-%m-%d")
        f_lv = AES.collect_forced_symbols(over_asof, p_syms, live_ref, False, gap_max, known) if use_forced else set()
        res, sess, dt = run_engine(cur, s2t, eh, over_asof, p_syms, f_lv, D, "keep")
        sets, off = _cat_sets(res, D)
        runs["LV"] = dict(res=res, sets=sets, off=off, mem=p_mem, forced=f_lv, sess=sess,
                          norm_syms={x[2] for x in p_norm}, unres=p_unres, secs=dt)
        print(f"[LV] 输入 {len(p_syms)} 个 + 强制拉回 {len(f_lv)} 个(参照日={live_ref}, 含当天) | 耗时 {dt:.1f}s")

        f_lvf = AES.collect_forced_symbols(over_asof, p_syms, D, True, gap_max, known) if use_forced else set()
        res, sess, dt = run_engine(cur, s2t, eh, over_asof, p_syms, f_lvf, D, "skip")
        sets, off = _cat_sets(res, D)
        runs["LVF"] = dict(res=res, sets=sets, off=off, mem=p_mem, forced=f_lvf, sess=sess,
                           norm_syms={x[2] for x in p_norm}, unres=p_unres, secs=dt)
        print(f"[LVF] 强制拉回 {len(f_lvf)} 个(参照日={D}, 不含当天) | 耗时 {dt:.1f}s")
    else:
        print(f"ℹ️ 当前 panel 对应的交易日是 {panel_session}，不是 {D} → 跳过 LV/LVF/P（panel 只反映最新状态）")

    snap_path, snap = load_snapshot(D)
    if snap:
        ss, _ = _cat_sets(snap.get("results", {}), D)
        runs["SNAP"] = dict(sets=ss, res=snap.get("results", {}))
        print(f"[SNAP] {snap_path}")

    if panel_session == D:
        runs["P"] = dict(sets={c: _norm_set(panel.get(k, {}), known) for c, k in CAT_KEY.items()})

    runs["H"] = dict(sets={c: _norm_set((eh.get(k, {}) or {}).get(D), known) for c, k in CAT_KEY.items()})

    # ---------- 计数 ----------
    print(f"\n{'来源':<30}{'Close':>8}{'Over':>8}")
    for lbl, r in runs.items():
        print(f"{lbl+' '+DESC[lbl]:<30}{len(r['sets']['close']):>8}{len(r['sets']['over']):>8}")

    # ---------- 配对比较 ----------
    pairs = [("BT", "H"), ("LV", "H"), ("P", "H"), ("SNAP", "H"), ("BT", "LV"), ("LV", "P"), ("LV", "LVF")]
    diff_syms = defaultdict(set)
    pair_report = {}
    print("\n---------- 差异清单 ----------")
    for a, b in pairs:
        if a not in runs or b not in runs:
            continue
        for c in ("close", "over"):
            A, B = runs[a]["sets"][c], runs[b]["sets"][c]
            ao, bo = sorted(A - B), sorted(B - A)
            pair_report[f"{a}_vs_{b}_{c}"] = {"only_" + a: ao, "only_" + b: bo}
            mark = "✅一致" if not ao and not bo else "❌"
            print(f"[{CAT_KEY[c]:<18}] {a:>4} vs {b:<4} {mark}  "
                  f"{a}有{b}无({len(ao)}): {ao}  |  {b}有{a}无({len(bo)}): {bo}")
            if (a, b) != ("LV", "LVF"):
                for s in ao + bo:
                    diff_syms[s].add(c)

    # ---------- 滞后数据覆盖历史的证据 ----------
    for lbl in ("LV", "BT"):
        r = runs.get(lbl)
        if not r or not r["off"]:
            continue
        print(f"\n---------- [{lbl}] 最新K线 ≠ {D} 的命中（原代码会写进其他日期 key） ----------")
        for d, cats in sorted(r["off"].items(), key=lambda x: str(x[0])):
            for c, ss in cats.items():
                hist_d = _norm_set((eh.get(CAT_KEY[c], {}) or {}).get(d), known)
                if hist_d and hist_d == ss:
                    tag = "🚨 history 该日期的列表与这些滞后 symbol 完全一致 → 基本可以确认被覆盖过"
                elif ss <= hist_d:
                    tag = "history 该日期包含这些 symbol"
                else:
                    tag = ""
                print(f"  {CAT_KEY[c]}[{d}] ← {sorted(ss)}  (history 当前该日 {len(hist_d)} 个) {tag}")

    # ---------- 逐个 symbol 详情 ----------
    details = {}
    if diff_syms:
        print(f"\n---------- 差异 symbol 详情 ({len(diff_syms)} 个) ----------")
    for s in sorted(diff_syms):
        print(f"\n◆ {s}  表={s2t.get(s)}  DB最新={s_latest.get(s)}  涉及类别={sorted(diff_syms[s])}")
        for lbl in ("BT", "LV", "LVF"):
            if lbl in runs:
                grp = runs[lbl]["mem"].get(s)
                print(f"   [{lbl}] 输入分组={grp or ('(强制拉回)' if s in runs[lbl]['forced'] else '无')} → {describe(runs[lbl]['res'].get(s))}")
                r = runs[lbl]['res'].get(s)
                if SHOW_MSG and r and r.get("msg"):
                    print(f"         {AES.strip_ansi(r['msg']).strip()}")
        for lbl in ("SNAP", "P", "H"):
            if lbl in runs:
                inc = [c for c in ("close", "over") if s in runs[lbl]["sets"][c]]
                extra = ""
                if lbl == "P":
                    vals = [f"{c}={panel.get(CAT_KEY[c], {}).get(s)!r}" for c in inc if isinstance(panel.get(CAT_KEY[c]), dict)]
                    extra = " " + ", ".join(vals) if vals else ""
                print(f"   [{lbl}] 所在类别={inc or '无'}{extra}")
        adj = adjacent_appearances(eh, s, D, known)
        print(f"   [H 前后±{ADJACENT_DAYS}天] Close: {adj['close']} | Over: {adj['over']}")
        hints = []
        for c in sorted(diff_syms[s]):
            hints += [f"({c}) {x}" for x in make_hints(s, c, runs, D)]
        for x in dict.fromkeys(hints):
            print(f"   💡 {x}")
        details[s] = {"hints": list(dict.fromkeys(hints)), "adjacent": adj,
                      **{lbl: runs[lbl]["res"].get(s) for lbl in ("BT", "LV", "LVF") if lbl in runs}}

    if not diff_syms:
        print("\n🎉 所有可比来源完全一致，没有差异。")

    def _ser(r):
        out = {"sets": {c: sorted(v) for c, v in r["sets"].items()}}
        for k in ("forced", "norm_syms"):
            if k in r:
                out[k] = sorted(r[k])
        if "unres" in r:
            out["unresolved"] = r["unres"]
        if "off" in r:
            out["off_date_hits"] = {str(d): {c: sorted(v) for c, v in cs.items()} for d, cs in r["off"].items()}
        return out

    report = {"date": D, "generated_at": datetime.now().isoformat(timespec="seconds"),
              "live_run_date": LIVE_RUN_DATE, "runs": {k: _ser(v) for k, v in runs.items()},
              "pairs": pair_report,
              "details": {s: {k: ({kk: (AES.strip_ansi(vv) if kk == "msg" else vv) for kk, vv in v.items()}
                                  if isinstance(v, dict) and k in ("BT", "LV", "LVF") else v)
                              for k, v in d.items()} for s, d in details.items()}}
    try:
        path = os.path.join(REPORT_DIR, f"verify_{D}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        AES._atomic_json_dump(path, report)
        print(f"\n📄 详细报告已保存: {path}")
    except Exception as e:
        print(f"\n报告保存失败: {e}")


def main():
    print("SupportLevel 一致性验证（只读模式）")
    eh = _load(AES.EARNING_HISTORY_PATH)
    panel = _load(AES.SECTORS_PANEL_PATH)
    sectors_all = _load(AES.SECTORS_ALL_PATH)

    conn = sqlite3.connect(f"file:{AES.DB_PATH}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        t0 = time.time()
        s2t, s_latest, dups = AES.build_symbol_index(cur, sectors_all, print)
        print(f"符号索引: {len(s2t)} 个 symbol，耗时 {time.time() - t0:.1f}s")
        if dups:
            print(f"⚠️ {len(dups)} 个 symbol 同时存在于多个表中: {sorted(dups)[:20]}")
        missing = check_indexes(cur, list(sectors_all.keys()) + ["Earning"])
        if missing:
            print(f"⚡ 性能提示: {len(missing)} 个表缺少 (name, date) 索引，可执行:")
            for t in missing[:50]:
                print(f'   CREATE INDEX IF NOT EXISTS "idx_{t}_name_date" ON [{t}](name, date);')

        anomalies = scan_history_anomalies(eh)
        if anomalies:
            print("\n🚨 history 中列表长度异常偏小的日期（疑似被滞后 symbol 覆盖）:")
            for key, d, n, med, items in anomalies:
                print(f"   {key}[{d}] 仅 {n} 个 (前后中位数 {med})：{items}")

        known = set(s2t)
        over_full = eh.get("SupportLevel_Over", {}) or {}
        for D in VERIFY_DATES:
            verify_one(D, cur, s2t, s_latest, known, eh, panel, over_full)
    finally:
        conn.close()


if __name__ == "__main__":
    main()