# -*- coding: utf-8 -*-
"""
=====================================================================
 多应用服务器  (OVideo / ONews / Finance / Prediction)
=====================================================================
 文件结构（修改某模块时，只需把对应的节喂给 AI）：
   §1  公共基础（三者共用）
   §2A ONews + OVideo 共用：点数账本 / 邀请码
   §2B 在线客服会话（OVideo 寻片/举报 + ONews/Finance 在线客服）
   §3  OVideo 视频（独享）
   §4  ONews 新闻（独享）
   §5  Finance 美股（独享）
   §6  后台网页 ADMIN_HTML（原样粘贴）
   §7  启动入口

 改 OVideo  → §1 + §2A + §2B + §3
 改 ONews   → §1 + §2A + §4        （涉及客服再加 §2B）
 改 Finance → §1 + §5              （涉及客服再加 §2B）
=====================================================================
"""
import os
import re
import sys
import hmac
import json
import time
import sqlite3
import secrets
import hashlib
import threading
import traceback
from difflib import SequenceMatcher
from functools import wraps
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, send_from_directory, request, g
from flask_cors import CORS
from flask_compress import Compress
from werkzeug.utils import safe_join


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  §1 公共基础（OVideo / ONews / Finance 三者共用）                       ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ---------------- §1.1 Flask 实例 ----------------
app = Flask(__name__)
CORS(app)
Compress(app)          # Gzip 压缩（application/json, text/csv 等）

# ---------------- §1.2 全局配置 ----------------
# 以北京时间作为"每日免费次数"的统一基准，不依赖服务器系统时区
APP_TZ = timezone(timedelta(hours=8))

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))     # LocalServer
PARENT_DIR = os.path.dirname(CURRENT_DIR)                     # /root 或 /Users/yanzhang/Coding
BASE_RESOURCES_DIR = os.path.join(CURRENT_DIR, 'Resources')
USER_DB_PATH = os.path.join(PARENT_DIR, 'user_data.db')
ANALYTICS_DB_PATH = os.path.join(PARENT_DIR, 'analytics.db')

ALLOWED_APPS = ['ONews', 'Finance', 'Prediction', 'OVideo']

# 订阅：客户端上报的到期时间允许的最大跨度（天）。超过即视为伪造/后门时间。
MAX_SUBSCRIPTION_HORIZON_DAYS = 400
# 永久 VIP 的对外哨兵值（只由服务器根据 is_permanent 生成，绝不接受客户端写入）
PERMANENT_SENTINEL = "2099-12-31T23:59:59Z"
# 兼容老客户端的 {"days": 30} 充值方式（False = 关闭白嫖漏洞）
ALLOW_LEGACY_DAYS_GRANT = False

# 永久 VIP 邀请码  格式: "邀请码": "备注"   ⚠️ 请改掉
VALID_INVITE_CODES = {
    "ONEWS_FAMILY_2024": "Family Access",
    "VIP_FRIEND_888": "Friend Access",
    "DEV_TEST_KEY": "Developer Key"
}

# 视频模块黑名单：这些用户即使是永久 VIP 也看不到视频模块（auth/status 也会下发）
VIDEO_MODULE_BLOCKED_USERS = {
    "001356.cdec6d350edb4646b0130f9363b6d37e.2149",
}

# 播放/阅读/点击的权限来源
ALLOWED_ACCESS_TYPES = {
    'subscription', 'vip_permanent',
    'points', 'points_bonus', 'points_daily', 'points_mixed',
    'free', 'free_day', 'unlocked_today', 'guest',
    'unknown'
}

# 邀请码字母表：去掉 0/O/1/I/L 等易混字符
INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# 活跃用户明细/流水仅保留最近 N 天
ANALYTICS_LOG_KEEP_DAYS = 15
_last_unlock_cleanup_date = None

# ⚠️ 推荐用环境变量设置后台密码：export ADMIN_PASSWORD='你的密码'（不设则用下面的默认值）
ADMIN_PASSWORD_HASH = (os.environ.get('ADMIN_PASSWORD_SHA256') or
                       hashlib.sha256(os.environ.get('ADMIN_PASSWORD', "YourStrongPassword123!").encode()).hexdigest())
ADMIN_TOKENS = {}                    # token -> 过期时间戳（内存，重启失效）
ADMIN_TOKEN_TTL = 7 * 86400          # 后台登录 7 天有效
_admin_login_fail = {}               # ip -> [失败次数, 首次失败时间]

_sub_kind_cache = {}                 # (user_id, app_name) -> (kind, ts)
_SUB_KIND_TTL = 60                   # 秒
_vip_perm_cache = {}                 # user_id -> (bool, ts)   任一 App 永久 VIP（视频屏蔽配置用）
_user_exists_cache = {}              # user_id -> ts           只缓存"存在"的结果
_USER_EXISTS_TTL = 300
_CACHE_MAX = 20000                   # 内存缓存条目上限，超过直接清空

# 下载接口禁止外泄的文件（小写比较；macOS 文件系统大小写不敏感）
DOWNLOAD_DENY_BASENAMES = {
    'url_mapping.json', 'blacklist_url.json', 'blocked_channels.json', 'ovideo.db',
}
DOWNLOAD_DENY_SUFFIXES = ('-wal', '-shm', '-journal', '.building')


