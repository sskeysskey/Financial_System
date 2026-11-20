#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MW_Bridge.py —— MarketWatch 抓取「浏览器扩展版」的本地桥接程序

架构：
  本程序（127.0.0.1:8765）= 大脑：任务调度 / 节奏限速 / 封禁冷却 / 数据校验 / 写库 / 改 JSON / 滑块
  Chrome 扩展 MW Daily Helper = 手脚：在你自用的 Chrome 中打开真实页面、解析、回传
  业务规则全部复用 MW_Today.py（作为库 import，MW_Today.py 本身不需要修改）

用法:
    python3 MW_Bridge.py                     # 单独运行：自动唤起 Chrome 扩展开始抓取
    python3 MW_Bridge.py --no-open           # 不自动唤起，在扩展弹窗中点「开始」
    python3 MW_Bridge.py --groups ETFs Energy
    python3 MW_Bridge.py --dry-run           # 只抓取并打印，不写库、不改 JSON
    python3 MW_Bridge.py --no-sanity / --no-check / --no-auto-slider / --ignore-cooldown / --keep-window
    FS_UNATTENDED=1 python3 MW_Bridge.py     # 无人值守（流水线自动设置）：滑块自动失败直接冷却

退出码（与 MW_Today.py 一致，并新增 3）:
    0 = 支持的分组已全部清空   2 = 仍有剩余   1 = 读取任务失败等错误
    3 = 扩展未连接/中途失联且仍有剩余   130 = Ctrl+C
