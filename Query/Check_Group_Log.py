#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resonance_Debug.py —— 多组共振 / 转折 全流程诊断
每个数字从哪来、为什么被算/不算，全部打印。
"""
import os, re, sys, json
from collections import defaultdict, OrderedDict

USER_HOME = os.path.expanduser("~")
BASE = os.path.join(USER_HOME, "Coding")
BASE_DOWNLOAD = os.path.join(USER_HOME, "Downloads")
EARNING_HISTORY_PATH = os.path.join(BASE, "Financial_System", "Modules", "Earning_History.json")
CONFIG_PATH          = os.path.join(BASE, "Financial_System", "Modules", "Sectors_panel.json")
LOG_PATH             = os.path.join(BASE_DOWNLOAD, "resonance_debug.log")

# ===================== 开关（和主程序保持一致） =====================
EXCLUDE_BACKUP_GROUPS = True    # 排除 *_backup
MAX_STALE_DAYS        = 0       # 分组最新日期允许落后全局最新交易日的天数
COLLAPSE_FAMILIES     = False   # 同族分组合并计 1 项
COMPARE_WITH_OLD      = True    # 同时打印“旧逻辑(含 backup/陈旧)”的结果做对比
MAX_DAYS_PRINT        = 15      # 每只票逐日明细最多打印几天

IGNORE_GROUPS = {"_Tag_Blacklist", "no_season"}
WEEK52_LOW_SECTORS = {
    "Basic_Materials","Real_Estate","Energy","Technology","Consumer_Cyclical",
    "Utilities","Consumer_Defensive","Industrials","Communication_Services",
    "Financial_Services","Healthcare"
}
HIGH_WEIGHT_CATEGORIES = {"PE_Volume","Short","Short_W","PE_Volume_high",
                          "SupportLevel_Over","PE_Deeper","PE_Deep"}
MEDIUM_WEIGHT_CATEGORIES = {"PE_Volume_up","PE_W","SupportLevel_Close","PE_Hot",
                            "OverSell_W","season"}
SUPPORT_LEVEL_GROUPS = {"SupportLevel_Close","SupportLevel_Over"}
SOURCE_GROUPS = {"Short","Short_W","Strategy12","Strategy34","OverSell_W",
                 "PE_Deep","PE_Deeper","PE_W","PE_valid","PE_invalid",
                 "PE_low","PE_lower","PE_lowest",
                 "PE_Volume","PE_Volume_up","PE_Hot","PE_Volume_high","season"}
PE_CHAODI_SOURCES = {"PE_Null"}
GROUP_FAMILIES = [
    {"PE_low","PE_lower","PE_lowest"}, {"PE_Deep","PE_Deeper"},
    {"Short","Short_W"}, {"SupportLevel_Close","SupportLevel_Over"},
    {"PE_Volume","PE_Volume_up","PE_Volume_high"},
    {"ETF_Volume_high","ETF_Volume_low","ETF_low"},
]
# 转折参数
TURN_MIN_STREAK = 3
TURN_MIN_DROP = 1
TURN_MAX_GAP = 2
TURN_RECENT_DAYS = 3
TURN_ALLOW_DROP_TO_ZERO = False
TURN_REQUIRE_NO_RECOVERY = True
TURN_LEVEL2_KEYS = {"PE_Volume","SupportLevel_Over","Short","PE_Volume_high","PE_Deep"}
TURN_LEVEL3_KEYS = {"PE_Volume","SupportLevel_Over","SupportLevel_Close","Short","Short_W",
                    "PE_Volume_high","PE_Deep","PE_valid","PE_invalid","PE_Deeper","season"}
TURN_NAME = {0:"一般转折",1:"值得一看",2:"较强转折",3:"极强转折"}

# ========== 内置配置：在这里填写你要跟踪的股票，不填就是空列表 [] ==========
INTERNAL_FOCUS = [
    # "ORCL",
    # "AAPL",
    # "MSFT"
]
# =========================================================================

# 优先级：命令行参数 > 内置配置；都没有则不聚焦全部输出
cli_args = sys.argv[1:]
if cli_args:
    # 有命令行参数，优先使用命令行
    FOCUS = {a.upper() for a in cli_args}
else:
    # 无命令行，读取内置配置
    FOCUS = {a.upper() for a in INTERNAL_FOCUS}

# ===================== 基础工具 =====================
_LOG = []
def log(msg=""):
    print(msg); _LOG.append(str(msg))
def flush_log():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG))
    print(f"\n>>> 日志已写入: {LOG_PATH}")

_DATE_RE = re.compile(r"^(\d{4})\D+(\d{1,2})\D+(\d{1,2})")
def norm_date(s):
    s = str(s).strip()
    m = _DATE_RE.match(s)
    if m:
        y, mo, d = m.groups(); return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    return "-".join(m.groups()) if m else s

def load_json(p):
    if not os.path.exists(p): return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=OrderedDict)

def clean_ticker(s):
    m = re.search(r"^([A-Za-z-]+)", s); return m.group(1) if m else s
def split_symbol_suffix(raw):
    b = clean_ticker(raw); return b.upper(), (raw[len(b):] if raw.startswith(b) else "")
def category_color(cat, suffix):
    if cat == "PE_Volume_high": return 'red' if (suffix and '甲' in suffix) else 'orange'
    if cat in HIGH_WEIGHT_CATEGORIES: return 'red'
    if cat in MEDIUM_WEIGHT_CATEGORIES: return 'orange'
    return 'blue'
def is_valid_group(g):
    if g in IGNORE_GROUPS: return False
    if EXCLUDE_BACKUP_GROUPS and g.endswith("_backup"): return False
    return True
def collapse_family(groups):
    if not COLLAPSE_FAMILIES: return set(groups)
    out = set()
    for g in groups:
        fam = next((f for f in GROUP_FAMILIES if g in f), None)
        out.add("|".join(sorted(fam)) if fam else g)
    return out
def fmt_items(items):
    d = {}
    for c, s in items:
        if c not in d or (s and not d[c]): d[c] = s
    return "、".join(f"{c}{('['+s+']') if s else ''}" for c, s in sorted(d.items()))

# ===================== 0. 52周新低集合 =====================
def load_week52(path):
    data = load_json(path); res = {}
    for sec in WEEK52_LOW_SECTORS:
        for sym in (data.get(sec) or {}):
            res[clean_ticker(sym).upper()] = sec
    return res

# ===================== 1. 分组体检 =====================
def audit(history):
    dates = set()
    for g, dm in history.items():
        if not is_valid_group(g) or not isinstance(dm, dict): continue
        dates.update(dm.keys())
    desc = sorted(dates, key=norm_date, reverse=True)
    pos = {d: i for i, d in enumerate(desc)}

    log("=" * 100)
    log("【0】数据体检")
    log("=" * 100)
    log(f"JSON 分组总数: {len(history)}  |  参与计算的分组: "
        f"{sum(1 for g in history if is_valid_group(g))}")
    bk = [g for g in history if g.endswith('_backup')]
    log(f"检测到 *_backup 镜像分组 {len(bk)} 个 → "
        f"{'已排除(EXCLUDE_BACKUP_GROUPS=True)' if EXCLUDE_BACKUP_GROUPS else '⚠未排除，会重复计数！'}")
    if bk: log("   " + ", ".join(sorted(bk)[:20]) + (" ..." if len(bk) > 20 else ""))
    log(f"全局交易日(新→旧, 前10): {desc[:10]}")
    log(f"全局最新交易日 = {desc[0] if desc else 'N/A'}")
    log("")
    log(f"{'分组':<26}{'最新日期':<14}{'滞后':<6}{'当日只数':<9}状态")
    log("-" * 100)
    for g in sorted(history):
        dm = history[g]
        if not isinstance(dm, dict) or not dm:
            log(f"{g:<26}{'-':<14}{'-':<6}{'-':<9}空分组"); continue
        latest = max(dm.keys(), key=norm_date)
        lag = pos.get(latest, -1)
        n = len(dm.get(latest) or [])
        if g in IGNORE_GROUPS:            st = "IGNORE_GROUPS"
        elif g.endswith("_backup"):       st = "backup(镜像)" + ("→已排除" if EXCLUDE_BACKUP_GROUPS else "→⚠计入")
        elif lag < 0:                     st = "⚠日期解析异常"
        elif lag > MAX_STALE_DAYS:        st = f"⚠陈旧→已排除(超过 MAX_STALE_DAYS={MAX_STALE_DAYS})"
        else:                             st = "✅计入"
        log(f"{g:<26}{latest:<14}{lag:<6}{n:<9}{st}")
    return desc, pos

# ===================== 2. 共振（逐项溯源） =====================
def resonance(history, desc, pos, week52):
    log("\n" + "=" * 100)
    log("【1】多组共振 —— 每一项的来源")
    log("=" * 100)
    contrib = defaultdict(list)      # sym -> [(group, date, raw, ok, reason)]
    chaodi = set()
    for g in sorted(history):
        dm = history[g]
        if g in IGNORE_GROUPS or not isinstance(dm, dict) or not dm: continue
        latest = max(dm.keys(), key=norm_date)
        lag = pos.get(latest, 10**9)
        reason, ok = "", True
        if EXCLUDE_BACKUP_GROUPS and g.endswith("_backup"):
            ok, reason = False, "backup 镜像分组(与主分组重复)"
        elif lag > MAX_STALE_DAYS:
            ok, reason = False, f"分组最新日期落后 {lag} 交易日(陈旧)"
        for raw in (dm.get(latest) or []):
            base, suf = split_symbol_suffix(raw)
            if ok and "抄底" in raw: chaodi.add(base)
            contrib[base].append((g, latest, raw, ok, reason))

    rows = []
    for sym in sorted(contrib):
        if FOCUS and sym not in FOCUS: continue_print = False
        else: continue_print = True
        good = {c[0] for c in contrib[sym] if c[3]}
        eff = set(good)
        removed = []
        if sym in chaodi and (eff & PE_CHAODI_SOURCES):
            removed.append(f"抄底标的→剔除 {sorted(eff & PE_CHAODI_SOURCES)}")
            eff -= PE_CHAODI_SOURCES
        w52 = sym in week52
        if w52 and good: eff.add("52week_low")
        eff2 = collapse_family(eff)
        count = len(eff2)

        # 同族重复提示
        fam_warn = [sorted(f & good) for f in GROUP_FAMILIES if len(f & good) >= 2]

        verdict = ""
        if count < 2:
            verdict = f"count={count} < 2 → 不进入共振列表"
        # elif count == 2 and not eff2.isdisjoint(SUPPORT_LEVEL_GROUPS) \
        #                 and not eff2.isdisjoint(SOURCE_GROUPS):
        #     verdict = "count=2 且同时含 SupportLevel + 源头分组 → 按规则丢弃"
        else:
            verdict = f"✅ 归入「共振 {count} 组」"
            rows.append((count, sym))

        if continue_print:
            log(f"\n---- {sym} ----")
            for g, d, raw, ok, rs in sorted(contrib[sym]):
                mark = "  +" if ok else "  x"
                log(f"{mark} {g:<24}@{d:<12} 原始串='{raw}'"
                    f"{'  色=' + category_color(g, split_symbol_suffix(raw)[1]) if ok else '  ✗ ' + rs}")
            log(f"   52week_low: {'是（' + week52[sym] + ' 板块）' if w52 else '否'}"
                f"{'  → 虚拟分组 +1' if w52 and good else ''}")
            log(f"   抄底: {'是' if sym in chaodi else '否'}"
                + (("  " + "; ".join(removed)) if removed else ""))
            for fw in fam_warn:
                log(f"   ⚠同族分组同时命中(可能重复计数): {fw}")
            log(f"   有效分组({len(eff2)}): {sorted(eff2)}")
            log(f"   → {verdict}")

    log("\n---- 共振汇总（修复后逻辑）----")
    agg = defaultdict(list)
    for c, s in rows: agg[c].append(s)
    for c in sorted(agg, reverse=True):
        log(f"共振 {c} 组 ({len(agg[c])}只): {', '.join(sorted(agg[c]))}")

    if COMPARE_WITH_OLD:
        log("\n---- 旧逻辑对比（含 backup + 各组各自最新日）----")
        old = defaultdict(set)
        for g, dm in history.items():
            if g in IGNORE_GROUPS or not isinstance(dm, dict) or not dm: continue
            latest = max(dm.keys())          # 故意复刻旧写法(字符串 max)
            for raw in (dm.get(latest) or []):
                old[split_symbol_suffix(raw)[0]].add(g)
        for sym in sorted(old):
            if FOCUS and sym not in FOCUS: continue
            n_old = len(old[sym] | ({"52week_low"} if sym in week52 else set()))
            n_new = len({c[0] for c in contrib[sym] if c[3]} |
                        ({"52week_low"} if sym in week52 else set()))
            flag = "  ← ⚠差异" if n_old != n_new else ""
            log(f"  {sym:<8} 旧={n_old:<3} 新={n_new:<3}{flag}  旧分组={sorted(old[sym])}")
    return agg

# ===================== 3. 转折（逐步判定） =====================
def build_index(history):
    sym_items = defaultdict(dict); dates = set()
    for g, dm in history.items():
        if not is_valid_group(g) or not isinstance(dm, dict): continue
        for d, syms in dm.items():
            if not isinstance(syms, list): continue
            dates.add(d)
            for raw in syms:
                s, suf = split_symbol_suffix(raw)
                sym_items[s].setdefault(d, []).append((g, suf))
    return sym_items, sorted(dates, key=norm_date, reverse=True)

def key_hits(cats, cnt):
    if cnt <= 2:
        h = cats & TURN_LEVEL2_KEYS; return h, len(h) >= 1, 1, "LEVEL2"
    h = cats & TURN_LEVEL3_KEYS;     return h, len(h) >= 2, 2, "LEVEL3"

def turning(history, week52):
    sym_items, desc = build_index(history)
    pos = {d: i for i, d in enumerate(desc)}
    recent = set(desc[:TURN_RECENT_DAYS])
    log("\n" + "=" * 100)
    log("【2】转折检测 —— 逐步判定")
    log("=" * 100)
    log(f"参数: MIN_STREAK={TURN_MIN_STREAK} MIN_DROP={TURN_MIN_DROP} MAX_GAP={TURN_MAX_GAP} "
        f"RECENT_DAYS={TURN_RECENT_DAYS} ALLOW_ZERO={TURN_ALLOW_DROP_TO_ZERO} "
        f"NO_RECOVERY={TURN_REQUIRE_NO_RECOVERY}")
    log(f"最近窗口: {sorted(recent, key=norm_date, reverse=True)}")

    results = []
    for sym in sorted(sym_items):
        show = (not FOCUS) or (sym in FOCUS)
        dm = sym_items[sym]
        rec = sorted(dm, key=lambda d: pos[d])          # 新→旧
        cats_of = {d: {c for c, _ in dm[d]} for d in rec}
        cnt_of  = {d: len(cats_of[d]) for d in rec}
        if show:
            log(f"\n---- {sym} 逐日明细(新→旧, 最多{MAX_DAYS_PRINT}天) ----")
            for d in rec[:MAX_DAYS_PRINT]:
                log(f"   {d} (T-{pos[d]}) {cnt_of[d]}项: {fmt_items(dm[d])}")
        if len(rec) < TURN_MIN_STREAK:
            if show: log(f"   ✗ 有记录日仅 {len(rec)} < MIN_STREAK={TURN_MIN_STREAK}")
            continue

        cands = []
        if TURN_ALLOW_DROP_TO_ZERO and pos[rec[0]] >= 1:
            zd = desc[pos[rec[0]] - 1]
            if zd in recent: cands.append((zd, 0, 0, "信号完全消失日"))
        for i, d in enumerate(rec):
            if d not in recent: break
            cands.append((d, cnt_of[d], i + 1, "记录日"))
        if show: log(f"   候选转折日: {[(d, m) for d, m, _, _ in cands] or '无(最近窗口内无记录)'}")

        best = None
        for d, m, p_start, kind in cands:
            if show: log(f"   ▶ 试 {d} ({m}项, {kind})")
            if TURN_REQUIRE_NO_RECOVERY:
                up = [x for x in rec if pos[x] < pos[d] and cnt_of[x] > m]
                if up:
                    if show: log(f"      ✗ 之后已回升: {[(x, cnt_of[x]) for x in up]}")
                    continue
            plateau, prev, j = [], d, p_start
            while j < len(rec):
                cd = rec[j]; gap = pos[cd] - pos[prev]
                if gap > TURN_MAX_GAP:
                    if show: log(f"      ✂ 断裂 {cd}: 与 {prev} 间隔 {gap} > MAX_GAP={TURN_MAX_GAP}")
                    break
                cnt = cnt_of[cd]
                if cnt <= m or cnt < 2:
                    if show: log(f"      ✂ 断裂 {cd}: {cnt}项 未多于转折日({m})或 <2")
                    break
                h, ok, need, lv = key_hits(cats_of[cd], cnt)
                if not ok:
                    if show: log(f"      ✂ 断裂 {cd}: {lv} 关键项命中 {sorted(h)}={len(h)} < {need}")
                    break
                plateau.append((cd, cnt, len(h)))
                if show: log(f"      ✓ 平台 {cd} {cnt}项 关键项{sorted(h)}({len(h)}/{need}) {lv}")
                prev = cd; j += 1
            if len(plateau) < TURN_MIN_STREAK:
                if show: log(f"      ✗ 平台仅 {len(plateau)} 天 < {TURN_MIN_STREAK}")
                continue
            counts = [c for _, c, _ in plateau]
            drop = min(counts) - m
            if drop < TURN_MIN_DROP:
                if show: log(f"      ✗ 跌幅 {drop} < MIN_DROP={TURN_MIN_DROP}")
                continue
            best = dict(symbol=sym, date=d, to_n=m, from_n=min(counts), from_max=max(counts),
                        drop=drop, streak=len(plateau),
                        key_max=max(k for _, _, k in plateau), plateau=plateau,
                        plateau_red=any(any(category_color(c, s) == 'red' for c, s in dm[pd])
                                        for pd, _, _ in plateau))
            break
        if not best:
            if show: log("   → 结论: 无转折")
            continue

        # 打分
        notes, score = [], 0.0
        add = min(best['drop'], 3) * 1.0; score += add
        notes.append(f"跌幅 {best['drop']} 档 → +{add:.1f}")
        ex = min(max(best['streak'] - TURN_MIN_STREAK, 0), 3)
        if ex: score += ex * 0.5; notes.append(f"平台超出基准 {ex} 天 → +{ex*0.5:.1f}")
        kb = min(best['key_max'], 3) * 0.4; score += kb
        notes.append(f"单日关键项最多 {best['key_max']} → +{kb:.1f}")
        if best['plateau_red']: score += .5; notes.append("平台含红色分组 → +0.5")
        if sym in week52: score += .5; notes.append(f"52周新低板块({week52[sym]}) → +0.5")
        if best['to_n'] == 0: score += .5; notes.append("信号完全消失 → +0.5")
        level = 3 if score >= 4.5 else 2 if score >= 3.5 else 1 if score >= 2.5 else 0
        best.update(score=score, level=level)
        results.append(best)
        if show:
            log(f"   → ✅ 转折 {best['from_n']}→{best['to_n']} @{best['date']} "
                f"平台{best['streak']}天 得分{score:.1f} L{level}({TURN_NAME[level]})")
            for n in notes: log(f"      · {n}")

    log("\n---- 转折汇总(按分数降序) ----")
    for r in sorted(results, key=lambda x: (-x['score'], -x['drop'], x['symbol'])):
        log(f"  {r['symbol']:<8} {r['from_n']}→{r['to_n']} @{r['date']} "
            f"平台{r['streak']}天 分{r['score']:.1f} L{r['level']}")
    if not results: log("  （无）")
    return results

# ===================== main =====================
if __name__ == "__main__":
    history = load_json(EARNING_HISTORY_PATH)
    week52 = load_week52(CONFIG_PATH)
    log(f"Earning_History: {EARNING_HISTORY_PATH}  (分组 {len(history)})")
    log(f"52周新低集合: {len(week52)} 只 → {sorted(week52)[:30]}")
    if FOCUS: log(f"仅打印明细的 symbol: {sorted(FOCUS)}")
    desc, pos = audit(history)
    resonance(history, desc, pos, week52)
    turning(history, week52)
    flush_log()