# ---------------- §1.3 通用工具 ----------------
def utcnow():
    """带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


def today_str():
    """统一的"自然日"字符串，永远按北京时间 00:00 切分"""
    return datetime.now(APP_TZ).strftime('%Y-%m-%d')


def now_iso():
    """北京时间、不带 +08:00 后缀（naive），保证 SQLite date(created_at) 得到北京自然日"""
    return datetime.now(APP_TZ).replace(tzinfo=None).isoformat()


# fromisoformat() 是 3.7+；strptime 的 %z 在 3.6 不支持 "+08:00"，所以手写解析
_TZ_SUFFIX_RE = re.compile(r'([+-])(\d{2}):?(\d{2})\s*$')
_FRACTION_RE = re.compile(r'\.(\d+)$')


def parse_expiry(value):
    """任意常见格式时间 -> aware UTC datetime；失败返回 None（绝不抛异常）。
       支持：...Z / +00:00 / +0800 / 无时区(按UTC) / 空格分隔 / 微秒 / 仅日期 / datetime 对象 / 2026/10/01"""
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        s = str(value).strip()
        if not s:
            return None

        tz = None
        if s[-1] in ('Z', 'z'):
            s = s[:-1].strip()
            tz = timezone.utc
        else:
            m = _TZ_SUFFIX_RE.search(s)
            # 防止把 "2026-09-22" 的 "-22" 误判成时区
            if m and ('T' in s or ' ' in s):
                sign = 1 if m.group(1) == '+' else -1
                offset = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
                tz = timezone(sign * offset)
                s = s[:m.start()].strip()
        if tz is None:
            tz = timezone.utc

        if 'T' not in s and ' ' in s:
            s = s.replace(' ', 'T', 1)

        fm = _FRACTION_RE.search(s)
        if fm and len(fm.group(1)) > 6:
            s = s[:fm.start()] + '.' + fm.group(1)[:6]

        dt = None
        s2 = s.replace('/', '-')
        for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M',
                    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            for cand in (s, s2):
                try:
                    dt = datetime.strptime(cand, fmt)
                    break
                except ValueError:
                    continue
            if dt is not None:
                break
        if dt is None:
            return None
        return dt.replace(tzinfo=tz).astimezone(timezone.utc)
    except Exception as e:
        print("[parse_expiry][ERROR] %r -> %s" % (value, e))
        return None


def iso_utc(dt):
    """统一对外/入库格式：2026-09-10T06:21:00Z"""
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _row_get(row, key, default=None):
    """sqlite3.Row 安全取值：列不存在时返回默认值"""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _json_body():
    """安全读取 JSON 请求体：空体 / Content-Type 不对 时返回 {} 而不是 400/415"""
    return request.get_json(silent=True) or {}


def _arg_int(name, default, lo=None, hi=None):
    """安全读取整数 query 参数，带上下限"""
    try:
        v = int(request.args.get(name, default))
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _too_frequent(store, key, interval):
    """内存软限流：interval 秒内重复调用返回 True；字典过大时自动清理旧条目"""
    now = time.time()
    if now - store.get(key, 0) < interval:
        return True
    store[key] = now
    if len(store) > 5000:
        cutoff = now - 600
        for k, t in list(store.items()):
            if t < cutoff:
                store.pop(k, None)
    return False

def _cache_put(store, key, value):
    if len(store) > _CACHE_MAX:
        store.clear()
    store[key] = value


_json_file_cache = {}                # path -> (mtime, data)
_json_file_lock = threading.Lock()


def _load_json_cached(path):
    """按 mtime 缓存的 JSON 读取；文件不存在返回 None；读取失败时沿用旧缓存。
       ⚠️ 返回的是共享对象，调用方不要修改它（要改请先 dict() 复制）。"""
    try:
        m = os.path.getmtime(path)
    except OSError:
        return None
    hit = _json_file_cache.get(path)
    if hit and hit[0] == m:
        return hit[1]
    with _json_file_lock:
        hit = _json_file_cache.get(path)
        if hit and hit[0] == m:
            return hit[1]
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[json-cache] 读取 {path} 失败: {e}")
            return hit[1] if hit else None
        _json_file_cache[path] = (m, data)
        return data


def _load_version_json(app_name):
    """Resources/<app>/version.json（缓存）；不存在或格式不对返回 {}"""
    data = _load_json_cached(os.path.join(BASE_RESOURCES_DIR, app_name, 'version.json'))
    return data if isinstance(data, dict) else {}


def _user_exists(uid):
    """Apple 登录用户是否存在于 users 表（命中缓存 5 分钟）；数据库异常会抛出"""
    if not is_real_login_user(uid):
        return False
    now = time.time()
    hit = _user_exists_cache.get(uid)
    if hit and now - hit < _USER_EXISTS_TTL:
        return True
    conn = sqlite3.connect(USER_DB_PATH, timeout=10.0)
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE apple_user_id=?", (uid,)).fetchone() is not None
    finally:
        conn.close()
    if exists:
        _cache_put(_user_exists_cache, uid, now)
    return exists


def _is_admin_request():
    token = request.headers.get('X-Admin-Token') or request.args.get('token')
    if not token:
        return False
    exp = ADMIN_TOKENS.get(token)
    if not exp:
        return False
    if exp < time.time():
        ADMIN_TOKENS.pop(token, None)
        return False
    return True


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _is_admin_request():
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

def is_real_login_user(user_id):
    """只有 Apple 登录用户才享受点数。dev_ 开头是设备标识，guest_user 是兜底。"""
    return bool(user_id) and not user_id.startswith('dev_') and user_id != 'guest_user'


def _query_analytics(sql, params=()):
    """analytics.db 只读查询，撞锁时最多重试 3 次"""
    last_err = None
    for _ in range(3):
        conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError as e:
            last_err = e
            time.sleep(0.2)
        finally:
            conn.close()
    raise last_err


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('X-Admin-Token') or request.args.get('token')
        if not token or token not in ADMIN_TOKENS:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------------- §1.4 订阅身份（埋点/权限共用） ----------------
def get_subscription_kind(user_id, app_name='ONews'):
    """服务器权威判断用户在【该 App】的付费身份：'vip_permanent' / 'subscription' / None
       【修复】① 缓存按 (user_id, app) 区分，不再串 App；
              ② 判定规则与 check_user_subscription_status 一致（只看本 App 的列），
                 和客户端实际拿到的订阅状态一致，埋点不再把"实际扣点"记成 VIP。"""
    if not is_real_login_user(user_id):
        return None
    key = (user_id, app_name)
    hit = _sub_kind_cache.get(key)
    if hit and (time.time() - hit[1]) < _SUB_KIND_TTL:
        return hit[0]
    kind = None
    try:
        conn = sqlite3.connect(USER_DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM users WHERE apple_user_id=?", (user_id,)).fetchone()
        finally:
            conn.close()
        if row:
            ok, exp = check_user_subscription_status(row, app_name)
            if ok:
                kind = 'vip_permanent' if exp == PERMANENT_SENTINEL else 'subscription'
    except Exception as e:
        print(f"[access] 查询订阅身份失败: {e}")
    _cache_put(_sub_kind_cache, key, (kind, time.time()))
    return kind


def _invalidate_sub_cache(user_id):
    if not user_id:
        return
    for a in ALLOWED_APPS:
        _sub_kind_cache.pop((user_id, a), None)
    _vip_perm_cache.pop(user_id, None)
    _user_exists_cache.pop(user_id, None)


def check_user_subscription_status(user_row, app_name):
    """返回 (is_subscribed, expires_at_str)；优先级：is_permanent > expire_at。保证不抛异常。"""
    if user_row is None:
        return False, None
    prefix = app_name.lower()
    perm_col = f"{prefix}_is_permanent"
    expire_col = f"{prefix}_expire_at"
    try:
        if _row_get(user_row, perm_col, 0) in (1, '1', True):
            return True, PERMANENT_SENTINEL
        raw = _row_get(user_row, expire_col)
        if raw:
            dt = parse_expiry(raw)
            if dt is None:
                print(f"[subscription][WARN] 无法解析 {expire_col} = {raw!r}，视为未订阅")
                return False, None
            normalized = iso_utc(dt)
            return (dt > utcnow()), normalized
    except Exception as e:
        traceback.print_exc()
        print(f"[subscription][ERROR] 判定订阅状态异常: {e}")
        return False, None
    return False, None


# ---------------- §1.5 流水清理（三模块流水表） ----------------
def analytics_cutoff_iso(days=ANALYTICS_LOG_KEEP_DAYS):
    """北京时间 N 天前的 naive ISO 字符串，用于与 created_at 比较"""
    return (datetime.now(APP_TZ) - timedelta(days=days)).replace(tzinfo=None).isoformat()


def cleanup_old_event_logs(days_to_keep=ANALYTICS_LOG_KEEP_DAYS):
    """删除 N 天前的三张流水表记录"""
    cutoff = analytics_cutoff_iso(days_to_keep)
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    try:
        c = conn.cursor()
        total = 0
        for table in ('event_logs', 'news_event_logs', 'finance_event_logs'):
            c.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff,))
            total += c.rowcount
        conn.commit()
        if total:
            print(f"[cleanup] 已清理 {total} 条过期流水 (< {cutoff})")
    except Exception as e:
        print(f"[cleanup] 流水清理失败: {e}")
    finally:
        conn.close()


def cleanup_old_unlocks(days_to_keep=7):
    """删除 days_to_keep 天前的视频解锁记录"""
    cutoff = (datetime.now(APP_TZ) - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    try:
        c = conn.cursor()
        c.execute("DELETE FROM video_free_unlocks WHERE unlock_date < ?", (cutoff,))
        deleted = c.rowcount
        conn.commit()
        if deleted:
            print(f"[cleanup] 已清理 {deleted} 条过期解锁记录 (< {cutoff})")
    except Exception as e:
        print(f"[cleanup] 清理失败: {e}")
    finally:
        conn.close()


_cleanup_lock = threading.Lock()


def compact_sqlite(path, force_vacuum=False, min_free_ratio=0.25, min_free_pages=2560):
    """回收磁盘：DELETE 不会让 SQLite 文件变小。
       空闲页 ≥25% 且 ≥约10MB 时 VACUUM；每次都把 -wal 文件截断回 0。"""
    if not os.path.exists(path):
        return
    try:
        conn = sqlite3.connect(path, timeout=60.0, isolation_level=None)
        try:
            pages = conn.execute("PRAGMA page_count").fetchone()[0] or 0
            free = conn.execute("PRAGMA freelist_count").fetchone()[0] or 0
            before = os.path.getsize(path)
            vacuumed = False
            if force_vacuum or (pages and free >= min_free_pages and float(free) / pages >= min_free_ratio):
                conn.execute("VACUUM")
                vacuumed = True
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA optimize")
            if vacuumed:
                print(f"[maintenance] VACUUM {os.path.basename(path)}: "
                      f"{before // 1024} KB -> {os.path.getsize(path) // 1024} KB")
        finally:
            conn.close()
    except Exception as e:
        print(f"[maintenance] 压缩 {path} 失败: {e}")


def _daily_maintenance():
    try:
        cleanup_old_unlocks(days_to_keep=7)
        cleanup_old_event_logs(days_to_keep=ANALYTICS_LOG_KEEP_DAYS)
        compact_sqlite(ANALYTICS_DB_PATH)
        compact_sqlite(USER_DB_PATH)
    except Exception:
        traceback.print_exc()


def maybe_cleanup_old_unlocks():
    """每个北京自然日最多执行一次；放到后台线程跑，不拖慢当前请求"""
    global _last_unlock_cleanup_date
    today = today_str()
    if _last_unlock_cleanup_date == today:
        return
    with _cleanup_lock:
        if _last_unlock_cleanup_date == today:
            return
        _last_unlock_cleanup_date = today
    threading.Thread(target=_daily_maintenance, name='daily-maintenance', daemon=True).start()


# ---------------- §1.6 公共数据库初始化 ----------------
def init_user_db():
    """user_data.db：users 表（Finance 的点数表在 §5 init_finance_user_db）"""
    print(f"检查用户数据库: {USER_DB_PATH}")
    os.makedirs(os.path.dirname(USER_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(USER_DB_PATH, timeout=60.0)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apple_user_id TEXT NOT NULL UNIQUE,
            device_id TEXT,
            created_at TIMESTAMP NOT NULL,
            last_login_at TIMESTAMP,
            finance_expire_at TIMESTAMP,
            finance_is_permanent INTEGER DEFAULT 0,
            onews_expire_at TIMESTAMP,
            onews_is_permanent INTEGER DEFAULT 0,
            prediction_expire_at TIMESTAMP,
            prediction_is_permanent INTEGER DEFAULT 0
        )
    ''')
    for ddl in ('ALTER TABLE users ADD COLUMN device_id TEXT',
                'ALTER TABLE users ADD COLUMN prediction_expire_at TIMESTAMP',
                'ALTER TABLE users ADD COLUMN prediction_is_permanent INTEGER DEFAULT 0'):
        try:
            c.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()
    print("用户数据库已准备就绪。")


def init_anonymous_sub_db():
    print("检查匿名（免登录）订阅表 ...")
    conn = sqlite3.connect(USER_DB_PATH, timeout=60.0)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS anonymous_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app TEXT NOT NULL DEFAULT 'ONews',
            original_transaction_id TEXT NOT NULL,
            device_id TEXT,
            transaction_id TEXT,
            product_id TEXT,
            environment TEXT,
            purchase_date TIMESTAMP,
            expire_at TIMESTAMP,
            app_version TEXT,
            report_count INTEGER DEFAULT 1,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE(app, original_transaction_id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_anon_dev ON anonymous_subscriptions(device_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_anon_exp ON anonymous_subscriptions(expire_at)')
    conn.commit()
    conn.close()
    print("匿名订阅表已就绪。")


def init_analytics_base():
    """analytics.db 开启 WAL（各模块的表在各自节里建）"""
    print(f"检查行为数据库: {ANALYTICS_DB_PATH}")
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.commit()
    conn.close()


# ---------------- §1.7 登录 / 状态 / 兑换 / 付费 / 删号 ----------------
def handle_auth(app_name):
    try:
        data = _json_body()
        user_id = data.get('user_id')
        device_id = data.get('device_id')
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400
        conn = sqlite3.connect(USER_DB_PATH, timeout=60.0)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE apple_user_id = ?", (user_id,)).fetchone()
        now = utcnow().replace(tzinfo=None)   # 存 naive UTC，兼容老数据
        is_subscribed, expiration_date = False, None
        if user:
            c.execute("UPDATE users SET last_login_at = ?, device_id = ? WHERE apple_user_id = ?",
                      (now, device_id, user_id))
            is_subscribed, expiration_date = check_user_subscription_status(user, app_name)
        else:
            c.execute("INSERT INTO users (apple_user_id, device_id, created_at, last_login_at) VALUES (?, ?, ?, ?)",
                      (user_id, device_id, now, now))
        conn.commit()
        conn.close()
        return jsonify({
            "status": "success",
            "is_subscribed": is_subscribed,
            "subscription_expires_at": expiration_date,
            "video_module_blocked": user_id in VIDEO_MODULE_BLOCKED_USERS
        }), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def handle_status_check(app_name):
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
    debug = request.args.get('debug') in ('1', 'true', 'yes') and _is_admin_request()   # 【修复】仅管理员可看调试信息
    conn = None
    try:
        conn = sqlite3.connect(USER_DB_PATH, timeout=60.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE apple_user_id = ?", (user_id,)).fetchone()
        is_subscribed, expires_at_str = check_user_subscription_status(row, app_name)
        payload = {
            "is_subscribed": is_subscribed,
            "subscription_expires_at": expires_at_str,
            "video_module_blocked": user_id in VIDEO_MODULE_BLOCKED_USERS
        }
        if debug:
            prefix = app_name.lower()
            raw = _row_get(row, f"{prefix}_expire_at") if row else None
            parsed = parse_expiry(raw)
            payload["_debug"] = {
                "db_path": USER_DB_PATH,
                "row_found": bool(row),
                "row_id": _row_get(row, 'id') if row else None,
                "checked_columns": [f"{prefix}_expire_at", f"{prefix}_is_permanent"],
                "raw_expire_at": str(raw),
                "raw_type": type(raw).__name__,
                "parsed_expire_at_utc": iso_utc(parsed) if parsed else None,
                "is_permanent_raw": _row_get(row, f"{prefix}_is_permanent", None) if row else None,
                "server_now_utc": iso_utc(utcnow()),
                "python_version": sys.version,
                "has_fromisoformat": hasattr(datetime, 'fromisoformat'),
            }
        print(f"[status] {app_name} user={user_id[:14]}... -> sub={is_subscribed} exp={expires_at_str}")
        resp = jsonify(payload)
        resp.headers['Cache-Control'] = 'no-store, no-cache, max-age=0'
        return resp
    except Exception as e:
        # 出错也返回结构合法的 JSON，避免客户端误判成"服务器不可达"
        traceback.print_exc()
        resp = jsonify({
            "is_subscribed": False,
            "subscription_expires_at": None,
            "video_module_blocked": user_id in VIDEO_MODULE_BLOCKED_USERS,
            "_error": str(e)
        })
        resp.headers['Cache-Control'] = 'no-store, no-cache, max-age=0'
        return resp
    finally:
        if conn is not None:
            conn.close()


def handle_payment(app_name):
    """⚠️ 目前信任客户端上报的到期时间（未做 Apple 票据校验）"""
    data = _json_body()
    user_id = data.get('user_id')
    explicit_expiry = data.get('explicit_expiry')
    days = data.get('days')
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    prefix = app_name.lower()
    expire_col = f"{prefix}_expire_at"
    perm_col = f"{prefix}_is_permanent"

    # 1. 计算目标时间
    if explicit_expiry:
        new_dt = parse_expiry(explicit_expiry)
        if new_dt is None:
            return jsonify({"error": f"invalid explicit_expiry: {explicit_expiry}"}), 400
        # 拒绝 2099 之类的后门时间，否则 is_permanent 改回 0 也降不了权
        if new_dt > utcnow() + timedelta(days=MAX_SUBSCRIPTION_HORIZON_DAYS):
            print(f"[payment][REJECT] {user_id} 上报了超范围到期时间 {explicit_expiry}，已拒绝")
            return jsonify({"error": "expiry out of allowed range"}), 400
    elif days is not None:
        if not ALLOW_LEGACY_DAYS_GRANT:
            return jsonify({"error": "explicit_expiry required"}), 400
        try:
            d = max(1, min(int(days), MAX_SUBSCRIPTION_HORIZON_DAYS))
        except Exception:
            return jsonify({"error": "invalid days"}), 400
        new_dt = utcnow() + timedelta(days=d)
        print(f"[payment][LEGACY] {user_id} 走旧的 days={d} 充值路径")
    else:
        return jsonify({"error": "missing explicit_expiry"}), 400

    # 2. 写库（只允许延长，不允许缩短）
    conn = sqlite3.connect(USER_DB_PATH, timeout=60.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        row = c.execute("SELECT * FROM users WHERE apple_user_id = ?", (user_id,)).fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404
        if _row_get(row, perm_col, 0) in (1, '1', True):
            return jsonify({"status": "success", "is_subscribed": True,
                            "subscription_expires_at": PERMANENT_SENTINEL})
        cur_dt = parse_expiry(_row_get(row, expire_col))
        final_dt = new_dt if (cur_dt is None or new_dt > cur_dt) else cur_dt
        final_str = iso_utc(final_dt)
        c.execute(f"UPDATE users SET {expire_col} = ? WHERE apple_user_id = ?", (final_str, user_id))
        conn.commit()
        _invalidate_sub_cache(user_id)
        print(f"[payment] {app_name} 用户 {user_id} 到期时间 -> {final_str}")
        return jsonify({"status": "success", "is_subscribed": final_dt > utcnow(),
                        "subscription_expires_at": final_str})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/api/<app_name>/user/delete', methods=['POST'])
def delete_user(app_name):
    if app_name not in ALLOWED_APPS:
        return jsonify({"error": "无效的应用名称"}), 404
    data = _json_body()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
    conn = sqlite3.connect(USER_DB_PATH, timeout=60.0)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM users WHERE apple_user_id = ?", (user_id,))
        if c.rowcount == 0:
            return jsonify({"error": "User not found"}), 404
        conn.commit()
        _invalidate_sub_cache(user_id)
        print(f"[{app_name}] 用户 {user_id} 已成功删除账号。")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"删除账号失败: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ---- 各 App 的登录/订阅路由绑定（OVideo 走 ONews 的账号体系） ----
@app.route('/api/ONews/auth/apple', methods=['POST'])
def onews_auth(): return handle_auth('ONews')

@app.route('/api/ONews/payment/subscribe', methods=['POST'])
def onews_pay(): return handle_payment('ONews')

@app.route('/api/ONews/user/status', methods=['GET'])
def onews_status(): return handle_status_check('ONews')

@app.route('/api/ONews/user/redeem', methods=['POST'])
def onews_redeem(): return handle_redeem_invite('ONews')



# ---------------- §1.9 版本检查 / 文件下载 ----------------
@app.route('/api/<app_name>/check_version', methods=['GET'])
def check_version(app_name):
    if app_name not in ALLOWED_APPS:
        return jsonify({"error": "无效的应用名称"}), 404
    cached = _load_json_cached(os.path.join(BASE_RESOURCES_DIR, app_name, 'version.json'))
    if cached is None:
        return jsonify({"error": "Version file not found"}), 404
    data = dict(cached)                      # 复制一份，不能改共享缓存
    data['server_date'] = datetime.now(APP_TZ).strftime('%y%m%d')
    data['is_free_access_day'] = is_free_access_day()   # 定义在 §5
    return jsonify(data)


@app.route('/api/<app_name>/download', methods=['GET'])
def download_file(app_name):
    filename = request.args.get('filename')
    print(f"收到来自应用 '{app_name}' 的文件下载请求: {filename}")
    if app_name not in ALLOWED_APPS:
        return jsonify({"error": "无效的应用名称"}), 404
    if not filename:
        return jsonify({"error": "缺少文件名参数"}), 400

    try:
        full_path = safe_join(BASE_RESOURCES_DIR, app_name, filename)
    except Exception:
        full_path = None
    if not full_path:
        print(f"错误: 请求的路径不安全: {filename}")
        return jsonify({"error": "无效的路径"}), 400

    # 【修复】按"规范化后的真实文件名"判断：'./Finance.db'、'Finance.db/'、大小写变体都绕不过
    base_lower = os.path.basename(full_path).lower()
    if base_lower in DOWNLOAD_DENY_BASENAMES or base_lower.endswith(DOWNLOAD_DENY_SUFFIXES):
        return jsonify({"error": "文件未找到"}), 404

    if app_name == 'Finance' and base_lower == 'finance.db':
        uid = request.args.get('user_id', '')
        if not is_real_login_user(uid):
            return jsonify({"error": "请先登录后再下载离线数据库"}), 401
        try:
            if not _user_exists(uid):
                return jsonify({"error": "用户不存在"}), 401
        except Exception:
            return jsonify({"error": "auth_check_failed"}), 500

    if not os.path.isfile(full_path):
        print(f"错误: 请求的文件不存在: {full_path}")
        return jsonify({"error": "文件未找到"}), 404
    try:
        directory, file = os.path.split(full_path)
        return send_from_directory(directory, file, as_attachment=True)
    except Exception as e:
        print(f"发生错误: {e}")
        return jsonify({"error": str(e)}), 500



# ╔══════════════════════════════════════════════════════════════════════╗
# ║  §2A ONews + OVideo 共用：点数账本 / 邀请码                             ║
# ║      表：onews_points(旧) / news_points / video_points / onews_invite_logs ║
# ║      依赖：§1；配置函数 get_news_points_config(§4) / get_video_points_config(§3) ║
# ╚══════════════════════════════════════════════════════════════════════╝

def init_points_db():
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=60.0)
    c = conn.cursor()
    for tname in ('onews_points', 'news_points', 'video_points'):
        c.execute(f'''
            CREATE TABLE IF NOT EXISTS {tname} (
                user_id TEXT PRIMARY KEY,
                invite_code TEXT UNIQUE,
                bonus_remaining INTEGER DEFAULT 0,
                bonus_total INTEGER DEFAULT 0,
                invited_by_code TEXT,
                invite_reward_count INTEGER DEFAULT 0,
                first_login_bonus_granted INTEGER DEFAULT 0,
                created_at TIMESTAMP
            )
        ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS onews_invite_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id TEXT NOT NULL,
            inviter_code TEXT,
            invitee_id TEXT NOT NULL,
            reward_points INTEGER,
            created_at TIMESTAMP NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_onews_invite_inviter ON onews_invite_logs(inviter_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_onews_invite_time ON onews_invite_logs(created_at)')
    conn.commit()
    conn.close()


def _gen_points_code(cursor, table, length=6):
    for _ in range(30):
        code = ''.join(secrets.choice(INVITE_ALPHABET) for _ in range(length))
        if not cursor.execute(f"SELECT 1 FROM {table} WHERE invite_code=?", (code,)).fetchone():
            return code
    return ''.join(secrets.choice(INVITE_ALPHABET) for _ in range(length + 2))


def _ensure_points(c, table, user_id, cfg, migrate_from=None):
    """确保点数行存在；返回 (row, just_granted)。
       news_points 首次创建时可从旧 onews_points 迁移。
       【修复】INSERT OR IGNORE：status 与 unlock 并发首建时不再 IntegrityError 500"""
    row = c.execute(f"SELECT * FROM {table} WHERE user_id=?", (user_id,)).fetchone()
    just_granted = False
    if row is None:
        code = _gen_points_code(c, table)
        migrated = None
        if migrate_from:
            migrated = c.execute(
                f"SELECT invite_code, bonus_remaining, bonus_total, invited_by_code, invite_reward_count "
                f"FROM {migrate_from} WHERE user_id=?", (user_id,)).fetchone()
        if migrated:
            old_code = migrated['invite_code']
            if old_code and not c.execute(f"SELECT 1 FROM {table} WHERE invite_code=?", (old_code,)).fetchone():
                code = old_code
            c.execute(f'''INSERT OR IGNORE INTO {table}
                (user_id, invite_code, bonus_remaining, bonus_total, invited_by_code,
                 invite_reward_count, first_login_bonus_granted, created_at)
                VALUES (?,?,?,?,?,?,1,?)''',
                (user_id, code, migrated['bonus_remaining'], migrated['bonus_total'],
                 migrated['invited_by_code'], migrated['invite_reward_count'], now_iso()))
        else:
            bonus = cfg['first_login_bonus']
            c.execute(f'''INSERT OR IGNORE INTO {table}
                (user_id, invite_code, bonus_remaining, bonus_total, invited_by_code,
                 invite_reward_count, first_login_bonus_granted, created_at)
                VALUES (?,?,?,?,NULL,0,?,?)''',
                (user_id, code, bonus, bonus, 1 if bonus > 0 else 0, now_iso()))
            just_granted = bonus > 0 and c.rowcount == 1
        row = c.execute(f"SELECT * FROM {table} WHERE user_id=?", (user_id,)).fetchone()
    return row, just_granted


def _grant_points_bonus(c, table, user_id, points, cfg):
    migrate = 'onews_points' if table == 'news_points' else None
    _ensure_points(c, table, user_id, cfg, migrate_from=migrate)
    c.execute(f"UPDATE {table} SET bonus_remaining=bonus_remaining+?, bonus_total=bonus_total+? WHERE user_id=?",
              (points, points, user_id))


def _news_daily_used(c, user_id, today):
    return c.execute('''SELECT COUNT(*) AS n FROM news_free_unlocks
                        WHERE user_id=? AND unlock_date=? AND COALESCE(source,'daily')='daily' ''',
                     (user_id, today)).fetchone()['n']


def _video_daily_used(c, user_id, today):
    return c.execute('''SELECT COUNT(*) AS n FROM video_free_unlocks
                        WHERE user_id=? AND unlock_date=? AND COALESCE(source,'daily')='daily' ''',
                     (user_id, today)).fetchone()['n']


def _log_onews_invite(inviter_id, code, invitee_id, points):
    try:
        conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
        conn.execute('''INSERT INTO onews_invite_logs
            (inviter_id, inviter_code, invitee_id, reward_points, created_at)
            VALUES (?,?,?,?,?)''', (inviter_id, code, invitee_id, points, now_iso()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"记录ONews邀请日志失败: {e}")




# ╔══════════════════════════════════════════════════════════════════════╗
# ║  §3 OVideo 视频（独享）                                                ║
# ║   3.1 配置与缓存  3.2 渠道屏蔽  3.3 数据规范化/集数解析                  ║
# ║   3.4 OVideo.db 构建  3.5 通用辅助/点数/埋点表                          ║
# ║   3.6 客户端路由  3.7 搜索  3.8 举报/寻片  3.9 埋点/点数  3.10 后台      ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ---------------- §3.1 配置与缓存 ----------------
OVIDEO_DIR = os.path.join(BASE_RESOURCES_DIR, 'OVideo')
OVIDEO_COVER_DIR = os.path.join(OVIDEO_DIR, 'cover_image')
OVIDEO_DB_PATH = os.path.join(OVIDEO_DIR, 'OVideo.db')
OVIDEO_VIDEO_FILE = os.path.join(OVIDEO_DIR, 'OVideos.json')
OVIDEO_BLACKLIST_FILE = os.path.join(OVIDEO_DIR, 'blacklist_url.json')
OVIDEO_MAPPING_FILE = os.path.join(OVIDEO_DIR, 'url_mapping.json')
OVIDEO_SCHEMA_VERSION = "3"          # 表结构变更 -> +1，触发自动重建

# Featured 首页「按上映日期」排序时 Drama 改用 (更新日期 − N 天)（当前未启用）
FEATURED_DRAMA_DATE_OFFSET_DAYS = 2

ALLOWED_EVENT_TYPES = {'play', 'download_complete'}
ALLOWED_REPORT_TYPES = {'playback_failed', 'download_failed', 'media_error', 'content_mismatch', 'other'}
report_last_time = {}   # 软限流
wish_last_time = {}     # 软限流

_video_db_lock = threading.Lock()
_VIDEO_DB_CHECK_INTERVAL = 3.0       # ensure_video_db 最多每 N 秒真正检查一次
_video_db_state = {"checked_at": 0.0}

_fuzzy_cache = {"mtime": None, "rows": None}
_fuzzy_cache_lock = threading.Lock()


def _get_valid_urls():
    """url_mapping 的 dict（只用来做 `in` 判断，等价于原来的 key 集合）"""
    return _load_json_cached(OVIDEO_MAPPING_FILE) or {}


# ---------------- §3.2 播放渠道(channel)屏蔽 ----------------
# 配置文件（可热改，改完下一次请求自动重建 OVideo.db）：Resources/OVideo/blocked_channels.json
# {
#   "enabled": true,
#   "names": ["暴风", "shangxidq"],     # 精确匹配渠道名(忽略大小写/空格)
#   "keywords": [],                     # 子串匹配
#   "block_resolve": true,              # 拦截老客户端缓存的播放页 URL
#   "hide_when_no_playable": false      # 剩余渠道一个能播的都没有时隐藏
# }
OVIDEO_CHANNEL_BLOCK_FILE = os.path.join(OVIDEO_DIR, 'blocked_channels.json')
DEFAULT_CHANNEL_BLOCK = {
    "enabled": True,
    "names": ["暴风", "shangxidq"],
    "keywords": [],
    "block_resolve": True,
    "hide_when_no_playable": False,
}
_channel_block_cache = {"mtime": None, "cfg": None}
_channel_block_lock = threading.Lock()
_blocked_eps_cache = {"mtime": None, "urls": set()}


def _norm_channel_name(name):
    return (name or "").strip().replace(" ", "").replace("　", "").lower()


def load_channel_block_config(force=False):
    """读取并缓存渠道屏蔽配置；文件 mtime 变化即自动重载。"""
    try:
        m = os.path.getmtime(OVIDEO_CHANNEL_BLOCK_FILE)
    except OSError:
        m = 0.0
    if (not force and _channel_block_cache["cfg"] is not None
            and _channel_block_cache["mtime"] == m):
        return _channel_block_cache["cfg"]
    with _channel_block_lock:
        raw = dict(DEFAULT_CHANNEL_BLOCK)
        if m:
            try:
                with open(OVIDEO_CHANNEL_BLOCK_FILE, 'r', encoding='utf-8') as f:
                    user = json.load(f)
                if isinstance(user, dict):
                    raw.update(user)
                elif isinstance(user, list):
                    raw["names"] = user
            except Exception as e:
                print(f"[OVideo] blocked_channels.json 读取失败，使用默认配置: {e}")
        names = {_norm_channel_name(n) for n in (raw.get("names") or []) if str(n).strip()}
        keywords = [k for k in (_norm_channel_name(x) for x in (raw.get("keywords") or [])) if k]
        cfg = {
            "enabled": bool(raw.get("enabled", True)) and bool(names or keywords),
            "names": names,
            "keywords": keywords,
            "block_resolve": bool(raw.get("block_resolve", True)),
            "hide_when_no_playable": bool(raw.get("hide_when_no_playable", False)),
        }
        _channel_block_cache["cfg"] = cfg
        _channel_block_cache["mtime"] = m
        return cfg


def is_channel_blocked(channel_name, cfg=None):
    cfg = cfg or load_channel_block_config()
    if not cfg["enabled"]:
        return False
    n = _norm_channel_name(channel_name)
    if not n:
        return False
    if n in cfg["names"]:
        return True
    return any(k in n for k in cfg["keywords"])


def channel_block_signature(cfg):
    """生效配置的指纹：配置变了 -> OVideo.db 自动重建"""
    payload = json.dumps({
        "e": cfg["enabled"], "n": sorted(cfg["names"]), "k": sorted(cfg["keywords"]),
        "r": cfg["block_resolve"], "h": cfg["hide_when_no_playable"],
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def _get_blocked_episode_urls():
    """被屏蔽渠道独占的 episode URL 集合（随 OVideo.db mtime 失效）"""
    if not load_channel_block_config()["block_resolve"]:
        return set()
    try:
        m = os.path.getmtime(OVIDEO_DB_PATH)
    except OSError:
        return set()
    if _blocked_eps_cache["mtime"] == m:
        return _blocked_eps_cache["urls"]
    try:
        conn = sqlite3.connect(OVIDEO_DB_PATH, timeout=10.0)
        try:
            urls = {r[0] for r in conn.execute("SELECT url FROM blocked_channel_eps")}
        finally:
            conn.close()
    except Exception as e:
        print(f"[OVideo] 读取 blocked_channel_eps 失败: {e}")
        return set()
    _blocked_eps_cache["urls"] = urls
    _blocked_eps_cache["mtime"] = m
    return urls


def filter_blocked_channels(playlist, cfg=None):
    """给直读 JSON 的老接口用：返回过滤后的 playlist"""
    cfg = cfg or load_channel_block_config()
    if not cfg["enabled"] or not playlist:
        return playlist
    return [ch for ch in playlist if not is_channel_blocked(ch.get('name'), cfg)]


# ---------------- §3.3 数据规范化 / 集数解析（与客户端保持同步） ----------------
TYPE_MAPPING = {
    "科幻片":"科幻","奇幻":"科幻","奇幻片":"科幻","异世界":"科幻","玄幻":"科幻","探案":"悬疑",
    "运动":"体育","动作片":"动作","武侠":"古装","战争片":"战争","战斗":"战争","同杏":"同性",
    "剧情片":"剧情","日常":"剧情","黑色电影":"剧情","韩剧":"剧情","美剧":"剧情","国产剧":"剧情",
    "港台剧":"剧情","日剧":"剧情","国产":"剧情","大陆":"剧情","泰剧":"剧情","美国":"剧情","欧美":"剧情",
    "美国剧":"剧情","欧美剧":"剧情","日本剧":"剧情","日本":"剧情","香港剧":"剧情","韩国剧":"剧情",
    "韩国":"剧情","日韩":"剧情","日韩剧":"剧情","香港":"剧情","台湾":"剧情","港台":"剧情","邵氏电影":"剧情",
    "泰国":"剧情","海外剧":"剧情","海外":"剧情","台湾剧":"剧情",
    "喜剧片":"喜剧","搞笑":"喜剧","爱情片":"爱情","恋爱":"爱情","情":"爱情","浪漫":"爱情",
    "丧尸":"恐怖","恐怖片":"恐怖","惊栗":"惊悚","惊悚片":"惊悚","犯罪片":"犯罪",
    "记录":"纪录片","其他":"纪录片","纪录":"纪录片","记录片":"纪录片",
    "选秀":"其它","大陆综艺":"其它","晚会":"其它","日韩综艺":"其它","欧美综艺":"其它","相声":"其它",
    "访谈":"其它","戏曲":"其它","港台综艺":"其它","国产综艺":"其它","动画":"其它","海外动漫":"其它",
    "鬼怪":"其它","日本动漫":"其它","综艺":"其它","有声动漫":"其它","机战":"其它","日韩动漫":"其它",
    "欧美动漫":"其它","脱口秀":"其它","游戏":"其它","热血":"其它","致郁":"其它","动漫片":"其它","动画片":"其它",
    "动漫":"其它","动漫电影":"其它","动画电影":"其它","国产动漫":"其它","真人秀":"其它","港台动漫":"其它",
}
_R_CHINA = {"中国大陆","内地","澳门","大陆","大陆国语","中国","国产"}
_R_TW    = {"台湾","港台","中国台湾"}
_R_HK    = {"香港","中国香港","中国澳门"}
_R_EU    = {"欧美","英国","西班牙","挪威","瑞典","丹麦","乌克兰","南斯拉夫","塞浦路斯","奥地利","UK","United Kingdom",
            "保加利亚","克罗地亚","塞尔维亚","德国","意大利","捷克","捷克斯洛伐克","法国","波黑","玻利维亚",
            "突尼斯","罗马尼亚","西德","马耳他","澳大利亚","爱尔兰","瑞士","立陶宛","芬兰","荷兰","匈牙利",
            "希腊","拉脱维亚","马其顿","新西兰","比利时","波兰","NZ","冰岛","北马其顿","卢森堡","斯洛伐克",
            "斯洛文尼亚","澳大利亚Australia","爱沙尼亚","英语","葡萄牙"}
_R_ASIA  = {"乌兹别克斯坦","俄罗斯","印度尼西亚","土耳其","新加坡","格鲁吉亚","泰国","苏联","菲律宾",
            "巴基斯坦","不丹","哈萨克斯坦","塔吉克斯坦","尼泊尔","柬埔寨","蒙古","越南","马来西亚"}
_R_MID   = {"伊拉克","伊朗","以色列","埃及","巴勒斯坦","叙利亚","巴勒斯坦被占领区","沙特阿拉伯","约旦","苏丹","阿富汗","黎巴嫩","科威特"}
_R_AM    = {"加拿大","墨西哥","哥伦比亚","巴西","智利","厄瓜多尔","阿根廷","秘鲁","Aruba","Canada","Jamaica",
            "USA","乌拉圭","古巴","委内瑞拉","牙买加","特立尼达和多巴哥"}
_R_AF    = {"南非","乍得","埃塞俄比亚","塞内加尔","摩洛哥","阿尔及利亚","阿尔巴尼亚"}
_CHINESE_RE = re.compile(r'[\u4e00-\u9fa5·]+')

_SEASON_EP_RE = re.compile(r'[Ss](\d{1,2})[\s._\-]*[Ee](\d{1,3})')
_EP_LABEL_RE  = re.compile(r'第\s*(\d{1,4})\s*[集期话話幕]')
_PURE_NUM_RE  = re.compile(r'^\s*(\d{1,4})\s*$')
_ANY_NUM_RE   = re.compile(r'(\d{1,4})')


def _episode_index(name):
    """从单个 episode 名解析集号；无法解析返回 None（例如 'HD'、'20241019'）"""
    n = (name or '').strip()
    if not n:
        return None
    digits = re.sub(r'\D', '', n)
    if len(digits) >= 6 and digits[:2] in ('19', '20'):   # 日期型
        return None
    m = _EP_LABEL_RE.search(n)
    if m:
        return int(m.group(1))
    m = _PURE_NUM_RE.match(n)
    if m:
        return int(m.group(1))
    m = _ANY_NUM_RE.search(n)
    if m:
        v = int(m.group(1))
        if 0 < v <= 2000:
            return v
    return None


def _channel_progress(ep_names):
    """单个渠道的"有效集数"：
       1) 存在 SxxExx：只取最大季内的集数
       2) 否则按 第N集/第N期/纯数字 取最大集号
       3) 否则（日期型 / HD 等）用集数数量"""
    names = [n for n in ep_names if (n or '').strip()]
    if not names:
        return 0
    seasons = {}
    for n in names:
        m = _SEASON_EP_RE.search(n)
        if m:
            seasons.setdefault(int(m.group(1)), set()).add(int(m.group(2)))
    if seasons:
        top = max(seasons.keys())
        return max(max(seasons[top]), len(seasons[top]))
    valid = [v for v in (_episode_index(n) for n in names) if v is not None]
    if valid and len(valid) * 2 >= len(names):
        return max(valid)
    return len(names)


def _normalize_region(region):
    if not region or not region.strip():
        return "其它"
    first = region.split('/')[0].strip()
    if first in _R_CHINA: return "中国"
    if first in _R_TW:    return "中国台湾"
    if first in _R_HK:    return "香港澳门"
    if first in _R_EU:    return "欧洲"
    if first in _R_ASIA:  return "亚洲"
    if first in _R_MID:   return "中东"
    if first in _R_AM:    return "北美洲/南美洲"
    if first in _R_AF:    return "非洲"
    return first


def _normalize_types(types):
    if not types:
        return []
    return list({TYPE_MAPPING.get(t, t) for t in types})


def _clean_name(raw):
    t = (raw or "").strip()
    if not t:
        return ""
    m = _CHINESE_RE.search(t)
    return m.group(0).strip() if m else t


def _norm_search(text):
    return (text or "").lower().replace('·', '').replace(' ', '')


def _release_sort_key(date):
    return date.split('(')[0] if date else ""


def _release_year(date):
    if not date:
        return None
    try:
        return int(date.split('(')[0].split('-')[0])
    except Exception:
        return None


def _best_rating(ratings):
    if not ratings:
        return 0.0
    vals = []
    for v in ratings.values():
        try:
            vals.append(float(v))
        except Exception:
            pass
    return max(vals) if vals else 0.0


# ---------------- §3.4 OVideo.db 构建 / 自动重建 ----------------
def build_video_db():
    """把 OVideos.json 全量构建成 SQLite。
       先写到临时文件，完成后 os.replace 原子替换 —— 重建期间其他请求仍读旧库，不会报 no such table。"""
    if not os.path.exists(OVIDEO_VIDEO_FILE):
        return

    chan_cfg = load_channel_block_config(force=True)
    if chan_cfg['enabled']:
        print("[OVideo] 渠道屏蔽已启用 names=%s keywords=%s"
              % (sorted(chan_cfg['names']), chan_cfg['keywords']))
    else:
        print("[OVideo] 渠道屏蔽未启用")

    print("[OVideo] 开始构建 SQLite ...")
    src_mtime = os.path.getmtime(OVIDEO_VIDEO_FILE)
    with open(OVIDEO_VIDEO_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    blacklist_set = set()
    if os.path.exists(OVIDEO_BLACKLIST_FILE):
        try:
            with open(OVIDEO_BLACKLIST_FILE, 'r', encoding='utf-8') as bf:
                blacklist_set = set(json.load(bf).keys())
        except Exception as e:
            print(f"[OVideo] 黑名单读取失败: {e}")

    valid_url_set = set()
    if os.path.exists(OVIDEO_MAPPING_FILE):
        try:
            with open(OVIDEO_MAPPING_FILE, 'r', encoding='utf-8') as mf:
                valid_url_set = set(json.load(mf).keys())
        except Exception as e:
            print(f"[OVideo] url_mapping 读取失败: {e}")

    def _is_playable(u):
        return (u in valid_url_set) or ('.m3u8' in (u or '').lower())

    rows = []
    cat_order = list(data.keys())
    blocked_ep_urls = set()
    channel_stats = {}
    stat_dropped_channels = 0
    stat_hidden_by_channel = 0

    for category, items in data.items():
        for item in items:
            url = item.get('url')
            if not url:
                continue
            name = item.get('name', '') or ''
            region = item.get('地区', '') or ''
            date = item.get('date', '') or ''
            ratings = item.get('评分') or {}
            ntypes = _normalize_types(item.get('类型') or [])
            director = item.get('导演') or ''
            cast = item.get('主演') or []
            alias = item.get('alias') or ''
            intro = item.get('intro') or ''
            cleaned_cast = [_clean_name(x) for x in cast]
            cleaned_dir = _clean_name(director)

            item_nolist = dict(item)
            playlist = item_nolist.pop('playlist', []) or []

            # ---- 渠道屏蔽（必须在 hide / 集数计算之前） ----
            for ch in playlist:
                cn = (ch.get('name') or '').strip() or '(未命名)'
                channel_stats[cn] = channel_stats.get(cn, 0) + 1
            raw_channels_with_eps = len([ch for ch in playlist if (ch.get('episodes') or {})])

            if chan_cfg['enabled'] and playlist:
                kept_channels, dropped_channels = [], []
                for ch in playlist:
                    (dropped_channels if is_channel_blocked(ch.get('name'), chan_cfg)
                     else kept_channels).append(ch)
                if dropped_channels:
                    stat_dropped_channels += len(dropped_channels)
                    kept_urls_item = set()   # 同一 URL 也在保留渠道里就不能拦截
                    for ch in kept_channels:
                        kept_urls_item.update(u for u in (ch.get('episodes') or {}).values() if u)
                    for ch in dropped_channels:
                        for u in (ch.get('episodes') or {}).values():
                            if u and u not in kept_urls_item:
                                blocked_ep_urls.add(u)
                    playlist = kept_channels

            channels_with_eps = [ch for ch in playlist if (ch.get('episodes') or {})]

            hide_blacklisted = 0
            if raw_channels_with_eps > 0 and not channels_with_eps:
                hide_blacklisted = 1          # 所有渠道都被屏蔽
                stat_hidden_by_channel += 1
            elif blacklist_set:
                if category == 'Movie':
                    # Movie：所有 episode 全部命中黑名单才隐藏
                    all_ep_urls = [u for ch in channels_with_eps
                                   for u in (ch.get('episodes') or {}).values()]
                    if all_ep_urls and all(u in blacklist_set for u in all_ep_urls):
                        hide_blacklisted = 1
                elif category in ('Drama', 'Anime', 'Show'):
                    # 每个有剧集的渠道都满足：全部不可播 且 至少一个在黑名单 -> 隐藏
                    if channels_with_eps:
                        hide = True
                        for ch in channels_with_eps:
                            ep_urls = list((ch.get('episodes') or {}).values())
                            all_unplayable = all(not _is_playable(u) for u in ep_urls)
                            has_blacklisted = any(u in blacklist_set for u in ep_urls)
                            if not (all_unplayable and has_blacklisted):
                                hide = False
                                break
                        if hide:
                            hide_blacklisted = 1

            if (not hide_blacklisted and chan_cfg['hide_when_no_playable'] and channels_with_eps):
                if not any(_is_playable(u) for ch in channels_with_eps
                           for u in (ch.get('episodes') or {}).values()):
                    hide_blacklisted = 1

            # 追剧：有效集数（只统计可播放且不在黑名单的 episode）
            latest_ep_count = 0
            if category != 'Movie':
                per_channel = []
                for ch in channels_with_eps:
                    eps = ch.get('episodes') or {}
                    names = [n for n, u in eps.items() if _is_playable(u) and u not in blacklist_set]
                    if names:
                        per_channel.append(_channel_progress(names))
                if per_channel:
                    latest_ep_count = max(per_channel)

            rows.append((
                url, category, name,
                region, _normalize_region(region),
                _release_year(date), _release_sort_key(date),
                item.get('update', '') or '', _best_rating(ratings),
                '|' + '|'.join(ntypes) + '|',
                '|' + '|'.join(item.get('类型') or []) + '|',
                1 if '纪录片' in ntypes else 0,
                name.lower(), alias.lower(),
                ('\x1f'.join(item.get('类型') or [])).lower(),
                cleaned_dir.lower(), ('\x1f'.join(cleaned_cast)).lower(), intro.lower(),
                _norm_search(name), _norm_search(alias),
                _norm_search(cleaned_dir), _norm_search('\x1f'.join(cleaned_cast)),
                json.dumps(item_nolist, ensure_ascii=False),
                json.dumps(playlist, ensure_ascii=False),   # 已过滤屏蔽渠道
                hide_blacklisted,
                latest_ep_count,
            ))

    tmp_path = OVIDEO_DB_PATH + '.building'
    for p in (tmp_path, tmp_path + '-journal'):
        if os.path.exists(p):
            os.remove(p)
    conn = sqlite3.connect(tmp_path, timeout=60.0)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE videos (
            url TEXT PRIMARY KEY,
            category TEXT, name TEXT,
            region TEXT, norm_region TEXT,
            release_year INTEGER, release_sort_key TEXT,
            update_sort_key TEXT, best_rating REAL,
            norm_types TEXT, raw_types TEXT, has_documentary INTEGER,
            name_lower TEXT, alias_lower TEXT, types_lower TEXT,
            director_lower TEXT, cast_lower TEXT, intro_lower TEXT,
            name_norm TEXT, alias_norm TEXT, director_norm TEXT, cast_norm TEXT,
            item_json TEXT, playlist_json TEXT,
            hide_blacklisted INTEGER DEFAULT 0,
            latest_ep_count INTEGER DEFAULT 0
        )
    ''')
    c.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE blocked_channel_eps (url TEXT PRIMARY KEY)")
    c.executemany("INSERT OR REPLACE INTO videos VALUES (%s)" % ",".join("?" * 26), rows)
    if blocked_ep_urls:
        c.executemany("INSERT OR IGNORE INTO blocked_channel_eps VALUES (?)", [(u,) for u in blocked_ep_urls])
    c.execute("CREATE INDEX idx_cat_update  ON videos(category, update_sort_key)")
    c.execute("CREATE INDEX idx_cat_release ON videos(category, release_sort_key)")
    c.execute("CREATE INDEX idx_cat_rating  ON videos(category, best_rating)")
    c.execute("CREATE INDEX idx_doc ON videos(has_documentary)")
    c.execute("CREATE INDEX idx_hide ON videos(hide_blacklisted)")
    meta = {
        'schema_version': OVIDEO_SCHEMA_VERSION,
        'source_mtime': str(src_mtime),
        'blacklist_mtime': str(os.path.getmtime(OVIDEO_BLACKLIST_FILE)) if os.path.exists(OVIDEO_BLACKLIST_FILE) else "0",
        'mapping_mtime': str(os.path.getmtime(OVIDEO_MAPPING_FILE)) if os.path.exists(OVIDEO_MAPPING_FILE) else "0",
        'channel_block_sig': channel_block_signature(chan_cfg),
        'channel_stats': json.dumps(channel_stats, ensure_ascii=False),
        'categories': json.dumps(cat_order, ensure_ascii=False),
    }
    c.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", list(meta.items()))
    conn.commit()
    conn.close()
    os.replace(tmp_path, OVIDEO_DB_PATH)       # 原子替换

    _blocked_eps_cache["mtime"] = None
    _blocked_eps_cache["urls"] = set()
    print(f"[OVideo] 构建完成，共 {len(rows)} 条；屏蔽渠道 {stat_dropped_channels} 个，"
          f"因全渠道被屏蔽而隐藏 {stat_hidden_by_channel} 条，可拦截播放链接 {len(blocked_ep_urls)} 条。")


def _video_source_fingerprint():
    src_m = str(os.path.getmtime(OVIDEO_VIDEO_FILE))
    bl_m = str(os.path.getmtime(OVIDEO_BLACKLIST_FILE)) if os.path.exists(OVIDEO_BLACKLIST_FILE) else "0"
    map_m = str(os.path.getmtime(OVIDEO_MAPPING_FILE)) if os.path.exists(OVIDEO_MAPPING_FILE) else "0"
    chan_sig = channel_block_signature(load_channel_block_config())
    return (src_m, bl_m, map_m, OVIDEO_SCHEMA_VERSION, chan_sig)


def _read_video_meta():
    conn = sqlite3.connect(OVIDEO_DB_PATH, timeout=10.0)
    try:
        def _get(k):
            r = conn.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
            return r[0] if r else None
        return (_get('source_mtime'), _get('blacklist_mtime'), _get('mapping_mtime'),
                _get('schema_version'), _get('channel_block_sig'))
    finally:
        conn.close()


def ensure_video_db(force=False):
    """JSON / 黑名单 / url_mapping / 渠道屏蔽配置 / 表结构 变更时自动重建（最多每 3 秒检查一次）"""
    if not os.path.exists(OVIDEO_VIDEO_FILE):
        return
    now = time.time()
    if (not force and os.path.exists(OVIDEO_DB_PATH)
            and now - _video_db_state["checked_at"] < _VIDEO_DB_CHECK_INTERVAL):
        return
    _video_db_state["checked_at"] = now

    try:
        want = _video_source_fingerprint()
    except OSError:
        return

    def _up_to_date():
        if not os.path.exists(OVIDEO_DB_PATH):
            return False
        try:
            return _read_video_meta() == want
        except Exception:
            return False

    if _up_to_date():
        return
    with _video_db_lock:
        if _up_to_date():
            return
        try:
            build_video_db()
        except Exception:
            traceback.print_exc()
            print("[OVideo] 重建失败，继续使用旧库")


def _get_video_conn():
    conn = sqlite3.connect(OVIDEO_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- §3.5 通用辅助：屏蔽配置 / 排序 / 模糊候选 / 点数配置 / 埋点表 ----------------
def _is_vip_permanent(user_id):
    """任一 App 永久 VIP（用于视频地区/类型屏蔽豁免），缓存 60 秒"""
    if not is_real_login_user(user_id):
        return False
    hit = _vip_perm_cache.get(user_id)
    if hit and time.time() - hit[1] < _SUB_KIND_TTL:
        return hit[0]
    try:
        conn = sqlite3.connect(USER_DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("""SELECT onews_is_permanent, finance_is_permanent, prediction_is_permanent
                                  FROM users WHERE apple_user_id=?""", (user_id,)).fetchone()
        finally:
            conn.close()
        val = bool(row and (row['onews_is_permanent'] == 1
                            or row['finance_is_permanent'] == 1
                            or row['prediction_is_permanent'] == 1))
    except Exception:
        return False
    _cache_put(_vip_perm_cache, user_id, (val, time.time()))
    return val


def _get_block_config(user_id):
    """返回 (region_keywords, type_keywords)；永久 VIP 或未开启时为空"""
    if _is_vip_permanent(user_id):
        return [], []
    vdata = _load_version_json('ONews')
    rf = vdata.get('video_region_filter') or {}
    tf = vdata.get('video_type_filter') or {}
    if not isinstance(rf, dict): rf = {}
    if not isinstance(tf, dict): tf = {}
    region_kw = [k for k in (rf.get('keywords') or []) if k] if rf.get('enabled', False) else []
    type_kw = [k for k in (tf.get('keywords') or []) if k] if tf.get('enabled', False) else []
    return region_kw, type_kw


def _block_where(region_kw, type_kw):
    clauses, params = [], []
    if region_kw:
        clauses.append("region NOT IN (%s)" % ",".join("?" * len(region_kw)))
        params += region_kw
    for kw in type_kw:
        clauses.append("raw_types NOT LIKE ?")
        params.append(f"%{kw}%")
    return clauses, params


def _order_clause(sort):
    if sort == 'date':   return "release_sort_key DESC"
    if sort == 'rating': return "best_rating DESC, release_sort_key DESC"
    return "update_sort_key DESC"


def _get_fuzzy_candidates():
    """全表模糊匹配候选（预切分 cast、预建字符集合），仅 OVideo.db mtime 变化时重建"""
    try:
        db_mtime = os.path.getmtime(OVIDEO_DB_PATH)
    except OSError:
        return []
    if _fuzzy_cache["mtime"] == db_mtime and _fuzzy_cache["rows"] is not None:
        return _fuzzy_cache["rows"]
    with _fuzzy_cache_lock:
        if _fuzzy_cache["mtime"] == db_mtime and _fuzzy_cache["rows"] is not None:
            return _fuzzy_cache["rows"]
        conn = _get_video_conn()
        raw = conn.execute(
            "SELECT url, category, name_norm, alias_norm, director_norm, cast_norm, "
            "name_lower, best_rating, release_sort_key, update_sort_key, "
            "hide_blacklisted, region, raw_types, release_year FROM videos"
        ).fetchall()
        conn.close()
        rows = []
        for r in raw:
            name = r['name_norm'] or ''
            alias = r['alias_norm'] or ''
            director = r['director_norm'] or ''
            cast_list = [c for c in (r['cast_norm'] or '').split('\x1f') if c]
            rows.append({
                'url': r['url'], 'category': r['category'],
                'name': name, 'alias': alias, 'director': director, 'cast_list': cast_list,
                'name_set': set(name), 'alias_set': set(alias), 'director_set': set(director),
                'cast_sets': [set(c) for c in cast_list],
                'name_len': len(r['name_lower'] or ''),
                'rating': r['best_rating'] or 0.0,
                'rel': r['release_sort_key'] or '',
                'upd': r['update_sort_key'] or '',
                'hide': r['hide_blacklisted'] or 0,
                'region': r['region'] or '',
                'raw_types': r['raw_types'] or '',
                'release_year': r['release_year'],
            })
        _fuzzy_cache["rows"] = rows
        _fuzzy_cache["mtime"] = db_mtime
        return rows


def get_video_points_config():
    data = _load_version_json('ONews')
    try:
        q = data.get('video_free_quota', {}) or {}
        enabled = bool(q.get('enabled', False))
        return {
            'daily_quota': int(q.get('daily_count', 0)) if enabled else 0,
            'first_login_bonus': int(q.get('first_login_bonus', 0)) if enabled else 0,
            'invite_reward_points': int(data.get('video_invite_reward_points', 8)),
        }
    except Exception as e:
        print(f"读取视频点数配置失败: {e}")
        return {'daily_quota': 0, 'first_login_bonus': 0, 'invite_reward_points': 8}


def resolve_video_access_type(user_id, reported=None, episode_key=None):
    """决定这次播放/下载记为"订阅"还是"点数"。订阅以服务器为准；非订阅优先看当天解锁来源。"""
    kind = get_subscription_kind(user_id, 'ONews')
    if kind:
        return kind
    r = (reported or '').strip()
    if r in ALLOWED_ACCESS_TYPES and r not in ('subscription', 'vip_permanent') and r != 'points':
        return r
    if episode_key:
        try:
            conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=10.0)
            conn.row_factory = sqlite3.Row
            row = conn.execute("""SELECT source FROM video_free_unlocks
                                  WHERE user_id=? AND episode_key=?
                                  ORDER BY id DESC LIMIT 1""", (user_id, episode_key)).fetchone()
            conn.close()
            if row:
                return 'points_bonus' if (row['source'] or 'daily') == 'bonus' else 'points_daily'
        except Exception:
            pass
    if r == 'points':
        return 'points'
    return 'points' if is_real_login_user(user_id) else 'free'


def init_ovideo_analytics_db():
    """analytics.db 中 OVideo 相关表"""
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=60.0)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_video_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            video_url TEXT NOT NULL,
            video_title TEXT,
            event_type TEXT NOT NULL,
            first_at TIMESTAMP NOT NULL,
            last_at TIMESTAMP NOT NULL,
            count INTEGER DEFAULT 1,
            UNIQUE(user_id, video_url, event_type)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS event_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            video_url TEXT NOT NULL,
            video_title TEXT,
            event_type TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    ''')
    for ddl in ("ALTER TABLE event_logs ADD COLUMN user_type TEXT DEFAULT 'apple'",
                "ALTER TABLE user_video_events ADD COLUMN user_type TEXT DEFAULT 'apple'",
                "ALTER TABLE event_logs ADD COLUMN source TEXT",
                "ALTER TABLE event_logs ADD COLUMN app_version TEXT",
                "ALTER TABLE event_logs ADD COLUMN access_type TEXT",
                "ALTER TABLE user_video_events ADD COLUMN access_type TEXT"):
        try:
            c.execute(ddl)
        except sqlite3.OperationalError:
            pass
    c.execute('CREATE INDEX IF NOT EXISTS idx_logs_time ON event_logs(created_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_logs_type ON event_logs(event_type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_logs_user ON event_logs(user_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_logs_access ON event_logs(access_type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_url ON user_video_events(video_url)')

    # 视频解锁表（source: bonus=一次性赠送 / daily=每日免费）
    c.execute('''
        CREATE TABLE IF NOT EXISTS video_free_unlocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            episode_key TEXT NOT NULL,
            unlock_date TEXT NOT NULL,
            video_title TEXT,
            created_at TIMESTAMP NOT NULL,
            UNIQUE(user_id, episode_key, unlock_date)
        )
    ''')
    try:
        c.execute("ALTER TABLE video_free_unlocks ADD COLUMN source TEXT DEFAULT 'daily'")
    except sqlite3.OperationalError:
        pass
    c.execute('CREATE INDEX IF NOT EXISTS idx_unlock_user_date ON video_free_unlocks(user_id, unlock_date)')
    # 旧版一次性赠送表（已被 video_points 取代，保留兼容）
    c.execute('''
        CREATE TABLE IF NOT EXISTS video_bonus_quota (
            user_id TEXT PRIMARY KEY,
            bonus_total INTEGER NOT NULL,
            bonus_remaining INTEGER NOT NULL,
            granted_at TIMESTAMP NOT NULL
        )
    ''')

    # 错误链接举报表
    c.execute('''
        CREATE TABLE IF NOT EXISTS video_link_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            video_title TEXT,
            source_url TEXT,
            episode_url TEXT,
            channel_name TEXT,
            episode_name TEXT,
            real_url TEXT,
            report_type TEXT,
            note TEXT,
            app_version TEXT,
            first_at TIMESTAMP NOT NULL,
            last_at TIMESTAMP NOT NULL,
            count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            admin_reply TEXT,
            reply_status TEXT DEFAULT 'none',
            replied_at TIMESTAMP,
            UNIQUE(user_id, episode_url, report_type)
        )
    ''')
    for ddl in ("ALTER TABLE video_link_reports ADD COLUMN admin_reply TEXT",
                "ALTER TABLE video_link_reports ADD COLUMN reply_status TEXT DEFAULT 'none'",
                "ALTER TABLE video_link_reports ADD COLUMN replied_at TIMESTAMP"):
        try:
            c.execute(ddl)
        except sqlite3.OperationalError:
            pass
    c.execute('CREATE INDEX IF NOT EXISTS idx_reports_status ON video_link_reports(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reports_ep ON video_link_reports(episode_url)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reports_reply ON video_link_reports(user_id, reply_status)')

    # 寻片/许愿请求表
    c.execute('''
        CREATE TABLE IF NOT EXISTS video_wish_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_type TEXT DEFAULT 'apple',
            keyword TEXT,
            wish_content TEXT NOT NULL,
            app_version TEXT,
            first_at TIMESTAMP NOT NULL,
            last_at TIMESTAMP NOT NULL,
            count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            admin_reply TEXT,
            reply_status TEXT DEFAULT 'none',
            replied_at TIMESTAMP,
            UNIQUE(user_id, wish_content)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_wish_status ON video_wish_requests(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_wish_reply ON video_wish_requests(user_id, reply_status)')
    conn.commit()
    conn.close()

# ---------------- §3.6 OVideo 客户端路由：列表 / 详情 / 播放解析 ----------------
def _parse_max_year():
    """审核员限定：只看 <= max_year 的老片；非法值返回 None"""
    v = request.args.get('max_year')
    if not v:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _filter_playlist_playable(raw, valid):
    """只保留可播放（在 mapping 中或本身是 m3u8）的剧集，并下发原始顺序 episode_order"""
    out = []
    for channel in raw or []:
        eps, order = {}, []
        for ep_name, ep_url in (channel.get('episodes') or {}).items():
            if ep_url and (ep_url in valid or '.m3u8' in ep_url.lower()):
                eps[ep_name] = ep_url
                order.append(ep_name)
        if eps:
            nc = dict(channel)
            nc['episodes'] = eps
            nc['episode_order'] = order
            out.append(nc)
    return out


@app.route('/api/OVideo/videos', methods=['GET'])
def get_ovideos():
    """【老接口】一次性下发全部视频（新客户端走 /list /filter /search2）。
       【性能】改从 OVideo.db 读取（渠道屏蔽已在建库时处理），按 rowid 保持原 JSON 顺序。"""
    ensure_video_db()
    if not os.path.exists(OVIDEO_DB_PATH):
        return jsonify({"error": "Video file not found"}), 404
    user_id = request.args.get('user_id')
    if user_id and user_id in VIDEO_MODULE_BLOCKED_USERS:
        return jsonify({"categories": []})
    try:
        region_kw, type_kw = _get_block_config(user_id)
        bc, bp = _block_where(region_kw, type_kw)
        where = (" WHERE " + " AND ".join(bc)) if bc else ""
        valid_urls = _get_valid_urls()
        conn = _get_video_conn()
        try:
            r = conn.execute("SELECT value FROM meta WHERE key='categories'").fetchone()
            buckets = {c: [] for c in (json.loads(r['value']) if r else [])}
            for row in conn.execute(
                    f"SELECT category, item_json, playlist_json FROM videos{where} ORDER BY rowid", bp):
                it = json.loads(row['item_json'])
                it['playlist'] = _filter_playlist_playable(json.loads(row['playlist_json'] or '[]'), valid_urls)
                buckets.setdefault(row['category'], []).append(it)
        finally:
            conn.close()
        return jsonify({"categories": [{"name": k, "items": v} for k, v in buckets.items()]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/OVideo/playlist', methods=['GET'])
def ovideo_playlist():
    ensure_video_db()
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "Missing url"}), 400
    conn = _get_video_conn()
    try:
        row = conn.execute("SELECT playlist_json FROM videos WHERE url=?", (url,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"playlist": []})
    raw = json.loads(row['playlist_json'] or '[]')
    return jsonify({"playlist": _filter_playlist_playable(raw, _get_valid_urls())})


@app.route('/api/OVideo/track_series/status', methods=['POST'])
def ovideo_track_series_status():
    """追剧：批量查询一组剧的当前有效集数 / 更新时间"""
    ensure_video_db()
    urls = _json_body().get('urls') or []
    if not isinstance(urls, list):
        return jsonify({"items": []})
    urls = [u for u in urls if isinstance(u, str) and u][:400]
    if not urls:
        return jsonify({"items": []})
    conn = _get_video_conn()
    out = []
    CHUNK = 200
    try:
        for i in range(0, len(urls), CHUNK):
            chunk = urls[i:i + CHUNK]
            ph = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT url, category, name, update_sort_key, latest_ep_count, "
                f"hide_blacklisted, item_json FROM videos WHERE url IN ({ph})", chunk).fetchall()
            for r in rows:
                try:
                    it = json.loads(r['item_json'] or '{}')
                except Exception:
                    it = {}
                out.append({
                    "url": r['url'],
                    "category": r['category'],
                    "name": r['name'],
                    "image": it.get('image'),
                    "info": it.get('info'),
                    "update": r['update_sort_key'] or '',
                    "episode_count": int(r['latest_ep_count'] or 0),
                    "unavailable": bool(r['hide_blacklisted'] or 0),
                })
    finally:
        conn.close()
    return jsonify({"items": out})


@app.route('/api/OVideo/detail', methods=['GET'])
def ovideo_detail():
    """按 url 取单条完整剧集信息（追剧列表点击后跳详情页用）"""
    ensure_video_db()
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "Missing url"}), 400
    conn = _get_video_conn()
    try:
        row = conn.execute("SELECT category, item_json FROM videos WHERE url=?", (url,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    it = json.loads(row['item_json'] or '{}')
    it['category'] = row['category']
    return jsonify({"item": it})


@app.route('/api/OVideo/cover/<path:filename>', methods=['GET'])
def get_ovideo_cover(filename):
    try:
        safe_path = safe_join(OVIDEO_COVER_DIR, filename)
    except Exception:
        safe_path = None
    if not safe_path:
        return jsonify({"error": "Invalid path"}), 400
    if not os.path.isfile(safe_path):
        return jsonify({"error": "Image not found"}), 404
    directory, file = os.path.split(safe_path)
    response = send_from_directory(directory, file)
    response.headers['Cache-Control'] = 'public, max-age=604800'  # 7 天
    return response


@app.route('/api/OVideo/resolve', methods=['POST'])
def resolve_ovideo_url():
    """播放页 URL -> 真实 m3u8（同时做渠道屏蔽 / 黑名单拦截）"""
    data = _json_body()
    episode_url = data.get('url')
    if not episode_url or not isinstance(episode_url, str):
        return jsonify({"error": "Missing url"}), 400

    # 被封锁渠道的播放页（老客户端可能有本地缓存），必须放在 m3u8 直返之前
    if episode_url in _get_blocked_episode_urls():
        return jsonify({"error": "Blacklisted", "reason": "该播放源已下线，请切换其他播放源"}), 403

    # JSON 里直接写的 m3u8 直链，原样返回
    if '.m3u8' in episode_url.lower():
        return jsonify({"real_url": episode_url, "title": ""})

    blacklist = _load_json_cached(OVIDEO_BLACKLIST_FILE) or {}
    if episode_url in blacklist:
        return jsonify({"error": "Blacklisted", "reason": "该视频暂不可用"}), 403

    mappings = _load_json_cached(OVIDEO_MAPPING_FILE)
    if mappings is None:
        return jsonify({"error": "Mapping file not found"}), 404
    mapping_data = mappings.get(episode_url)
    if isinstance(mapping_data, list) and len(mapping_data) > 0:
        return jsonify({"real_url": mapping_data[0],
                        "title": mapping_data[1] if len(mapping_data) > 1 else ""})
    return jsonify({"error": "URL not found in mapping"}), 404


@app.route('/api/OVideo/categories', methods=['GET'])
def ovideo_categories():
    ensure_video_db()
    try:
        conn = _get_video_conn()
        try:
            r = conn.execute("SELECT value FROM meta WHERE key='categories'").fetchone()
        finally:
            conn.close()
        cats = json.loads(r['value']) if r else ["Movie", "Drama", "Show", "Anime"]
    except Exception:
        cats = ["Movie", "Drama", "Show", "Anime"]
    # "精选"置顶，作为默认页
    cats = ["Featured"] + [c for c in cats if c != "Featured"]
    return jsonify({"categories": cats})


@app.route('/api/OVideo/list', methods=['GET'])
def ovideo_list():
    ensure_video_db()
    user_id = request.args.get('user_id')
    if user_id and user_id in VIDEO_MODULE_BLOCKED_USERS:
        return jsonify({"items": [], "has_more": False, "page": 0})

    category = request.args.get('category', 'Movie')
    sort = request.args.get('sort', 'update')
    page = _arg_int('page', 0, 0, 100000)
    page_size = _arg_int('page_size', 24, 1, 60)

    where, params = [], []
    if category == 'Featured':
        pass                                   # 不加分类条件（包括 Show）
    elif category == 'Documentary':
        where.append("has_documentary=1")
    else:
        where.append("category=?"); params.append(category)

    where.append("hide_blacklisted=0")
    region_kw, type_kw = _get_block_config(user_id)
    bc, bp = _block_where(region_kw, type_kw)
    where += bc; params += bp

    max_year = _parse_max_year()
    if max_year is not None:
        where.append("release_year IS NOT NULL AND release_year <= ?")
        params.append(max_year)

    # （未启用）Featured 按上映日期排序时 Drama 改用 update − N 天：
    # if category == 'Featured' and sort == 'date':
    #     n = int(FEATURED_DRAMA_DATE_OFFSET_DAYS)
    #     order = (f"CASE WHEN category='Drama' THEN date(update_sort_key, '-{n} days') "
    #              f"ELSE release_sort_key END DESC")
    order = _order_clause(sort)

    sql = (f"SELECT category, item_json FROM videos WHERE {' AND '.join(where)} "
           f"ORDER BY {order} LIMIT ? OFFSET ?")
    params += [page_size + 1, page * page_size]
    conn = _get_video_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    has_more = len(rows) > page_size
    items = []
    for r in rows[:page_size]:
        it = json.loads(r['item_json'])
        it['category'] = r['category']
        items.append(it)
    return jsonify({"items": items, "has_more": has_more, "page": page})


@app.route('/api/OVideo/filter', methods=['GET'])
def ovideo_filter():
    ensure_video_db()
    user_id = request.args.get('user_id')
    if user_id and user_id in VIDEO_MODULE_BLOCKED_USERS:
        return jsonify({"items": [], "has_more": False, "page": 0})

    category = request.args.get('category')
    f_type = request.args.get('type')
    f_year = request.args.get('year')
    f_region = request.args.get('region')
    sort = request.args.get('sort', 'update')
    page = _arg_int('page', 0, 0, 100000)
    page_size = _arg_int('page_size', 24, 1, 60)

    where, params = [], []
    if category:
        if category == 'Documentary':
            where.append("has_documentary=1")
        else:
            where.append("category=?"); params.append(category)
    if f_type:
        where.append("norm_types LIKE ?"); params.append(f"%|{f_type}|%")
    if f_year:
        try:
            where.append("release_year=?"); params.append(int(f_year))
        except (TypeError, ValueError):
            where.pop()
    if f_region:
        where.append("norm_region=?"); params.append(f_region)

    where.append("hide_blacklisted=0")
    region_kw, type_kw = _get_block_config(user_id)
    bc, bp = _block_where(region_kw, type_kw)
    where += bc; params += bp

    max_year = _parse_max_year()
    if max_year is not None:
        where.append("release_year IS NOT NULL AND release_year <= ?")
        params.append(max_year)

    sql = (f"SELECT item_json FROM videos WHERE {' AND '.join(where)} "
           f"ORDER BY {_order_clause(sort)} LIMIT ? OFFSET ?")
    params += [page_size + 1, page * page_size]
    conn = _get_video_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    has_more = len(rows) > page_size
    items = [json.loads(r['item_json']) for r in rows[:page_size]]
    return jsonify({"items": items, "has_more": has_more, "page": page})


@app.route('/api/OVideo/filter_options', methods=['GET'])
def ovideo_filter_options():
    ensure_video_db()
    user_id = request.args.get('user_id')
    if user_id and user_id in VIDEO_MODULE_BLOCKED_USERS:
        return jsonify({"types": [], "years": [], "regions": []})

    region_kw, type_kw = _get_block_config(user_id)
    bc, bp = _block_where(region_kw, type_kw)
    wsql = " WHERE " + " AND ".join(["hide_blacklisted=0"] + bc)

    conn = _get_video_conn()
    try:
        type_set = set()
        for r in conn.execute(f"SELECT norm_types FROM videos{wsql}", bp):
            for t in (r['norm_types'] or '').split('|'):
                if t and t != '纪录片':
                    type_set.add(t)
        years = sorted({r['release_year'] for r in
                        conn.execute(f"SELECT DISTINCT release_year FROM videos{wsql}", bp)
                        if r['release_year'] is not None}, reverse=True)
        regions = sorted({r['norm_region'] for r in
                          conn.execute(f"SELECT DISTINCT norm_region FROM videos{wsql}", bp)
                          if r['norm_region'] and r['norm_region'] != '其它'})
    finally:
        conn.close()
    return jsonify({"types": sorted(type_set), "years": years, "regions": regions})


# ---------------- §3.7 搜索（子串 + 模糊） ----------------
@app.route('/api/OVideo/search2', methods=['GET'])
def ovideo_search2():
    ensure_video_db()
    user_id = request.args.get('user_id')
    if user_id and user_id in VIDEO_MODULE_BLOCKED_USERS:
        return jsonify({"items": []})

    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify({"items": []})
    qn = q.replace('·', '').replace(' ', '')
    if not qn:
        qn = q
    limit = _arg_int('limit', 150, 1, 300)

    region_kw, type_kw = _get_block_config(user_id)
    bc, bp = _block_where(region_kw, type_kw)
    base_where = ["hide_blacklisted=0"] + bc
    base_params = list(bp)
    max_year_int = _parse_max_year()
    if max_year_int is not None:
        base_where.append("release_year IS NOT NULL AND release_year <= ?")
        base_params.append(max_year_int)

    cat_order = {"Movie": 0, "Drama": 1, "Show": 2, "Anime": 3}
    conn = _get_video_conn()
    try:
        # ---------- 阶段 1：子串匹配 ----------
        like, like_n = f"%{q}%", f"%{qn}%"
        cond = ("(name_lower LIKE ? OR name_norm LIKE ? OR alias_lower LIKE ? OR alias_norm LIKE ? "
                "OR types_lower LIKE ? OR director_lower LIKE ? OR director_norm LIKE ? "
                "OR cast_lower LIKE ? OR cast_norm LIKE ? OR intro_lower LIKE ?)")
        exact_params = [like, like_n, like, like_n, like, like, like_n, like, like_n, like]
        sql1 = ("SELECT url, category, item_json, best_rating, "
                "name_lower, name_norm, alias_lower, alias_norm, types_lower, "
                "director_lower, director_norm, cast_lower, cast_norm, intro_lower, "
                "release_sort_key, update_sort_key "
                f"FROM videos WHERE {' AND '.join([cond] + base_where)}")
        exact_rows = conn.execute(sql1, exact_params + base_params).fetchall()

        # 匹配层级 mp（越小越优先）：
        #   完全匹配：0 名称 / 1 又名 / 2 导演 / 3 演员(前2) / 4 演员(3+)
        #   部分匹配：5 名称 / 6 又名 / 7 导演 / 8 演员(前2) / 9 演员(3+) / 10 简介 / 11 类型/其它
        #   模糊匹配：13 名称 / 14 又名 / 15 导演 / 16 演员(前2) / 17 演员(3+)
        BIG = 10 ** 6

        def classify(r):
            name, name_n = r['name_lower'] or '', r['name_norm'] or ''
            alias, alias_n = r['alias_lower'] or '', r['alias_norm'] or ''
            director, director_n = r['director_lower'] or '', r['director_norm'] or ''
            cast_list = (r['cast_lower'] or '').split('\x1f')
            cast_list_n = (r['cast_norm'] or '').split('\x1f')
            intro = r['intro_lower'] or ''

            def cast_exact_pos():
                idx = BIG
                for i, c in enumerate(cast_list):
                    if c == q:
                        idx = min(idx, i); break
                for i, c in enumerate(cast_list_n):
                    if c == qn:
                        idx = min(idx, i); break
                return idx

            def cast_contains_pos():
                idx = BIG
                for i, c in enumerate(cast_list):
                    if c and q in c:
                        idx = min(idx, i); break
                for i, c in enumerate(cast_list_n):
                    if c and qn in c:
                        idx = min(idx, i); break
                return idx

            if name == q or name_n == qn:
                return 0, BIG
            if alias == q or alias_n == qn:
                return 1, BIG
            if director == q or director_n == qn:
                return 2, BIG
            cp = cast_exact_pos()
            if cp != BIG:
                return (3, cp) if cp <= 1 else (4, cp)
            if q in name or qn in name_n:
                return 5, BIG
            if q in alias or qn in alias_n:
                return 6, BIG
            if q in director or qn in director_n:
                return 7, BIG
            cp = cast_contains_pos()
            if cp != BIG:
                return (8, cp) if cp <= 1 else (9, cp)
            if q in intro:
                return 10, BIG
            return 11, BIG

        results_map = {}
        for r in exact_rows:
            mp, cast_pos = classify(r)
            results_map[r['url']] = {
                "url": r['url'], "item_json": r['item_json'],
                "mp": mp, "cast_pos": cast_pos, "fuzzy": 1.0,
                "namelen": len(r['name_lower'] or ''),
                "rating": r['best_rating'] or 0.0,
                "rel": r['release_sort_key'] or "",
                "cat": cat_order.get(r['category'], 4),
                "upd": r['update_sort_key'] or "",
            }

        # ---------- 阶段 2：模糊匹配（内存缓存 + 字符集合预筛） ----------
        FUZZY_TRIGGER = 8
        FUZZY_THRESHOLD = 0.6
        PREFILTER_OVERLAP = 0.6
        if len(results_map) < FUZZY_TRIGGER and len(qn) >= 2:
            candidates = _get_fuzzy_candidates()
            q_set = set(qn)
            qn_len = len(q_set)
            region_block = set(region_kw)
            sm = SequenceMatcher(None)
            sm.set_seq2(qn)                     # 查询词固定为 seq2，索引只算一次

            def overlap(text_set):
                if not text_set or not q_set:
                    return 0.0
                return len(q_set & text_set) / qn_len

            def fuzzy_score(text):
                if not text:
                    return 0.0
                if qn in text:
                    return 1.0
                sm.set_seq1(text)
                whole = sm.ratio() if sm.quick_ratio() >= FUZZY_THRESHOLD else 0.0
                lq, lt = len(qn), len(text)
                best_local = 0.0
                if lt > lq:
                    for i in range(lt - lq + 1):
                        sm.set_seq1(text[i:i + lq])
                        if sm.quick_ratio() < FUZZY_THRESHOLD:
                            continue
                        s = sm.ratio()
                        if s > best_local:
                            best_local = s
                            if best_local >= 0.99:
                                break
                return max(whole, best_local)

            for r in candidates:
                if r['url'] in results_map:
                    continue
                # 在 Python 里复现 SQL base_where 的过滤
                if r['hide'] != 0:
                    continue
                if region_block and r['region'] in region_block:
                    continue
                if type_kw and any(kw in r['raw_types'] for kw in type_kw):
                    continue
                if max_year_int is not None:
                    ry = r['release_year']
                    if ry is None or ry > max_year_int:
                        continue

                best_mp, best_score, best_cast_pos = None, 0.0, BIG
                if overlap(r['name_set']) >= PREFILTER_OVERLAP:
                    s = fuzzy_score(r['name'])
                    if s >= FUZZY_THRESHOLD:
                        best_mp, best_score = 13, s
                if best_mp is None and overlap(r['alias_set']) >= PREFILTER_OVERLAP:
                    s = fuzzy_score(r['alias'])
                    if s >= FUZZY_THRESHOLD:
                        best_mp, best_score = 14, s
                if best_mp is None and overlap(r['director_set']) >= PREFILTER_OVERLAP:
                    s = fuzzy_score(r['director'])
                    if s >= FUZZY_THRESHOLD:
                        best_mp, best_score = 15, s
                if best_mp is None:
                    for i, cset in enumerate(r['cast_sets']):
                        if overlap(cset) < PREFILTER_OVERLAP:
                            continue
                        s = fuzzy_score(r['cast_list'][i])
                        if s >= FUZZY_THRESHOLD and s > best_score:
                            best_score = s
                            best_cast_pos = i
                    if best_cast_pos != BIG:
                        best_mp = 16 if best_cast_pos <= 1 else 17

                if best_mp is not None:
                    results_map[r['url']] = {
                        "url": r['url'], "item_json": None,
                        "mp": best_mp, "cast_pos": best_cast_pos, "fuzzy": best_score,
                        "namelen": r['name_len'], "rating": r['rating'],
                        "rel": r['rel'], "cat": cat_order.get(r['category'], 4), "upd": r['upd'],
                    }

        # 为模糊命中的项批量补 item_json
        missing = [u for u, v in results_map.items() if v['item_json'] is None]
        CHUNK = 400
        for i in range(0, len(missing), CHUNK):
            chunk = missing[i:i + CHUNK]
            ph = ",".join("?" * len(chunk))
            for r in conn.execute(f"SELECT url, item_json FROM videos WHERE url IN ({ph})", chunk):
                if r['url'] in results_map:
                    results_map[r['url']]['item_json'] = r['item_json']
    finally:
        conn.close()

    # 排序（多趟稳定排序：从最次要到最主要）
    # 显著性：mp > 上映日期 > 评分 > 短名 > 模糊分 > 演员位次 > 分类 > 更新时间
    scored = list(results_map.values())
    scored.sort(key=lambda x: x['upd'], reverse=True)
    scored.sort(key=lambda x: x['cat'])
    scored.sort(key=lambda x: x['cast_pos'])
    scored.sort(key=lambda x: x['fuzzy'], reverse=True)
    scored.sort(key=lambda x: x['namelen'])
    scored.sort(key=lambda x: x['rating'], reverse=True)
    scored.sort(key=lambda x: x['rel'], reverse=True)
    scored.sort(key=lambda x: x['mp'])

    items = [json.loads(s['item_json']) for s in scored[:limit] if s['item_json']]
    return jsonify({"items": items, "has_more": False, "page": 0})


# ---------------- §3.8 举报 / 寻片（写入统一会话 §2B） ----------------
@app.route('/api/OVideo/report', methods=['POST'])
def report_video_link():
    data = _json_body()
    user_id = data.get('user_id')
    source_url = data.get('source_url')
    episode_url = data.get('episode_url')
    if not user_id or not (source_url or episode_url):
        return jsonify({"error": "Invalid params"}), 400
    report_type = data.get('report_type', 'other')
    if report_type not in ALLOWED_REPORT_TYPES:
        report_type = 'other'
    if _too_frequent(report_last_time, user_id, 10):
        return jsonify({"error": "Too frequent"}), 429

    video_title = data.get('video_title', '')
    channel_name = data.get('channel_name', '')
    episode_name = data.get('episode_name', '')
    real_url = data.get('real_url', '')
    note = (data.get('note', '') or '')[:500]
    app_version = data.get('app_version', '')
    now = now_iso()

    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO video_link_reports
                (user_id, video_title, source_url, episode_url, channel_name,
                 episode_name, real_url, report_type, note, app_version,
                 first_at, last_at, count, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,'pending')
            ON CONFLICT(user_id, episode_url, report_type)
            DO UPDATE SET last_at=?, count=count+1, note=excluded.note, status='pending'
        ''', (user_id, video_title, source_url, episode_url, channel_name,
              episode_name, real_url, report_type, note, app_version, now, now, now))

        tk = support_thread_key('ONews', 'report', user_id, episode_url)
        sub = " · ".join([x for x in [channel_name, episode_name] if x])
        support_upsert_thread(c, 'ONews', tk, 'report', user_id, data.get('user_type'),
                              title=(video_title or '(未知影片)'), subtitle=sub,
                              ref_id=episode_url, app_version=app_version)
        body = f"报错反馈：{REPORT_TYPE_NAMES.get(report_type, report_type)}"
        if sub:
            body += f"（{sub}）"
        if note:
            body += f"\n补充说明：{note}"
        support_add_message(c, 'ONews', tk, 'user', body)
        conn.commit()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/api/OVideo/wish', methods=['POST'])
def submit_video_wish():
    data = _json_body()
    user_id = data.get('user_id')
    wish_content = (data.get('wish_content', '') or '').strip()[:200]
    if not user_id or not wish_content:
        return jsonify({"error": "Invalid params"}), 400
    if _too_frequent(wish_last_time, user_id, 10):
        return jsonify({"error": "Too frequent"}), 429

    user_type = _norm_user_type(user_id, data.get('user_type'))
    keyword = (data.get('keyword', '') or '')[:100]
    app_version = data.get('app_version', '')
    now = now_iso()

    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO video_wish_requests
                (user_id, user_type, keyword, wish_content, app_version,
                 first_at, last_at, count, status, reply_status)
            VALUES (?,?,?,?,?,?,?,1,'pending','none')
            ON CONFLICT(user_id, wish_content)
            DO UPDATE SET last_at=?, count=count+1, status='pending', keyword=excluded.keyword
        ''', (user_id, user_type, keyword, wish_content, app_version, now, now, now))
        row = c.execute("SELECT id FROM video_wish_requests WHERE user_id=? AND wish_content=?",
                        (user_id, wish_content)).fetchone()
        if row:
            tk = support_thread_key('ONews', 'wish', row['id'])
            support_upsert_thread(c, 'ONews', tk, 'wish', user_id, user_type,
                                  title=wish_content,
                                  subtitle=(f"搜索词: {keyword}" if keyword else ''),
                                  ref_id=row['id'], app_version=app_version)
            support_add_message(c, 'ONews', tk, 'user', f"我想看：{wish_content}")
        conn.commit()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


def _my_unread_replies(sql, user_id):
    if not user_id:
        return jsonify({"replies": []})
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        return jsonify({"replies": [dict(r) for r in conn.execute(sql, (user_id,)).fetchall()]})
    finally:
        conn.close()


def _ack_reply(table):
    data = _json_body()
    user_id = data.get('user_id')
    reply_id = data.get('id')
    if not user_id or not reply_id:
        return jsonify({"error": "Invalid params"}), 400
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    try:
        conn.execute(f"UPDATE {table} SET reply_status='read' WHERE id=? AND user_id=?",
                     (reply_id, user_id))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route('/api/OVideo/wish/my_replies', methods=['GET'])
def get_my_wish_replies():
    return _my_unread_replies('''
        SELECT id, wish_content, admin_reply, replied_at
        FROM video_wish_requests
        WHERE user_id=? AND reply_status='unread'
          AND admin_reply IS NOT NULL AND admin_reply != ''
        ORDER BY replied_at DESC''', request.args.get('user_id'))


@app.route('/api/OVideo/wish/ack_reply', methods=['POST'])
def ack_wish_reply():
    return _ack_reply('video_wish_requests')


@app.route('/api/OVideo/report/my_replies', methods=['GET'])
def get_my_report_replies():
    return _my_unread_replies('''
        SELECT id, video_title, episode_name, admin_reply, replied_at
        FROM video_link_reports
        WHERE user_id=? AND reply_status='unread'
          AND admin_reply IS NOT NULL AND admin_reply != ''
        ORDER BY replied_at DESC''', request.args.get('user_id'))


@app.route('/api/OVideo/report/ack_reply', methods=['POST'])
def ack_report_reply():
    return _ack_reply('video_link_reports')


# ---------------- §3.9 埋点 / 点数 ----------------
@app.route('/api/OVideo/track', methods=['POST'])
def track_event():
    data = _json_body()
    user_id = data.get('user_id')
    user_type = data.get('user_type', 'apple')
    video_url = data.get('video_url')
    video_title = data.get('video_title', '')
    event_type = data.get('event_type')
    source = data.get('source')
    app_version = data.get('app_version', '')
    episode_key = data.get('episode_key')
    if not user_id or not video_url or event_type not in ALLOWED_EVENT_TYPES:
        return jsonify({"error": "Invalid params"}), 400

    # 权限来源：客户端上报 + 服务器兜底纠正
    access_type = resolve_video_access_type(user_id, data.get('access_type'), episode_key or video_url)
    now = now_iso()
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    try:
        c = conn.cursor()
        c.execute('''
            INSERT INTO user_video_events
                (user_id, user_type, video_url, video_title, event_type,
                 first_at, last_at, count, access_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(user_id, video_url, event_type)
            DO UPDATE SET last_at = ?, count = count + 1, access_type = ?
        ''', (user_id, user_type, video_url, video_title, event_type, now, now,
              access_type, now, access_type))
        c.execute('''
            INSERT INTO event_logs
                (user_id, user_type, video_url, video_title, event_type,
                 created_at, source, app_version, access_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, user_type, video_url, video_title, event_type, now,
              source, app_version, access_type))
        conn.commit()
        return jsonify({"status": "ok", "access_type": access_type}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


def _guest_quota_payload(cfg):
    return {
        "daily_quota": cfg['daily_quota'], "used_today": 0,
        "remaining": 0, "daily_remaining": 0,
        "bonus_remaining": 0, "total_remaining": 0,
        "bonus_just_granted": False,
        "unlocked_episodes": [], "unlocked_news": [],
        "invite_code": None, "invite_reward_count": 0,
        "has_redeemed_invite": False,
        "invite_reward_points": cfg['invite_reward_points'],
        "logged_in": False
    }


@app.route('/api/OVideo/quota/status', methods=['GET'])
def video_quota_status():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
    cfg = get_video_points_config()
    daily_quota = cfg['daily_quota']
    if not is_real_login_user(user_id):
        return jsonify(_guest_quota_payload(cfg))
    maybe_cleanup_old_unlocks()
    today = today_str()
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        row, just_granted = _ensure_points(c, 'video_points', user_id, cfg)
        conn.commit()
        bonus_remaining = row['bonus_remaining']
        episodes = [r['episode_key'] for r in c.execute(
            "SELECT episode_key FROM video_free_unlocks WHERE user_id=? AND unlock_date=?",
            (user_id, today)).fetchall()]
        daily_used = _video_daily_used(c, user_id, today)
        invite_code = row['invite_code']
        invite_reward_count = row['invite_reward_count']
        has_redeemed = bool(row['invited_by_code'])
    finally:
        conn.close()
    daily_remaining = max(0, daily_quota - daily_used)
    total = bonus_remaining + daily_remaining
    return jsonify({
        "daily_quota": daily_quota, "used_today": daily_used,
        "remaining": total, "daily_remaining": daily_remaining,
        "bonus_remaining": bonus_remaining, "total_remaining": total,
        "bonus_just_granted": just_granted,
        "unlocked_episodes": episodes, "unlocked_news": [],
        "invite_code": invite_code, "invite_reward_count": invite_reward_count,
        "has_redeemed_invite": has_redeemed,
        "invite_reward_points": cfg['invite_reward_points'], "logged_in": True
    })


@app.route('/api/OVideo/quota/unlock', methods=['POST'])
def video_quota_unlock():
    data = _json_body()
    user_id = data.get('user_id')
    episode_key = data.get('episode_key')
    if not user_id or not episode_key:
        return jsonify({"error": "Missing params"}), 400
    exceeded = {"status": "quota_exceeded", "remaining": 0,
                "bonus_remaining": 0, "daily_remaining": 0, "total_remaining": 0}
    if not is_real_login_user(user_id):
        return jsonify(exceeded)
    cfg = get_video_points_config()
    daily_quota = cfg['daily_quota']
    today, now = today_str(), now_iso()
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("BEGIN IMMEDIATE")
        row, _ = _ensure_points(c, 'video_points', user_id, cfg)
        bonus_remaining = row['bonus_remaining']
        du = _video_daily_used(c, user_id, today)
        dr = max(0, daily_quota - du)
        if c.execute("SELECT 1 FROM video_free_unlocks WHERE user_id=? AND episode_key=? AND unlock_date=?",
                     (user_id, episode_key, today)).fetchone():
            c.execute("COMMIT")
            total = bonus_remaining + dr
            return jsonify({"status": "already_unlocked", "remaining": total,
                            "bonus_remaining": bonus_remaining,
                            "daily_remaining": dr, "total_remaining": total})
        if bonus_remaining > 0:
            source = 'bonus'
        elif dr > 0:
            source = 'daily'
        else:
            c.execute("COMMIT")
            return jsonify(exceeded)
        c.execute('''INSERT INTO video_free_unlocks
                     (user_id, episode_key, unlock_date, video_title, created_at, source)
                     VALUES (?,?,?,?,?,?)''',
                  (user_id, episode_key, today, data.get('video_title', ''), now, source))
        if source == 'bonus':
            c.execute("UPDATE video_points SET bonus_remaining=bonus_remaining-1 WHERE user_id=?", (user_id,))
            bonus_remaining -= 1
        else:
            dr = max(0, dr - 1)
        c.execute("COMMIT")
        total = bonus_remaining + dr
        return jsonify({"status": "success", "remaining": total,
                        "bonus_remaining": bonus_remaining,
                        "daily_remaining": dr, "total_remaining": total})
    except Exception as e:
        try: c.execute("ROLLBACK")
        except Exception: pass
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ---------------- §3.10 后台：视频统计 / 举报 / 寻片 ----------------
def _period_where(period):
    """today / 7d / all -> SQL 片段（固定常量，无注入）"""
    if period == 'today':
        return "AND date(created_at) = date('now', '+8 hours')"
    if period == '7d':
        return "AND created_at >= datetime('now', '+8 hours', '-7 days')"
    return ""


# 后台"用户视频明细"的固定筛选（白名单，绝不拼接外部输入）
VIDEO_DETAIL_FILTERS = {
    'online':  "video_url NOT LIKE '%.m3u8'",
    'offline': "video_url LIKE '%.m3u8'",
    'vip':     "access_type IN ('subscription','vip_permanent')",
    'points':  "access_type LIKE 'points%'",
}


def _video_detail_filter(filter_key, legacy_suffix=''):
    """新版网页传 filter=online|offline|vip|points；
       兼容旧网页（浏览器缓存）传的 suffix SQL 片段：只做识别，不拼接。"""
    key = (filter_key or '').strip().lower()
    if not key and legacy_suffix:
        s = legacy_suffix.lower().replace(' ', '')
        if 'm3u8' in s:
            key = 'online' if 'notlike' in s else 'offline'
        elif 'subscription' in s or 'vip_permanent' in s:
            key = 'vip'
        elif 'points' in s:
            key = 'points'
    clause = VIDEO_DETAIL_FILTERS.get(key)
    return f" AND {clause}" if clause else ''


@app.route('/admin/api/video/user_details', methods=['GET'])
@require_admin
def admin_video_user_details():
    maybe_cleanup_old_unlocks()
    user_id = request.args.get('user_id')
    event_type = request.args.get('type')
    if not user_id or not event_type:
        return jsonify({"error": "Missing parameters"}), 400
    extra = _video_detail_filter(request.args.get('filter'), request.args.get('suffix', ''))
    sql = f'''
        SELECT date(created_at) AS day, video_url, video_title,
               MAX(created_at) AS last_time,
               COUNT(*) AS click_count,
               GROUP_CONCAT(DISTINCT source) AS sources,
               GROUP_CONCAT(DISTINCT NULLIF(app_version,'')) AS versions,
               GROUP_CONCAT(DISTINCT COALESCE(NULLIF(access_type,''),'unknown')) AS access_types
        FROM event_logs
        WHERE user_id = ? AND event_type = ? AND created_at >= ? {extra}
        GROUP BY day, video_url
        ORDER BY day DESC, last_time DESC
    '''
    return jsonify(_query_analytics(sql, (user_id, event_type, analytics_cutoff_iso())))


@app.route('/admin/api/overview', methods=['GET'])
@require_admin
def admin_overview():
    today = today_str()
    q = lambda sql, p=(): _query_analytics(sql, p)[0]['c']
    return jsonify({
        "total_users":           q("SELECT COUNT(DISTINCT user_id) AS c FROM event_logs"),
        "total_play_events":     q("SELECT COUNT(*) AS c FROM event_logs WHERE event_type='play'"),
        "total_download_events": q("SELECT COUNT(*) AS c FROM event_logs WHERE event_type='download_complete'"),
        "today_active_users":    q("SELECT COUNT(DISTINCT user_id) AS c FROM event_logs WHERE date(created_at)=?", (today,)),
        "today_play":            q("SELECT COUNT(*) AS c FROM event_logs WHERE event_type='play' AND date(created_at)=?", (today,)),
        "today_download":        q("SELECT COUNT(*) AS c FROM event_logs WHERE event_type='download_complete' AND date(created_at)=?", (today,)),
        "pending_reports":       q("SELECT COUNT(DISTINCT episode_url) AS c FROM video_link_reports WHERE status='pending'"),
        "today_play_vip":        q("SELECT COUNT(*) AS c FROM event_logs WHERE event_type='play' AND access_type IN ('subscription','vip_permanent') AND date(created_at)=?", (today,)),
        "today_play_points":     q("SELECT COUNT(*) AS c FROM event_logs WHERE event_type='play' AND access_type LIKE 'points%' AND date(created_at)=?", (today,)),
    })


@app.route('/admin/api/top_videos', methods=['GET'])
@require_admin
def admin_top_videos():
    event_type = request.args.get('type', 'play')
    where_time = _period_where(request.args.get('period', 'all'))
    limit = _arg_int('limit', 20, 1, 500)
    sql = f'''
        SELECT video_url, video_title,
               COUNT(DISTINCT user_id) AS unique_users,
               COUNT(*) AS total_count
        FROM event_logs
        WHERE event_type = ? {where_time}
        GROUP BY video_url
        ORDER BY unique_users DESC, total_count DESC
        LIMIT ?
    '''
    return jsonify(_query_analytics(sql, (event_type, limit)))


@app.route('/admin/api/video_users', methods=['GET'])
@require_admin
def admin_video_users():
    return jsonify(_query_analytics('''
        SELECT user_id, first_at, last_at, count
        FROM user_video_events
        WHERE video_url = ? AND event_type = ?
        ORDER BY last_at DESC
    ''', (request.args.get('video_url'), request.args.get('type', 'play'))))


@app.route('/admin/api/daily_trend', methods=['GET'])
@require_admin
def admin_daily_trend():
    return jsonify(_query_analytics('''
        SELECT date(created_at) AS day, event_type,
               COUNT(*) AS cnt, COUNT(DISTINCT user_id) AS uu
        FROM event_logs
        WHERE created_at >= datetime('now', '+8 hours', '-30 days')
        GROUP BY day, event_type
        ORDER BY day ASC
    '''))


@app.route('/admin/api/video_reports', methods=['GET'])
@require_admin
def admin_video_reports():
    where = "WHERE status='pending'" if request.args.get('status', 'pending') == 'pending' else ""
    return jsonify(_query_analytics(f'''
        SELECT video_title, source_url, episode_url, channel_name, episode_name,
               report_type,
               MAX(real_url) AS real_url,
               COUNT(DISTINCT user_id) AS unique_users,
               GROUP_CONCAT(DISTINCT user_id) AS user_ids,
               SUM(count) AS total_count,
               MAX(last_at) AS last_at,
               GROUP_CONCAT(DISTINCT NULLIF(note,'')) AS notes,
               MAX(admin_reply) AS admin_reply,
               MAX(reply_status) AS reply_status
        FROM video_link_reports
        {where}
        GROUP BY episode_url, report_type
        ORDER BY unique_users DESC, total_count DESC
        LIMIT 200
    '''))


@app.route('/admin/api/resolve_report', methods=['POST'])
@require_admin
def admin_resolve_report():
    """reply 留空=仅标记已处理；填写=回复举报该集的所有用户"""
    data = _json_body()
    episode_url = data.get('episode_url')
    reply = (data.get('reply', '') or '').strip()[:1000]
    if not episode_url:
        return jsonify({"error": "Missing episode_url"}), 400
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        if reply:
            c.execute('''UPDATE video_link_reports
                         SET status='resolved', admin_reply=?, reply_status='unread', replied_at=?
                         WHERE episode_url=?''', (reply, now_iso(), episode_url))
            users = c.execute('''SELECT user_id, MAX(video_title) AS vt,
                                        MAX(channel_name) AS cn, MAX(episode_name) AS en
                                 FROM video_link_reports WHERE episode_url=? GROUP BY user_id''',
                              (episode_url,)).fetchall()
            for u in users:
                tk = support_thread_key('ONews', 'report', u['user_id'], episode_url)
                sub = " · ".join([x for x in [u['cn'], u['en']] if x])
                support_upsert_thread(c, 'ONews', tk, 'report', u['user_id'], None,
                                      title=(u['vt'] or '(未知影片)'), subtitle=sub, ref_id=episode_url)
                support_add_message(c, 'ONews', tk, 'admin', reply)
        else:
            c.execute("UPDATE video_link_reports SET status='resolved' WHERE episode_url=?", (episode_url,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/admin/api/video_wishes', methods=['GET'])
@require_admin
def admin_video_wishes():
    where = "WHERE status='pending'" if request.args.get('status', 'pending') == 'pending' else ""
    return jsonify(_query_analytics(f'''
        SELECT id, user_id, user_type, keyword, wish_content, app_version,
               count, first_at, last_at, status, admin_reply, reply_status
        FROM video_wish_requests
        {where}
        ORDER BY (status='pending') DESC, last_at DESC
        LIMIT 200
    '''))


@app.route('/admin/api/resolve_wish', methods=['POST'])
@require_admin
def admin_resolve_wish():
    """reply 留空=仅标记已处理；填写=回复用户"""
    data = _json_body()
    wish_id = data.get('id')
    reply = (data.get('reply', '') or '').strip()[:1000]
    if not wish_id:
        return jsonify({"error": "Missing id"}), 400
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        if reply:
            c.execute('''UPDATE video_wish_requests
                         SET status='resolved', admin_reply=?, reply_status='unread', replied_at=?
                         WHERE id=?''', (reply, now_iso(), wish_id))
            w = c.execute("SELECT * FROM video_wish_requests WHERE id=?", (wish_id,)).fetchone()
            if w:
                tk = support_thread_key('ONews', 'wish', w['id'])
                support_upsert_thread(c, 'ONews', tk, 'wish', w['user_id'], w['user_type'],
                                      title=w['wish_content'],
                                      subtitle=(f"搜索词: {w['keyword']}" if w['keyword'] else ''),
                                      ref_id=w['id'])
                support_add_message(c, 'ONews', tk, 'admin', reply)
        else:
            c.execute("UPDATE video_wish_requests SET status='resolved' WHERE id=?", (wish_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/admin/api/top_users', methods=['GET'])
@require_admin
def admin_top_users():
    return jsonify(_query_analytics('''
        SELECT user_id,
               MAX(user_type) AS user_type,
               COUNT(DISTINCT CASE WHEN event_type='play' THEN video_url END) AS play_videos,
               COUNT(DISTINCT CASE WHEN event_type='download_complete' THEN video_url END) AS download_videos,
               COUNT(DISTINCT CASE WHEN event_type='play' AND video_url NOT LIKE '%.m3u8' THEN video_url END) AS online_play,
               COUNT(DISTINCT CASE WHEN event_type='play' AND video_url LIKE '%.m3u8' THEN video_url END) AS offline_play,
               COUNT(DISTINCT CASE WHEN event_type='play'
                     AND access_type IN ('subscription','vip_permanent') THEN video_url END) AS vip_play,
               COUNT(DISTINCT CASE WHEN event_type='play'
                     AND access_type LIKE 'points%' THEN video_url END) AS points_play,
               COUNT(*) AS total_actions,
               MAX(created_at) AS last_active
        FROM event_logs
        GROUP BY user_id
        ORDER BY total_actions DESC
        LIMIT 50
    '''))





# ╔══════════════════════════════════════════════════════════════════════╗
# ║  §7 启动入口                                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝

def init_all():
    # §1 公共
    init_user_db()
    init_anonymous_sub_db()
    init_analytics_base()
    # §2A 点数账本
    init_points_db()
    # 各模块表（必须在客服迁移之前：迁移要读 video_wish_requests / video_link_reports）
    init_ovideo_analytics_db()
    init_onews_analytics_db()
    init_finance_user_db()
    init_finance_analytics_db()
    # §2B 客服
    init_support_db()
    migrate_support_threads_once()
    # §3 OVideo.db
    ensure_video_db(force=True)


if __name__ == '__main__':
    init_all()
    # 启动时也做一次日常维护（清理过期流水 + 截断 WAL + 按需 VACUUM，后台线程执行）
    maybe_cleanup_old_unlocks()
    print("多应用服务器正在启动...")
    print(f"支持的应用: {', '.join(ALLOWED_APPS)}")
    print(f"资源目录被定位在: {BASE_RESOURCES_DIR}")
    host_ip = '0.0.0.0'
    port = 5001
    print("请确保您的手机和电脑连接到同一个Wi-Fi网络")
    print(f"在iOS App中请使用 http://{host_ip}:{port}/api/ONews/... 访问")
    app.run(host=host_ip, port=port, debug=False, threaded=True)