"""
import argparse
import datetime
import json
import os
import random
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SELF_DIR = os.path.dirname(os.path.abspath(__file__))
if SELF_DIR not in sys.path:
    sys.path.insert(0, SELF_DIR)
import MW_Today as core  # noqa: E402  复用全部业务逻辑

log = core.tqdm.write

# ================= 配置 =================
PROTOCOL_VERSION = 1
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = int(os.environ.get("MW_BRIDGE_PORT", "8765"))
PORT_FALLBACK_TRIES = 10                 # 端口被占用时依次尝试 8765~8774
HELLO_TIMEOUT = 120                      # 自动唤起后等待扩展连接的时长
HELLO_TIMEOUT_NO_OPEN = 1800             # --no-open 时等待用户点击「开始」的时长
HELLO_REOPEN_AFTER = 40                  # 超过此时长仍未连接则再唤起一次
HEARTBEAT_TIMEOUT = core.CAPTCHA_MANUAL_WAIT + 150   # 扩展无任何请求超过此时长视为失联
WAIT_CHUNK_SECONDS = 30                  # 冷却期间扩展每隔多久来问一次
NAV_WAIT_SECONDS = 20                    # 单页等待数据的超时（真实浏览器加载广告较多，比原来略宽松）
DONE_LINGER_SECONDS = 10                 # 结束后等待扩展取走 done 指令的时长
MAX_BODY_BYTES = 2 * 1024 * 1024
INSTANCE_LOCK_PATH = os.path.join(tempfile.gettempdir(), "mw_bridge.lock")
CHROME_APP = core._mac_app_name_from_binary(core.CHROME_BINARY_PATH)
# 抓取窗口位置/大小：与原调试 Chrome 一致（滑块模板匹配依赖窗口在主屏且未被遮挡）
WORKER_WINDOW = {"left": 0, "top": 25, "width": 1366, "height": 900}

STATE_TEXT = {"stale": "页面未完成跳转", "timeout": "等待数据超时", "transient": "页面暂不可读",
              "error": "扩展执行出错"}


# ================= 滑块（复用 Slider_Verify） =================
class SliderHelper:
    def __init__(self, enabled):
        self.lock = threading.Lock()
        self.w = core.CaptchaAutoSolver(enabled=enabled and core.IS_MAC)
        self.available = bool(self.w.enabled and self.w.ensure_ready())

    def summary(self):
        return self.w.summary()

    def note_manual(self):
        self.w.stats["manual"] += 1

    def solve(self):
        w = self.w
        if not self.lock.acquire(timeout=1):
            return "busy"
        try:
            solver = w._get_solver() if w.enabled else None
            if solver is None:
                return "unavailable"
            guard = getattr(solver, "guard", None)
            if guard is not None:
                allowed, reason = guard.allow()
                if not allowed:
                    log(f"   ⏸️ 自动拖拽被保护器暂停：{reason}，转手动处理")
                    w.enabled = False
                    return "blocked"
            # 扩展已把抓取窗口设为 Chrome 的焦点窗口，这里只需把 Chrome 应用切到最前
            ok, msg = core._osascript(f'tell application "{CHROME_APP}" to activate')
            if not ok:
                log(f"   ⚠️ 激活 {CHROME_APP} 失败: {msg[:120]}")
            w._browser_activated = True
            time.sleep(core.WINDOW_ACTIVATE_SETTLE)

            hit = None
            deadline = time.time() + core.SLIDER_APPEAR_TIMEOUT
            while time.time() < deadline:
                try:
                    hit = solver.locate()
                except Exception as e:
                    log(f"[Slider] 截图/识别异常: {e}")
                    break
                if hit:
                    break
                time.sleep(0.5)
            if hit is None:
                log(f"   ❓ {core.SLIDER_APPEAR_TIMEOUT}s 内屏幕上未找到滑块"
                    f"（检查：屏幕录制权限 / 抓取窗口是否在主屏且未被遮挡 / 模板是否匹配）")
                try:
                    solver._save_debug("notfound")
                except Exception:
                    pass
                return "not_found"
            try:
                res = solver.solve(hit)
            except w._failsafe_exc:
                log("   ✋ 检测到鼠标甩到屏幕角落（FailSafe），本轮停用自动拖拽，请手动完成。")
                w.enabled = False
                return "aborted"
            except Exception as e:
                log(f"   ❌ 拖拽过程异常: {e}")
                w.stats["failed"] += 1
                return "failed"
            if res.status == getattr(w._sv, "STATUS_NOT_FOUND", "not_found"):
                log(f"   ℹ️ {res.message}")
                return "solved"          # 滑块已不在：交给页面状态判定
            if res.solved:
                w.stats["solved"] += 1
                log(f"   ✅ 滑块验证已通过（拖拽 {res.attempts} 次）")
                w.restore_terminal()
                return "solved"
            w.stats["failed"] += 1
            log(f"   ❌ 滑块验证未通过: {res.message}")
            return "failed"
        finally:
            self.lock.release()


# ================= 任务状态机 =================
class Job:
    def __init__(self, task_list, alias_to_symbol, mw_overrides, last_valid_date, opts, slider):
        self.lock = threading.RLock()
        self.opts = opts
        self.lvd = last_valid_date
        self.slider = slider
        self.tasks = []
        for sym, group, handler in task_list:
            cands = core.resolve_mw_candidates(sym, group, handler, alias_to_symbol, mw_overrides)
            labels = [core.candidate_label(handler, a, p) for a, p, _ in cands]
            self.tasks.append({"symbol": sym, "group": group, "handler": handler,
                               "cands": cands, "labels": labels})
        self.total = len(self.tasks)
        self.ti = 0            # 当前 symbol 下标
        self.ci = 0            # 当前候选地址下标
        self.fails = 0         # 当前候选的失败次数（冷却不计入）
        self.hints = []
        self.pending = None
        self.seq = 0
        self.stats = {"success": [], "failed": [], "not_found": [], "skipped": [], "aborted": False}
        self.ctx = {"fingerprints": {}}
        self.throttle = core.AdaptiveThrottle()
        self.nav_since_break = 0
        self.next_break = random.randint(*core.LONG_BREAK_EVERY)
        self.next_delay = 0.0
        self.hard_blocks = 0
        self.hard_streak = 0
        self.cooldown_until = 0.0
        self.in_cooldown = False
        self.finished = False
        self.done_delivered = False
        self.abort_reason = None
        self.session = None
        self.last_seen = time.time()
        self.hello_event = threading.Event()
        self.done_event = threading.Event()
        self.started_at = None
        self.processed = 0

    # ---------- 工具 ----------
    def _cur(self):
        return self.tasks[self.ti] if self.ti < self.total else None

    def _session_ok(self, data):
        return self.session is not None and data.get("session") == self.session

    def brief(self):
        t = self._cur()
        return {"total": self.total, "done": self.processed,
                "success": len(self.stats["success"]), "failed": len(self.stats["failed"]),
                "not_found": len(self.stats["not_found"]), "skipped": len(self.stats["skipped"]),
                "current": f"{t['symbol']} [{t['group']}]" if t else "",
                "cooldown_left": int(max(0.0, self.cooldown_until - time.time())),
                "hard_blocks": self.hard_blocks}

    def _done_msg(self):
        self.done_delivered = True
        return {"action": "done", "summary": self.brief(),
                "aborted": self.stats["aborted"], "reason": self.abort_reason}

    def _finish(self):
        if not self.finished:
            self.finished = True
            self.pending = None
            self.done_event.set()

    def _abort(self, reason):
        if not self.finished:
            self.stats["aborted"] = True
            self.abort_reason = reason
            log(f"🛑 {reason}，终止本轮（剩余 symbol 保留在 JSON，稍后重跑即可续抓）。")
        self._finish()

    def _finish_task(self, outcome):
        t = self._cur()
        self.stats[outcome].append(f"{t['group']}:{t['symbol']}")
        self.processed += 1
        self.ti += 1
        self.ci = 0
        self.fails = 0
        self.hints = []

    def _schedule_delay(self, extra=0.0):
        if self.finished:
            return
        delay = random.uniform(*core.NAV_DELAY_RANGE) * self.throttle.scale + extra
        if self.nav_since_break >= self.next_break:
            secs = random.uniform(*core.LONG_BREAK_SECONDS)
            log(f"☕ 已连续访问 {self.nav_since_break} 个页面，休息 {secs:.0f} 秒（降低被风控概率）")
            delay += secs
            self.nav_since_break = 0
            self.next_break = random.randint(*core.LONG_BREAK_EVERY)
        self.next_delay = delay

    # ---------- API ----------
    def hello(self, data):
        with self.lock:
            if data.get("protocol") != PROTOCOL_VERSION:
                return {"ok": False, "error": f"扩展协议版本 {data.get('protocol')} 与桥接程序 {PROTOCOL_VERSION} 不一致，"
                                              f"请在 chrome://extensions 中重新加载扩展"}
            first = self.session is None
            self.session = secrets.token_hex(8)
            self.last_seen = time.time()
            if first:
                self.started_at = time.time()
                log(f"🔌 Chrome 扩展已连接（v{data.get('version')}），开始抓取")
            else:
                log("🔌 扩展重新连接（新的控制台会话），从当前进度继续")
            self.hello_event.set()
            return {"ok": True, "session": self.session, "total": self.total,
                    "last_valid_date": self.lvd, "unattended": core.UNATTENDED,
                    "slider": bool(self.slider and self.slider.available),
                    "slider_rounds": core.AUTO_SLIDER_MAX_ROUNDS,
                    "dry_run": self.opts["dry_run"], "keep_window": self.opts["keep_window"],
                    "window": WORKER_WINDOW}

    def next(self, data):
        with self.lock:
            if not self._session_ok(data):
                return {"action": "superseded"}
            self.last_seen = time.time()
            if self.finished:
                return self._done_msg()
            rem = self.cooldown_until - time.time()
            if rem > 0:
                return {"action": "wait", "ms": int(min(rem, WAIT_CHUNK_SECONDS) * 1000),
                        "reason": f"访问受限冷却中，剩余约 {rem / 60:.1f} 分钟", "summary": self.brief()}
            if self.in_cooldown:
                self.in_cooldown = False
                log("   ▶️ 冷却结束，继续抓取")
            if self.pending:     # 控制台重连等情况：重新下发同一任务
                return dict(self.pending, delay_ms=0, summary=self.brief())

            while self.ti < self.total and not self.tasks[self.ti]["cands"]:
                t = self.tasks[self.ti]
                log(f"❓ [{t['symbol']}] 分组 {t['group']} 无法推导 MarketWatch 地址，请在 Symbol_mapping_mw.json 中添加。")
                self._finish_task("not_found")
            if self.ti >= self.total:
                self._finish()
                return self._done_msg()

            t = self.tasks[self.ti]
            handler = t["handler"]
            asset, mw_path, extra_q = t["cands"][self.ci]
            mode = "table" if handler["parser"] == "ohlcv_table" else "quote"
            if self.ci == 0 and self.fails == 0:
                first = t["labels"][0]
                arrow = f" (→ {first})" if first != t["symbol"].lower() else ""
                log(f"▶ [{self.ti + 1}/{self.total}] {t['symbol']}{arrow} [{t['group']}]")
            self.seq += 1
            self.pending = {
                "action": "task", "task_id": self.seq,
                "symbol": t["symbol"], "group": t["group"], "label": t["labels"][self.ci],
                "url": core.build_target_url(handler, asset, mw_path, extra_q),
                "mode": mode, "mw_path": mw_path,
                "expect_seg": mw_path if mode == "table" else "",
                "expect_type": core.expected_type_for(handler, asset) or "",
                "max_rows": core.MAX_ROWS_TO_EXTRACT,
                "wait_ms": NAV_WAIT_SECONDS * 1000,
                "manual_wait_ms": core.CAPTCHA_MANUAL_WAIT * 1000,
                "index": self.ti + 1, "total": self.total,
            }
            delay, self.next_delay = self.next_delay, 0.0
            return dict(self.pending, delay_ms=int(delay * 1000), summary=self.brief())

    def result(self, data):
        with self.lock:
            if not self._session_ok(data):
                return {"ok": False, "action": "superseded"}
            self.last_seen = time.time()
            p = self.pending
            if not p or data.get("task_id") != p["task_id"] or self.finished:
                return {"ok": False, "error": "过期的任务结果，已忽略", "summary": self.brief()}
            self.pending = None
            self.nav_since_break += 1
            t = self._cur()
            state = str(data.get("state") or "error")
            extra = 0.0
            if state == "ready":
                extra = self._on_ready(t, p, data)
            elif state in ("notfound", "mismatch", "wrong_symbol"):
                self._on_notfound(t, p, data, state)
            elif state in ("blocked", "captcha_failed", "captcha_timeout"):
                self._on_block(t, state)
            elif state == "stopped":
                self._abort("用户在扩展中点击了停止")
            else:
                msg = STATE_TEXT.get(state, state)
                if data.get("error"):
                    msg += f"：{data.get('error')}"
                extra = self._retry(t, msg, stale=(state == "stale"))
            self._schedule_delay(extra)
            return {"ok": True, "summary": self.brief()}

    def captcha(self, data):
        phase = data.get("phase")
        with self.lock:
            if not self._session_ok(data):
                return {"ok": False, "action": "superseded"}
            self.last_seen = time.time()
            t = self._cur()
            sym = t["symbol"] if t else "?"
            if phase == "detected":
                self.throttle.on_block()
                log(f"🧩 [{sym}] 检测到滑块验证")
                return {"ok": True}
            if phase == "manual":
                if self.slider:
                    self.slider.note_manual()
                log(f"🧩 [{sym}] 请在 Chrome 抓取窗口中手动完成验证（最多等待 {core.CAPTCHA_MANUAL_WAIT} 秒）...")
                core.notify_mac("MarketWatch 需要人工完成验证，请切到 Chrome 抓取窗口处理")
                return {"ok": True}
            if phase == "resolved":
                log("   ✅ 验证已完成，继续抓取")
                return {"ok": True}
        if phase == "solve":   # 拖拽耗时较长，不持有任务锁
            log(f"🧩 [{sym}] 开始自动拖拽滑块...")
            result = self.slider.solve() if (self.slider and self.slider.available) else "unavailable"
            with self.lock:
                self.last_seen = time.time()
            return {"ok": True, "result": result}
        return {"ok": False, "error": f"未知 phase: {phase}"}

    def ping(self, data):
        with self.lock:
            if self._session_ok(data):
                self.last_seen = time.time()
            return {"ok": True}

    def stop(self, data):
        with self.lock:
            if self._session_ok(data):
                self._abort("用户在扩展中点击了停止")
            return {"ok": True}

    def ext_log(self, data):
        msg = str(data.get("msg") or "")[:500]
        if msg:
            log(f"   [扩展] {msg}")
        return {"ok": True}

    # ---------- 结果处理（逻辑与 MW_Today.run_single_url 一致） ----------
    def _retry(self, t, msg, stale=False):
        self.fails += 1
        sym = t["symbol"]
        if self.fails >= core.MAX_RETRIES:
            if stale:
                log(f"❌ [{sym}] 防串页校验未通过 (已重试 {core.MAX_RETRIES} 次)，不写入，保留在 JSON: {msg}")
            else:
                log(f"❌ [{sym}] 抓取失败 (已重试 {core.MAX_RETRIES} 次): {msg[:150]}")
            self._finish_task("failed")
            return 0.0
        log(f"⏳ [{sym}] 第 {self.fails} 次抓取未成功，准备重试: {msg[:120]}")
        return 1.5 * self.fails + random.uniform(0, 1)

    def _on_ready(self, t, p, data):
        sym, group, handler = t["symbol"], t["group"], t["handler"]
        payload = data.get("payload") or {}
        self.hard_streak = 0
        page_info = ""
        try:
            if p["mode"] == "table":
                rows = core.rows_from_table_result(payload, sym, expect_seg=p["mw_path"])
                if not rows:
                    raise core.ScrapeError("提取到的数据为空")
                core.check_and_register_fingerprint(self.ctx, core.table_fingerprint(rows), sym, group)
                row, note = core.select_row(rows, self.lvd)
            else:
                quote = core.quote_from_result(payload)
                core.check_and_register_fingerprint(self.ctx, core.quote_fingerprint(quote), sym, group)
                row, note = core.build_quote_row(sym, handler, quote, self.lvd)
                page_info = (f"（页面: {quote.get('company') or '-'} | 原始值: {quote.get('price_raw')} "
                             f"| 更新: {quote.get('ts') or '-'}）")
        except core.StalePageError as e:
            return self._retry(t, str(e), stale=True)
        except core.ScrapeError as e:
            return self._retry(t, str(e))
        except Exception as e:
            return self._retry(t, f"解析异常: {e}")

        if note:
            log(f"⚠️ [{sym}] {note}")
        if row is None:
            self._finish_task("skipped")
            return 0.0

        if self.opts["sanity"] and handler.get("sanity"):
            ok, msg = core.check_price_sanity(group, sym, row[0], row[2])
            if not ok:
                if core.PRICE_SANITY_ACTION == "skip":
                    log(f"🚫 [{sym}] {msg}，疑似映射错误或单位不一致，跳过（保留在 JSON）。{page_info}\n"
                        f"   URL: {p['url']}  （确认无误可用 --no-sanity 重跑）")
                    self._finish_task("skipped")
                    return 0.0
                log(f"⚠️ [{sym}] {msg}（仅提示，继续写入）")

        detail = f"{row[0]} | price={row[2]} vol={row[3]} O={row[4]} H={row[5]} L={row[6]}"
        if self.opts["dry_run"]:
            core.record_wrong_symbol_if_exceeded(group, sym, row[0], row[2], dry_run=True)
            log(f"🔍 [DRY-RUN] [{sym}] -> {group}: {detail} {page_info}\n   URL: {p['url']}")
            self.throttle.on_success()
            self._finish_task("success")
            return 0.0

        if not core.insert_data_to_db(core.DB_PATH, group, [row], core.get_table_type(group)):
            return self._retry(t, "数据库写入失败")
        core.remove_symbol_from_json(core.SECTORS_JSON_PATH, group, sym)
        core.record_wrong_symbol_if_exceeded(group, sym, row[0], row[2], dry_run=False)
        log(f"✅ [{sym}] 成功写入 1 条数据 ({detail}) 到 {group} 表。{page_info}")
        self.throttle.on_success()
        self._finish_task("success")
        return 0.0

    def _on_notfound(self, t, p, data, state):
        sym = t["symbol"]
        final_url = data.get("final_url") or ""
        if state == "mismatch":
            actual = core._body_type_from_class(data.get("body_class") or "")
            desc = f"页面品种类型为 '{actual or '?'}'，与预期 '{p['expect_type'] or '?'}' 不符: {final_url}"
        elif state == "wrong_symbol":
            desc = f"页面 URL 中的代码与预期 '{p['mw_path']}' 不符（可能被重定向到其它代码）: {final_url}"
        else:
            desc = f"页面不存在或被重定向: {final_url}"
        log(f"❓ [{sym}] MarketWatch 未找到: {desc[:200]}")
        if state in ("mismatch", "wrong_symbol"):
            hint = core.suggest_override_from_url(final_url)
            if hint:
                self.hints.append(hint)
        self.hard_streak = 0
        self.ci += 1
        self.fails = 0
        if self.ci < len(t["cands"]):
            log(f"   ↪ [{sym}] 尝试下一个候选地址: {t['labels'][self.ci]}")
            return
        log(f"   [{sym}] 所有候选地址均未找到（{', '.join(t['labels'])}），可在 Symbol_mapping_mw.json 中添加映射。")
        for hint in dict.fromkeys(self.hints):
            log(f"   💡 建议映射: {{\"{t['group']}\": {{\"{sym}\": \"{hint}\"}}}}")
        self._finish_task("not_found")

    def _on_block(self, t, state):
        """与 MW_Today.handle_hard_block 一致，但不阻塞：设置 cooldown_until，由扩展轮询等待"""
        sym = t["symbol"]
        reason = {"blocked": "页面显示访问受限（硬封禁页，没有可拖拽的滑块）",
                  "captcha_failed": "无人值守模式下滑块未能自动通过",
                  "captcha_timeout": "验证码等待超时"}[state]
        self.throttle.on_block()
        self.hard_blocks += 1
        streak = self.hard_streak
        self.hard_streak += 1
        core.save_block_state(last_block_ts=time.time(), last_symbol=sym, reason=reason, engine="extension",
                              last_block_at=datetime.datetime.now().isoformat(timespec="seconds"))
        if streak >= len(core.HARD_BLOCK_COOLDOWN_MINUTES) or self.hard_blocks > core.HARD_BLOCK_MAX_PER_RUN:
            core.notify_mac("MarketWatch 多次冷却后仍被拦截，本轮已终止，剩余项保留在 JSON")
            self._abort(f"[{sym}] {reason}；已连续冷却 {streak} 次 / 本轮累计被封 {self.hard_blocks} 次")
            return
        minutes = core.HARD_BLOCK_COOLDOWN_MINUTES[streak] * random.uniform(
            1 - core.HARD_BLOCK_JITTER, 1 + core.HARD_BLOCK_JITTER)
        self.cooldown_until = time.time() + minutes * 60
        self.in_cooldown = True
        log(f"🧊 [{sym}] {reason}\n   第 {streak + 1}/{len(core.HARD_BLOCK_COOLDOWN_MINUTES)} 次冷却 "
            f"{minutes:.0f} 分钟，期间不访问 MarketWatch，结束后自动续抓（Ctrl+C 可中止）")
        core.notify_mac(f"MarketWatch 访问受限，冷却 {minutes:.0f} 分钟后自动继续")
        self.throttle.set_floor(2.0 + streak)
        self.nav_since_break = 0

    def print_summary(self):
        s = self.stats
        log(f"📊 统计：成功 {len(s['success'])} | 失败 {len(s['failed'])} | "
            f"未找到 {len(s['not_found'])} | 跳过 {len(s['skipped'])}")
        if self.processed and self.started_at:
            el = time.time() - self.started_at
            log(f"⏱️ 总耗时 {el:.1f}s，平均 {el / self.processed:.2f} 秒/个（含间隔、休息与冷却）")
        if self.hard_blocks:
            log(f"🧊 本轮共触发访问受限 {self.hard_blocks} 次（若频繁出现，请调大 MW_Today.NAV_DELAY_RANGE）")
        for key, label in (("failed", "失败"), ("not_found", "未找到"), ("skipped", "跳过")):
            if s[key]:
                log(f"   {label}列表: {', '.join(s[key])}")
        if self.slider:
            sm = self.slider.summary()
            if sm:
                log(sm)


# ================= HTTP 服务 =================
START_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="mw-bridge-token" content="{token}"><meta name="mw-bridge-auto" content="{auto}">
<title>MW Bridge</title></head>
<body style="font:14px -apple-system,sans-serif;margin:40px">
<h3>MW Bridge 已启动（端口 {port}）</h3>
<p id="status">正在把任务交给 Chrome 扩展「MW Daily Helper」……<br>
若此页面一直不消失：请确认已在 chrome://extensions 中加载并启用该扩展，且当前 Chrome 用户就是安装扩展的那个。</p>
</body></html>"""


