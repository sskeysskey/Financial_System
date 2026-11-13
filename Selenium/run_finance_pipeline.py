#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
import subprocess
from datetime import date

FIN = "/Users/yanzhang/Coding/Financial_System"
FILTER_PY   = f"{FIN}/JavaScript/Screener/Filter.py"
COMPARE_PY  = f"{FIN}/JavaScript/TopETFs/Compare_Insert.py"
EARNINGS_PY = f"{FIN}/Selenium/YF_Earnings_Combined.py"
DUP_PY      = f"{FIN}/Query/Check_Earning_dup.py"

SCREENER_LOG = "/Users/yanzhang/Coding/News/screener_sectors.txt"
STATE_FILE   = f"{FIN}/Selenium/pipeline_state.json"

NO_CHANGE_MSG = "Sectors_All文件没有需要更新的内容"
COMPARE_RC_SYNCED = 0
COMPARE_RC_NEW_ETF = 2

STAGES = ["filter", "compare", "earnings", "dup"]
PYTHON = sys.executable  # 用当前解释器运行所有子程序


# ================= 进度记录 =================
def today_str():
    return date.today().isoformat()

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    if state.get("date") != today_str():  # 不是今天的记录，视为新的一天
        state = {"date": today_str(), "done": []}
    return state

def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)  # 原子写入，避免中途崩溃损坏文件

def mark_done(state, stage):
    if stage not in state["done"]:
        state["done"].append(stage)
        save_state(state)


# ================= 通用工具 =================
def run(script):
    """运行子程序并返回退出码；开启自动化模式"""
    env = {**os.environ, "PIPELINE_AUTO": "1"}
    name = os.path.basename(script)
    print(f"\n========== [{time.strftime('%H:%M:%S')}] 运行 {name} ==========", flush=True)
    rc = subprocess.run([PYTHON, script], env=env).returncode
    print(f"========== {name} 退出码: {rc} ==========", flush=True)
    return rc

def read_filter_result(since_ts):
    """
    返回 True：有新增 symbol；False：无新增；None：结果无效（文件缺失/旧文件/格式错误）
    """
    if not os.path.exists(SCREENER_LOG):
        print("未找到 screener_sectors.txt")
        return None
    if os.path.getmtime(SCREENER_LOG) < since_ts:
        print("screener_sectors.txt 不是本次运行生成的（旧文件）")
        return None

    with open(SCREENER_LOG, "r", encoding="utf-8") as f:
        text = f.read()

    marker = "--- 新增的 Symbols ---"
    if marker not in text:
        print("日志中没有'新增的 Symbols'段")
        return None

    section = text.split(marker, 1)[1].strip("\n").split("\n\n", 1)[0]
    items = [ln.strip()[2:] for ln in section.splitlines() if ln.strip().startswith("- ")]
    if not items:
        return None
    print(f"新增的 Symbols 段内容: {items}")
    return items != [NO_CHANGE_MSG]


# ================= 各步骤 =================
# 返回 True 表示继续下一步，False 表示暂停/出错，停止流水线

def stage_filter(state):
    start_ts = time.time()
    rc = run(FILTER_PY)
    if rc != 0:
        print("❌ Filter 异常退出，流程停止")
        return False
    has_new = read_filter_result(start_ts)
    if has_new is None:
        print("❌ Filter 结果无效，流程停止")
        return False
    # Filter 本身已经跑完并写好了数据，无论是否有新 symbol 都记为完成
    mark_done(state, "filter")
    if has_new:
        print("⏸ Filter 发现新 symbol，请手动处理。处理完后重新运行本脚本，将从 compare 继续")
        return False
    return True

def stage_compare(state):
    rc = run(COMPARE_PY)
    if rc == COMPARE_RC_SYNCED:
        mark_done(state, "compare")
        return True
    if rc == COMPARE_RC_NEW_ETF:
        mark_done(state, "compare")  # 文件已写入 ETFs_new.txt，本步已完成
        print("⏸ Compare_Insert 发现新 ETF，请手动处理。处理完后重新运行本脚本，将从 earnings 继续")
        return False
    print(f"❌ Compare_Insert 出错（退出码 {rc}），流程停止，下次运行会重跑本步")
    return False

def stage_earnings(state):
    rc = run(EARNINGS_PY)
    if rc == 0:
        mark_done(state, "earnings")
    else:
        print("⚠️ YF_Earnings_Combined 退出码非 0，本步不记为完成，下次会重跑")
    return True  # 保持原行为：earnings 失败也继续后面的步骤

def stage_dup(state):
    rc = run(DUP_PY)
    if rc == 0:
        mark_done(state, "dup")
    return True


STAGE_FUNCS = {
    "filter": stage_filter,
    "compare": stage_compare,
    "earnings": stage_earnings,
    "dup": stage_dup,
}


# ================= 主流程 =================
def parse_args():
    parser = argparse.ArgumentParser(description="金融数据流水线（支持断点续跑）")
    parser.add_argument("--start", choices=STAGES,
                        help="手动指定从哪一步开始，之前的步骤会被标记为已完成")
    parser.add_argument("--reset", action="store_true",
                        help="清空今天的进度，从头开始")
    return parser.parse_args()

def main():
    args = parse_args()
    state = load_state()

    if args.reset:
        state = {"date": today_str(), "done": []}
        save_state(state)
        print("已清空今天的进度")

    if args.start:
        for s in STAGES[:STAGES.index(args.start)]:
            if s not in state["done"]:
                state["done"].append(s)
        save_state(state)
        print(f"从 {args.start} 开始，之前的步骤已标记为完成")

    print(f"当前进度（{today_str()}）: {state['done'] or '无'}")

    for stage in STAGES:
        if stage in state["done"]:
            print(f"⏭ {stage} 今天已完成，跳过")
            continue
        if not STAGE_FUNCS[stage](state):
            return

    print("\n🎉 流水线结束")


if __name__ == "__main__":
    main()