#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# ================= 配置区 =================
DB_PATH   = Path("/Users/yanzhang/Coding/Database/Finance.db")
JSON_PATH = Path("/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json")
SYMBOL    = "KLAR"
KEEP_TABLE = "Financial_Services"   # 保留的表
DELETE_FROM = ["Technology"]   # 只从这些表中删除 KLAR
SYMBOL_COL = "name"                 # 存放代码的列名（你的结构里是 name）
DRY_RUN    = True                   # True=只演练不删除；确认无误后改为 False
# ==========================================

LOG_DIR = DB_PATH.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
run_time = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"cleanup_{SYMBOL}_{run_time}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"),
              logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def check_json_group(symbol: str) -> list[str]:
    """从 JSON 中找出 symbol 属于哪些分组"""
    with open(JSON_PATH, encoding="utf-8") as f:
        sectors = json.load(f)
    groups = [g for g, syms in sectors.items() if symbol in syms]
    log.info("JSON 中 %s 所属分组: %s", symbol, groups)
    return groups


def backup_db() -> Path:
    """删除前备份数据库"""
    backup = DB_PATH.with_name(f"{DB_PATH.stem}_backup_{run_time}.db")
    shutil.copy2(DB_PATH, backup)
    log.info("已备份数据库到: %s", backup)
    return backup


def get_tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [r[0] for r in rows]


def has_column(conn, table: str, col: str) -> bool:
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    return col in cols


def main():
    log.info("========== 开始执行 | SYMBOL=%s | DRY_RUN=%s ==========", SYMBOL, DRY_RUN)

    # 1. 校验 JSON 分组
    groups = check_json_group(SYMBOL)
    if KEEP_TABLE not in groups:
        log.warning("JSON 中 %s 不在 %s 分组下，请确认后再继续！", SYMBOL, KEEP_TABLE)

    # 2. 备份
    if not DRY_RUN:
        backup_db()

    conn = sqlite3.connect(DB_PATH)
    try:
        # 3. 扫描所有表
        hits = {}  # table -> 行数
        for t in get_tables(conn):
            if not has_column(conn, t, SYMBOL_COL):
                log.debug("跳过 %s（无 %s 列）", t, SYMBOL_COL)
                continue
            cnt = conn.execute(
                f'SELECT COUNT(*) FROM "{t}" WHERE "{SYMBOL_COL}" = ?', (SYMBOL,)
            ).fetchone()[0]
            if cnt > 0:
                hits[t] = cnt
                log.info("表 %-25s 中 %s 共 %d 行", t, SYMBOL, cnt)

        log.info("KLAR 存在的表: %s", list(hits.keys()))

        if len(hits) <= 1:
            log.info("%s 只存在于 %d 个表中，无需清理。", SYMBOL, len(hits))
            return

        if KEEP_TABLE not in hits:
            log.error("%s 表中没有 %s 数据，为安全起见中止操作！", KEEP_TABLE, SYMBOL)
            return

        # 4. 确定要删除的表（只删 DELETE_FROM 中指定的表）
        targets = [t for t in DELETE_FROM if t in hits]
        missing = [t for t in DELETE_FROM if t not in hits]
        if missing:
            log.warning("以下表中没有 %s，跳过：%s", SYMBOL, missing)
        if not targets:
            log.info("没有需要删除的目标表，结束。")
            return

        keep = {t: c for t, c in hits.items() if t not in targets}
        log.info("将保留（不改动）: %s", keep)
        log.info("将从以下表中删除 %s：", SYMBOL)
        for t in targets:
            log.info("  - %s (%d 行)", t, hits[t])

        if DRY_RUN:
            log.info("DRY_RUN 模式，未做任何修改。确认无误后将 DRY_RUN 改为 False 再运行。")
            return

        # 5. 执行删除（事务，出错自动回滚）
        with conn:
            for t in targets:
                cur = conn.execute(
                    f'DELETE FROM "{t}" WHERE "{SYMBOL_COL}" = ?', (SYMBOL,)
                )
                log.info("已从 %s 删除 %d 行", t, cur.rowcount)

        # 6. 校验
        for t in targets:
            left = conn.execute(
                f'SELECT COUNT(*) FROM "{t}" WHERE "{SYMBOL_COL}" = ?', (SYMBOL,)
            ).fetchone()[0]
            status = "通过" if left == 0 else "失败"
            log.info("校验 %s: 剩余 %d 行 -> %s", t, left, status)

        conn.execute("VACUUM")  # 可选：回收空间
        log.info("删除完成。日志文件: %s", LOG_FILE)

    except Exception:
        log.exception("执行出错，事务已回滚，数据库未被修改")
    finally:
        conn.close()
        log.info("========== 执行结束 ==========")


if __name__ == "__main__":
    main()