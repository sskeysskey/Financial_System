# Analyse_run_mode.py
import re
import sys
import datetime

LIVE_FLAG = "--live"


def _check_symbol(raw):
    v = (raw or "").strip().upper()
    if re.fullmatch(r"[A-Z0-9.\-^=_]+", v):
        return v, None
    return None, "SYMBOL 格式不正确（只允许字母、数字及 . - ^ = _）"


def _check_date(raw):
    v = (raw or "").strip()
    try:
        datetime.datetime.strptime(v, "%Y-%m-%d")
        return v, None
    except ValueError:
        return None, "日期格式应为 YYYY-MM-DD"


def _prompt(label, checker):
    while True:
        value, err = checker(input(label))
        if err is None:
            return value
        print(f"  ✗ {err}，请重新输入")


def _resolve(value, checker, name, prompt_text):
    """文件里的值合法就直接用，否则提示输入。"""
    if value:
        cleaned, err = checker(value)
        if err is None:
            return cleaned
        print(f"  ✗ 脚本中的 {name} 无效: {err}")
    return _prompt(prompt_text, checker)


def resolve_run_mode(symbol_default="", date_default=""):
    """
    返回 (SYMBOL_TO_TRACE, TARGET_DATE)
    - 带 --live：强制实盘，返回 ("", "")，忽略文件中的配置
    - 不带 --live：回测模式，使用文件中的值；缺失或无效时提示输入
    """
    if LIVE_FLAG in sys.argv:
        print("▶ 实盘模式 (--live)，忽略脚本内的 SYMBOL_TO_TRACE / TARGET_DATE")
        return "", ""

    print("▶ 回测模式（未带 --live）：需要 SYMBOL_TO_TRACE 和 TARGET_DATE")
    try:
        symbol = _resolve(symbol_default, _check_symbol, "SYMBOL_TO_TRACE",
                          "  请输入 SYMBOL_TO_TRACE (如 DTE): ")
        target_date = _resolve(date_default, _check_date, "TARGET_DATE",
                               "  请输入 TARGET_DATE (如 2026-09-24): ")
    except (EOFError, KeyboardInterrupt):
        sys.exit("\n已取消运行。")

    print(f"▶ 回测目标: {symbol} @ {target_date}")
    return symbol, target_date