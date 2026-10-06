"""
tag_hot.py —— 热门 Tag 共享读写层（纯 Python，不依赖 Qt；PyQt5 / PyQt6 程序都能直接用）

数据文件：~/Coding/Financial_System/Modules/tags_filter.json （与其他脚本共用，格式保持不变）
{
    "BLACKLIST_TAGS": [...],      # 旧字段，本模块不读不改，原样保留
    "HOT_TAGS":   [...],          # 热门
    "HOT_TAGS_T": [...]           # 热门T（核心热门，约定为 HOT_TAGS 的子集）
}

* 等级：None < 「热门」 < 「热门T」；只写在 HOT_TAGS_T 里的也按「热门T」算
* 设为热门T → 同时保证在 HOT_TAGS 与 HOT_TAGS_T 中；降为热门 → 仅从 HOT_TAGS_T 移除；移出 → 两处都删
* 只改被操作的那个 Tag，其余条目、顺序、其他键全部保留
* 与黑名单互斥：设为热门时自动从 Tag_Blacklist.json 移出（exclusive=False 可关闭）
* 写入：跨进程文件锁 + 写前重读 + 临时文件 + os.replace 原子替换；文件损坏时拒绝写入
"""
import os
import sys
import json
import tempfile
import threading
import subprocess
import unicodedata
from collections import OrderedDict
from contextlib import contextmanager

try:
    import fcntl
except ImportError:          # Windows
    fcntl = None

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
MODULES_DIR = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules")
HOT_PATH = os.path.join(MODULES_DIR, "tags_filter.json")
_LOCK_PATH = os.path.join(MODULES_DIR, ".tags_filter.lock")

KEY_HOT = "HOT_TAGS"
KEY_T = "HOT_TAGS_T"

LEVEL_T = "热门T"
LEVEL_HOT = "热门"
LEVELS = (LEVEL_T, LEVEL_HOT)                       # 优先级从高到低
LEVEL_COLORS = {LEVEL_T: "#EBCB8B", LEVEL_HOT: "#A3BE8C"}
LEVEL_ICONS = {LEVEL_T: "★", LEVEL_HOT: "☆"}
LEVEL_TEXT_COLOR = "#2E3440"                        # 浅色底上用深色字

_lock = threading.RLock()
_state = {"sig": None, "data": {KEY_HOT: [], KEY_T: []}, "map": {}, "error": None}


def norm_tag(tag):
    return unicodedata.normalize("NFKC", str(tag)).strip().casefold()


def signature(path=HOT_PATH):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def _empty():
    return {KEY_HOT: [], KEY_T: []}


def _clean_list(raw, key):
    lst = raw.get(key, [])
    if lst is None:
        return []
    if isinstance(lst, str):
        lst = [lst]
    if not isinstance(lst, (list, tuple)):
        raise ValueError(f"「{key}」必须是数组")
    out, seen = [], set()
    for t in lst:
        if t is None:
            continue
        s = str(t).strip()
        if not s:
            continue
        k = norm_tag(s)
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _parse(raw):
    if not isinstance(raw, dict):
        raise ValueError("顶层必须是 JSON 对象 {...}")
    hot = _clean_list(raw, KEY_HOT)
    t = _clean_list(raw, KEY_T)
    m = {}
    for s in hot:
        m[norm_tag(s)] = LEVEL_HOT
    for s in t:
        m[norm_tag(s)] = LEVEL_T          # T 优先
    return {KEY_HOT: hot, KEY_T: t}, m


def _read_raw(path=HOT_PATH):
    with open(path, "r", encoding="utf-8-sig") as f:
        txt = f.read()
    if not txt.strip():
        return OrderedDict()
    return json.loads(txt, object_pairs_hook=OrderedDict)


def load(force=False):
    """返回 {'HOT_TAGS': [...], 'HOT_TAGS_T': [...]} 的副本；按文件签名缓存"""
    with _lock:
        sig = signature()
        if force or sig != _state["sig"]:
            if not os.path.exists(HOT_PATH):
                _state.update(data=_empty(), map={}, error=None)
            else:
                try:
                    data, m = _parse(_read_raw())
                    _state.update(data=data, map=m, error=None)
                except Exception as e:
                    _state["error"] = f"{type(e).__name__}: {e}"
                    print(f"[热门] 解析 {HOT_PATH} 失败，沿用上次内容: {e}")
            _state["sig"] = sig
        return {k: list(v) for k, v in _state["data"].items()}