def build_handler(job, token):
    routes = {"/api/hello": job.hello, "/api/next": job.next, "/api/result": job.result,
              "/api/captcha": job.captcha, "/api/ping": job.ping, "/api/stop": job.stop,
              "/api/log": job.ext_log}

    class Handler(BaseHTTPRequestHandler):
        server_version = "MWBridge/1"

        def log_message(self, fmt, *args):
            pass

        def _host_ok(self):
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"ok": False, "error": "bad host"})
            u = urllib.parse.urlparse(self.path)
            if u.path == "/health":
                return self._json(200, {"ok": True, "app": "mw_bridge", "protocol": PROTOCOL_VERSION,
                                        "finished": job.finished, "connected": job.session is not None,
                                        "summary": job.brief()})
            if u.path == "/start":
                q = urllib.parse.parse_qs(u.query)
                html = START_PAGE.format(token=token, port=self.server.server_address[1],
                                         auto="1" if q.get("auto", ["0"])[0] == "1" else "0")
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if u.path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            return self._json(404, {"ok": False})

        def do_OPTIONS(self):
            self._json(403, {"ok": False})   # 不提供 CORS：普通网页无法调用本接口

        def do_POST(self):
            if not self._host_ok():
                return self._json(403, {"ok": False, "error": "bad host"})
            origin = self.headers.get("Origin", "")
            if origin and not origin.startswith("chrome-extension://"):
                return self._json(403, {"ok": False, "error": "bad origin"})
            got = (self.headers.get("X-MW-Token") or "").encode("utf-8", "ignore")
            if not secrets.compare_digest(got, token.encode()):
                return self._json(401, {"ok": False, "error": "bad token"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n > MAX_BODY_BYTES:
                return self._json(413, {"ok": False})
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
            except Exception:
                return self._json(400, {"ok": False, "error": "bad json"})
            fn = routes.get(urllib.parse.urlparse(self.path).path)
            if fn is None:
                return self._json(404, {"ok": False})
            try:
                return self._json(200, fn(data))
            except Exception as e:
                log(f"❌ 桥接处理异常: {e}\n{traceback.format_exc()}")
                return self._json(500, {"ok": False, "error": str(e)})

    return Handler


def make_server(job, token):
    handler = build_handler(job, token)
    for i in range(PORT_FALLBACK_TRIES):
        port = BRIDGE_PORT + i
        try:
            srv = ThreadingHTTPServer((BRIDGE_HOST, port), handler)
            srv.daemon_threads = True
            return srv, port
        except OSError:
            continue
    raise RuntimeError(f"端口 {BRIDGE_PORT}~{BRIDGE_PORT + PORT_FALLBACK_TRIES - 1} 均被占用")


def open_in_chrome(url, background=True):
    try:
        if core.IS_MAC:
            cmd = ["open"] + (["-g"] if background else []) + ["-a", CHROME_APP, url]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                log(f"⚠️ 无法用 {CHROME_APP} 打开 {url}: {r.stderr.strip()[:200]}")
            return r.returncode == 0
        return webbrowser.open(url)
    except Exception as e:
        log(f"⚠️ 打开浏览器失败: {e}")
        return False


def acquire_instance_lock():
    if core.fcntl is None:
        return True
    fh = open(INSTANCE_LOCK_PATH, "a")
    try:
        core.fcntl.flock(fh.fileno(), core.fcntl.LOCK_EX | core.fcntl.LOCK_NB)
        return fh
    except OSError:
        fh.close()
        return None


# ================= 主流程 =================
def run(args):
    """返回 (stats, connected)"""
    empty = {"success": [], "failed": [], "not_found": [], "skipped": [], "aborted": False}
    tasks_dict = core.load_tasks_from_json(core.SECTORS_JSON_PATH)
    alias_to_symbol = core.load_alias_mapping(core.SYMBOL_MAPPING_PATH)
    mw_overrides = core.load_mw_overrides(core.MW_SYMBOL_OVERRIDE_PATH)

    lvd = core.get_last_valid_trading_date()
    log(f"📅 计算得出的最近有效开盘日为: {lvd}" if lvd else "⚠️ 无法计算最近有效开盘日，将使用网页原始日期。")

    task_list, unknown = core.build_task_list(tasks_dict, args.groups)
    for g, n in unknown.items():
        log(f"⏭️  分组 [{g}] 有 {n} 个待抓取项，不在本爬虫支持范围内，跳过。")
    if not task_list:
        log("✅ 支持的分组中没有待抓取的 Symbol，任务结束。")
        return empty, True

    recently_blocked = core.wait_startup_grace(ignore=args.ignore_cooldown)

    slider = SliderHelper(enabled=(not args.no_auto_slider) and core.AUTO_SLIDER_ENABLED)
    opts = {"dry_run": args.dry_run, "sanity": not args.no_sanity, "keep_window": args.keep_window}
    job = Job(task_list, alias_to_symbol, mw_overrides, lvd, opts, slider)
    if recently_blocked:
        job.throttle.set_floor(2.0)
        log(f"   🐢 {core.RECENT_BLOCK_HOURS} 小时内曾被拦截，本轮请求间隔从 ×2.0 起步")

    log(f"共加载 {len(task_list)} 个待抓取任务。（引擎: Chrome 扩展"
        f"{' | DRY-RUN 不写库' if args.dry_run else ''}{' | 已关闭价格校验' if args.no_sanity else ''}"
        f"{' | 滑块自动验证' if slider.available else ' | 滑块需手动'}{' | 无人值守' if core.UNATTENDED else ''}）")
    log(f"⏱️ 预计耗时约 {len(task_list) * core.EST_SECONDS_PER_SYMBOL / 60:.0f} 分钟（不含可能的冷却时间）")

    token = secrets.token_urlsafe(24)
    server, port = make_server(job, token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    start_url = f"http://127.0.0.1:{port}/start?auto={0 if args.no_open else 1}"
    bg = not core.UNATTENDED
    log(f"🌉 桥接服务已启动: http://127.0.0.1:{port}")

    connected = False
    try:
        # ---- 等待扩展连接 ----
        t0 = time.time()
        reopened = False
        if args.no_open:
            log(f"🔗 请在 Chrome 中点击扩展图标「MW Daily Helper」→「开始」（端口 {port}），或手动打开 {start_url}")
            timeout = args.hello_timeout or HELLO_TIMEOUT_NO_OPEN
        else:
            open_in_chrome(start_url, background=bg)
            timeout = args.hello_timeout or HELLO_TIMEOUT
        while not job.hello_event.wait(1):
            el = time.time() - t0
            if not args.no_open and not reopened and el > HELLO_REOPEN_AFTER:
                log("⏳ 扩展尚未响应，再唤起一次...")
                open_in_chrome(start_url, background=bg)
                reopened = True
            if el > timeout:
                log("❌ Chrome 扩展未连接。请检查：1) chrome://extensions 中已加载并启用 MW Daily Helper；"
                    "2) 扩展安装在 Chrome 最近使用的那个用户 Profile 中；3) 扩展被更新后需要点「重新加载」。")
                core.notify_mac("MW 扩展未连接，请检查 Chrome 扩展是否启用")
                job.stats["aborted"] = True
                return job.stats, False
        connected = True

        # ---- 运行中：心跳监控 ----
        reopened_at = None
        while not job.done_event.wait(2):
            idle = time.time() - job.last_seen
            if idle <= HEARTBEAT_TIMEOUT:
                reopened_at = None
                continue
            if reopened_at is None:
                log(f"⚠️ 扩展已 {idle:.0f} 秒无响应（控制台页可能被关闭或被冻结），尝试重新唤起...")
                open_in_chrome(start_url.replace("auto=0", "auto=1"), background=bg)
                reopened_at = time.time()
            elif time.time() - reopened_at > HELLO_TIMEOUT:
                with job.lock:
                    job._abort("Chrome 扩展长时间无响应")
                connected = False
        # 等扩展取走 done 指令（以便它关闭抓取窗口）
        t1 = time.time()
        while not job.done_delivered and time.time() - t1 < DONE_LINGER_SECONDS:
            time.sleep(0.3)
    finally:
        server.shutdown()
        server.server_close()
        log("🎉 所有任务执行完毕。")
        job.print_summary()
    return job.stats, connected


def parse_args():
    ap = argparse.ArgumentParser(description="MarketWatch 每日数据抓取（Chrome 扩展版桥接程序）")
    ap.add_argument("--groups", nargs="+", default=None, help="只抓取指定分组")
    ap.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写数据库、不修改 JSON")
    ap.add_argument("--no-sanity", action="store_true", help="关闭价格偏差合理性校验")
    ap.add_argument("--no-check", action="store_true", help="结束后不调用 Check_yesterday.py")
    ap.add_argument("--no-auto-slider", action="store_true", help="关闭滑块自动验证（只能手动）")
    ap.add_argument("--ignore-cooldown", action="store_true", help="忽略启动时的冷却等待")
    ap.add_argument("--no-open", action="store_true", help="不自动唤起 Chrome，等待在扩展弹窗中点击「开始」")
    ap.add_argument("--keep-window", action="store_true", help="结束后不关闭扩展打开的抓取窗口")
    ap.add_argument("--hello-timeout", type=int, default=0, help="等待扩展连接的秒数（默认自动）")
    # 兼容旧参数（流水线里可能仍带着），无实际作用
    ap.add_argument("--headful", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-fast", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-escalate", action="store_true", help=argparse.SUPPRESS)
    return ap.parse_args()


def main():
    args = parse_args()
    lock = acquire_instance_lock()
    if lock is None:
        print("⚠️ 已有 MW_Bridge 在运行，本次退出。", flush=True)
        sys.exit(1)
    core.start_caffeinate()
    exit_code = 0
    try:
        stats, connected = run(args)
        if args.dry_run:
            exit_code = 0 if connected else 3
        else:
            remaining = core.count_remaining_tasks(args.groups)
            if remaining is None:
                exit_code = 1
            elif remaining == 0:
                exit_code = 0
            else:
                exit_code = 2 if connected else 3
            if not args.no_check and remaining == 0:
                core.run_check_yesterday_if_empty()
    except KeyboardInterrupt:
        print("\n⛔ 用户中断 MW_Bridge", flush=True)
        exit_code = 130
    finally:
        core.stop_caffeinate()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()