#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ft_watchlist_add.py —— Python 侧「一键把 symbol 加入 Firstrade 自选股分组」客户端

链路：
    本文件  ──POST /wl_add──▶  bridge_server.py 任务队列
                              ──▶ Chrome 扩展 wl_agent.js（切分组 + 添加）
                              ◀── POST /wl_task_result
供 Chart_input_single.py / Check_Group.py 共用。

对外接口：
    watchlist_groups()                       -> ['买','买买','买买买','卖卖卖']
    add_symbol(sym, group, wait=45)          -> {'ok':bool,'message':str,...}   阻塞
    add_symbol_async(sym, group, on_done)    -> threading.Thread                非阻塞
    choose_group_dialog(sym, groups, parent) -> 选中的分组名 或 None            PyQt6
    last_group() / save_last_group(g)
    notify_mac(title, text)
"""
import os
import re
import sys
import json
import threading
import subprocess
from urllib import request

BRIDGE_BASE = os.environ.get("FT_BRIDGE", "http://127.0.0.1:18888")

USER_HOME = os.path.expanduser("~")
MODULES_DIR = os.path.join(USER_HOME, "Coding", "Financial_System", "Modules")
GROUPS_FILE = os.path.join(MODULES_DIR, "ft_watchlist_groups.json")   # 可选：自定义分组
LAST_FILE = os.path.join(MODULES_DIR, "ft_watchlist_last_group.txt")  # 记住上次选择

DEFAULT_GROUPS = ["买", "买买", "买买买", "卖卖卖"]


# ----------------------------------------------------------------------
# 分组列表
# ----------------------------------------------------------------------
def watchlist_groups():
    """优先 Modules/ft_watchlist_groups.json -> 环境变量 FT_WL_GROUPS -> 默认"""
    try:
        if os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            arr = data.get("groups") if isinstance(data, dict) else data
            arr = [str(x).strip() for x in (arr or []) if str(x).strip()]
            if arr:
                return arr
    except Exception as e:
        print(f"[FT-WL] 读取 {GROUPS_FILE} 失败: {e}")
    env = os.environ.get("FT_WL_GROUPS", "").strip()
    if env:
        arr = [s.strip() for s in re.split(r"[,\s;]+", env) if s.strip()]
        if arr:
            return arr
    return list(DEFAULT_GROUPS)


def last_group():
    try:
        if os.path.exists(LAST_FILE):
            with open(LAST_FILE, "r", encoding="utf-8") as f:
                g = f.read().strip()
            if g:
                return g
    except Exception:
        pass
    return ""


def save_last_group(group):
    try:
        os.makedirs(MODULES_DIR, exist_ok=True)
        with open(LAST_FILE, "w", encoding="utf-8") as f:
            f.write(str(group or "").strip())
    except Exception:
        pass


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------
def _post(path, payload, timeout=20):
    url = BRIDGE_BASE.rstrip("/") + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data,
                          headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path, timeout=5):
    url = BRIDGE_BASE.rstrip("/") + path
    with request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ping():
    try:
        return _get("/ping", timeout=3)
    except Exception:
        return None


def add_symbol(symbol, group, wait=45, restore=True):
    """阻塞式：把 symbol 加进 group。返回 dict(ok, message, symbol, group, raw)"""
    symbol = str(symbol or "").strip().upper()
    group = str(group or "").strip()
    out = {"ok": False, "symbol": symbol, "group": group, "message": ""}
    if not symbol:
        out["message"] = "symbol 为空"
        return out
    try:
        r = _post("/wl_add",
                  {"symbol": symbol, "group": group,
                   "wait": max(1, int(wait)), "restore": bool(restore)},
                  timeout=int(wait) + 20)
    except Exception as e:
        out["message"] = (f"连不上本地桥接服务 {BRIDGE_BASE}：{e}\n"
                          f"请先在终端运行 bridge_server.py")
        return out
    out["ok"] = bool(r.get("ok"))
    out["message"] = r.get("message") or ("已加入" if out["ok"] else "未收到浏览器回报")
    out["raw"] = r
    return out


def add_symbol_async(symbol, group, on_done=None, wait=45, restore=True):
    """非阻塞：在后台线程执行，完成后回调 on_done(dict)。
       ⚠ on_done 在工作线程里被调用，不要直接操作 GUI（用队列或 Qt signal）。"""
    def _run():
        res = add_symbol(symbol, group, wait=wait, restore=restore)
        if callable(on_done):
            try:
                on_done(res)
            except Exception as e:
                print(f"[FT-WL] on_done 回调异常: {e}")
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    return th


# ----------------------------------------------------------------------
# macOS 通知
# ----------------------------------------------------------------------
def notify_mac(title, text, subtitle=None):
    if sys.platform != "darwin":
        return
    def esc(s):
        return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    parts = [f'display notification "{esc(text)}" with title "{esc(title)}"']
    if subtitle:
        parts.append(f'subtitle "{esc(subtitle)}"')
    try:
        subprocess.Popen(["osascript", "-e", " ".join(parts)])
    except Exception:
        pass


# ----------------------------------------------------------------------
# 分组选择对话框（PyQt6，Nord 风格，支持数字键 1-9 / Esc）
# ----------------------------------------------------------------------
def choose_group_dialog(symbol, groups=None, parent=None, title=None):
    try:
        from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout,
                                     QLabel, QPushButton)
        from PyQt6.QtGui import QFont
        from PyQt6.QtCore import Qt
    except Exception as e:
        print(f"[FT-WL] 无法加载 PyQt6，无法弹出选择框: {e}")
        return None

    groups = groups or watchlist_groups()
    if not groups:
        return None

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    prev = last_group()

    class _Chooser(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.picked = None
            self.setWindowTitle(title or f"把 {symbol} 加入自选股分组")
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(18, 16, 18, 16)
            lay.setSpacing(8)

            head = QLabel(f"{symbol}  →  选择目标分组")
            head.setFont(QFont("Arial Unicode MS", 16, QFont.Weight.Bold))
            head.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(head)

            for i, g in enumerate(groups[:9], start=1):
                mark = "  ←上次" if g == prev else ""
                b = QPushButton(f"{i}.  {g}{mark}")
                b.setFont(QFont("Arial Unicode MS", 15))
                b.setMinimumHeight(38)
                b.clicked.connect(lambda _=False, gg=g: self._pick(gg))
                if g == prev:
                    b.setDefault(True)
                    b.setFocus()
                lay.addWidget(b)

            tip = QLabel("按 1~9 直接选择 ｜ Esc 取消")
            tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tip.setStyleSheet("color:#81A1C1; font-size:12px;")
            lay.addWidget(tip)

            self.setStyleSheet("""
                QDialog { background-color:#2E3440; }
                QLabel { color:#ECEFF4; }
                QPushButton {
                    background-color:#3B4252; color:#ECEFF4;
                    border:1px solid #4C566A; border-radius:6px;
                    padding:6px 12px; text-align:left;
                }
                QPushButton:hover { background-color:#4C566A; }
                QPushButton:default { border:2px solid #88C0D0; }
            """)

        def _pick(self, g):
            self.picked = g
            self.accept()

        def keyPressEvent(self, e):
            k = e.key()
            if k == Qt.Key.Key_Escape:
                self.picked = None
                self.reject()
                return
            if Qt.Key.Key_1 <= k <= Qt.Key.Key_9:
                idx = k - Qt.Key.Key_1
                if idx < len(groups):
                    self._pick(groups[idx])
                    return
            super().keyPressEvent(e)

    dlg = _Chooser()
    dlg.exec()
    return dlg.picked


# ----------------------------------------------------------------------
if __name__ == "__main__":
    sym = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
    grp = sys.argv[2] if len(sys.argv) > 2 else watchlist_groups()[0]
    print(f"桥接状态: {'OK' if ping() else '不可用'}")
    print(f"提交: {sym} -> {grp}")
    print(add_symbol(sym, grp, wait=45))