def last_error():
    load()
    return _state["error"]


def tag_map():
    load()
    return dict(_state["map"])


def level_of(tag):
    load()
    return _state["map"].get(norm_tag(tag))


def levels():
    """按等级返回 {'热门T': [...], '热门': [...仅热门、不含T...]}"""
    d = load()
    tk = {norm_tag(t) for t in d[KEY_T]}
    return {LEVEL_T: list(d[KEY_T]),
            LEVEL_HOT: [t for t in d[KEY_HOT] if norm_tag(t) not in tk]}


def counts():
    load()
    c = {LEVEL_T: 0, LEVEL_HOT: 0}
    for lv in _state["map"].values():
        c[lv] += 1
    return c


def hot_tags(tags, levels=None):
    """返回 [(原tag, 等级), ...]；levels=None 表示所有等级"""
    if not tags:
        return []
    if isinstance(tags, str):
        tags = [tags]
    load()
    m = _state["map"]
    out, seen = [], set()
    for t in tags:
        k = norm_tag(t)
        lv = m.get(k)
        if lv and (levels is None or lv in levels) and k not in seen:
            seen.add(k)
            out.append((str(t), lv))
    return out


def is_hot(tags, levels=None):
    return bool(hot_tags(tags, levels))


@contextmanager
def _file_lock():
    os.makedirs(MODULES_DIR, exist_ok=True)
    fh = open(_LOCK_PATH, "a+")
    try:
        if fcntl:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if fcntl:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _write_raw(obj):
    os.makedirs(MODULES_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=MODULES_DIR, prefix=".tags_filter.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=4)   # 与原文件缩进一致
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, HOT_PATH)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _edit_list(lst, s, k, want):
    """want=True：保证 lst 含 s（已存在则保持原位置）；want=False：删除所有等价项"""
    if lst is None:
        lst = []
    elif isinstance(lst, str):
        lst = [lst]
    else:
        lst = list(lst)
    present = any(x is not None and norm_tag(x) == k for x in lst)
    if want:
        if not present:
            lst.append(s)
        return lst
    return [x for x in lst if x is None or norm_tag(x) != k]


def set_level(tag, level, exclusive=True):
    """level ∈ {'热门T', '热门', None}；None 表示移出热门。返回新等级"""
    s = str(tag).strip()
    if not s:
        raise ValueError("Tag 为空")
    if level is not None and level not in LEVELS:
        raise ValueError(f"未知热门等级: {level}")
    k = norm_tag(s)
    with _lock, _file_lock():
        if os.path.exists(HOT_PATH):
            try:
                raw = _read_raw()
                _parse(raw)                     # 只校验
            except Exception as e:
                raise RuntimeError(
                    f"热门文件格式有误，为避免覆盖你的手动修改，本次未写入。\n"
                    f"请先修复：{HOT_PATH}\n{e}")
        else:
            raw = OrderedDict([("BLACKLIST_TAGS", []), (KEY_HOT, []), (KEY_T, [])])
        raw[KEY_HOT] = _edit_list(raw.get(KEY_HOT), s, k, level in LEVELS)
        raw[KEY_T] = _edit_list(raw.get(KEY_T), s, k, level == LEVEL_T)
        _write_raw(raw)
    load(force=True)

    if level and exclusive:                     # 与黑名单互斥
        try:
            import tag_blacklist as _TB
            if _TB.group_of(s):
                _TB.set_group(s, None, exclusive=False)
        except Exception as e:
            print(f"[热门] 同步移出黑名单失败: {e}")
    return level


def add(tag, level=LEVEL_HOT):
    return set_level(tag, level)


def remove(tag):
    return set_level(tag, None)


def toggle(tag, level):
    return set_level(tag, None if level_of(tag) == level else level)


def ensure_file():
    if os.path.exists(HOT_PATH):
        return
    with _lock, _file_lock():
        if not os.path.exists(HOT_PATH):
            _write_raw(OrderedDict([("BLACKLIST_TAGS", []), (KEY_HOT, []), (KEY_T, [])]))


def open_in_editor():
    ensure_file()
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", HOT_PATH])
        elif sys.platform == "win32":
            os.startfile(HOT_PATH)   # noqa
        else:
            subprocess.Popen(["xdg-open", HOT_PATH])
    except Exception as e:
        print(f"[热门] 打开文件失败: {e}")