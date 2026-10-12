"""
tag_hot.py —— 热门 Tag 共享读写层（纯 Python，不依赖 Qt；PyQt5 / PyQt6 程序都能直接用）

数据文件：~/Coding/Financial_System/Modules/tags_filter.json （与其他脚本共用，格式保持不变）
{
    "BLACKLIST_TAGS": [...],      # 旧字段，本模块不读不改，原样保留
    "HOT_TAGS":   [...],          # 「热门」
    "HOT_TAGS_T": [...]           # 「热门T」
}

* 两个列表【相互独立】：一个 Tag 可以不属于任何一个、只属于其一、或同时属于两者（巧合，互不推导）
* 写操作只改指定列表里的指定 Tag，其余条目、顺序、其他键全部保留
* 「主等级」：同时属于两者时按 热门T > 热门 取一个，仅用于显示配色 / 兼容旧接口 level_of、tag_map、hot_tags
* 与黑名单互斥：加入任一热门列表时自动从 Tag_Blacklist.json 移出（exclusive=False 可关闭）
* 写入：跨进程文件锁 + 写前重读 + 临时文件 + os.replace 原子替换（保留原文件权限）；文件损坏时拒绝写入
* 命令行：python tag_hot.py [--overlap] [--strip-overlap-from hot|t]
"""
import os
import sys
import json
import time
import shutil
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
try:
    import msvcrt
except ImportError:          # macOS / Linux
    msvcrt = None

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
LEVELS = (LEVEL_T, LEVEL_HOT)                       # 仅表示显示优先级，不代表包含关系
KEY_OF = {LEVEL_T: KEY_T, LEVEL_HOT: KEY_HOT}
LEVEL_COLORS = {LEVEL_T: "#EBCB8B", LEVEL_HOT: "#A3BE8C"}
LEVEL_ICONS = {LEVEL_T: "★", LEVEL_HOT: "☆"}
LEVEL_TEXT_COLOR = "#2E3440"                        # 浅色底上用深色字

_lock = threading.RLock()
_state = {"sig": None, "data": {KEY_HOT: [], KEY_T: []}, "groups": {}, "error": None}


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
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


def _default_raw():
    return OrderedDict([("BLACKLIST_TAGS", []), (KEY_HOT, []), (KEY_T, [])])


def _as_list(lst):
    if lst is None:
        return []
    if isinstance(lst, str):
        return [lst]
    return list(lst)


def _as_level_set(levels):
    """接受 '热门' / ['热门','热门T'] / set 等；修复旧版传字符串时按子串匹配的 bug"""
    if levels is None:
        return None
    if isinstance(levels, str):
        return {levels}
    return set(levels)


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
    data = {KEY_HOT: _clean_list(raw, KEY_HOT), KEY_T: _clean_list(raw, KEY_T)}
    g = {}
    for lv in LEVELS:                                  # 按优先级顺序收集，元组第一个即主等级
        for s in data[KEY_OF[lv]]:
            g.setdefault(norm_tag(s), []).append(lv)
    return data, {k: tuple(v) for k, v in g.items()}


def _read_raw(path=HOT_PATH):
    with open(path, "r", encoding="utf-8-sig") as f:
        txt = f.read()
    if not txt.strip():
        return OrderedDict()
    return json.loads(txt, object_pairs_hook=OrderedDict)


# ----------------------------------------------------------------------
# 读取
# ----------------------------------------------------------------------
def load(force=False):
    """返回 {'HOT_TAGS': [...], 'HOT_TAGS_T': [...]} 的副本；按文件签名缓存"""
    with _lock:
        sig = signature()
        if force or sig != _state["sig"]:
            if not os.path.exists(HOT_PATH):
                _state.update(data=_empty(), groups={}, error=None)
            else:
                try:
                    data, g = _parse(_read_raw())
                    _state.update(data=data, groups=g, error=None)
                except Exception as e:
                    _state["error"] = f"{type(e).__name__}: {e}"
                    print(f"[热门] 解析 {HOT_PATH} 失败，沿用上次内容: {e}")
            _state["sig"] = sig
        return {k: list(v) for k, v in _state["data"].items()}


def last_error():
    load()
    return _state["error"]


def groups_of(tag):
    """该 Tag 所属的热门列表，按优先级排序的元组：() / ('热门',) / ('热门T',) / ('热门T','热门')"""
    load()
    return _state["groups"].get(norm_tag(tag), ())


def has(tag, level):
    return level in groups_of(tag)


def level_of(tag):
    """【兼容】主等级：同时属于两者时返回 热门T；不属于返回 None"""
    g = groups_of(tag)
    return g[0] if g else None


def groups_map():
    load()
    return dict(_state["groups"])


def tag_map():
    """【兼容】norm_tag -> 主等级"""
    load()
    return {k: v[0] for k, v in _state["groups"].items()}


def levels():
    """按列表返回 {'热门T': [...], '热门': [...]}；两个列表各自完整、互不剔除"""
    d = load()
    return {LEVEL_T: list(d[KEY_T]), LEVEL_HOT: list(d[KEY_HOT])}


def counts():
    """各列表各自的条目数（同时属于两者的 Tag 两边都计）"""
    d = load()
    return {LEVEL_T: len(d[KEY_T]), LEVEL_HOT: len(d[KEY_HOT])}


def overlap():
    """同时出现在两个列表中的 Tag（按 HOT_TAGS 中的写法与顺序）"""
    d = load()
    tk = {norm_tag(t) for t in d[KEY_T]}
    return [t for t in d[KEY_HOT] if norm_tag(t) in tk]


def hot_tags_full(tags, levels=None):
    """返回 [(原tag, (命中的等级...)), ...]；levels=None 表示所有列表"""
    if not tags:
        return []
    if isinstance(tags, str):
        tags = [tags]
    wanted = _as_level_set(levels)
    load()
    g = _state["groups"]
    out, seen = [], set()
    for t in tags:
        k = norm_tag(t)
        if k in seen:
            continue
        lvs = g.get(k)
        if not lvs:
            continue
        hit = lvs if wanted is None else tuple(lv for lv in lvs if lv in wanted)
        if hit:
            seen.add(k)
            out.append((str(t), hit))
    return out


def hot_tags(tags, levels=None):
    """【兼容】返回 [(原tag, 命中的主等级), ...]；levels 只筛选对应列表"""
    return [(t, hit[0]) for t, hit in hot_tags_full(tags, levels)]


def is_hot(tags, levels=None):
    return bool(hot_tags_full(tags, levels))


# ----------------------------------------------------------------------
# 写入
# ----------------------------------------------------------------------
@contextmanager
def _file_lock():
    os.makedirs(MODULES_DIR, exist_ok=True)
    fh = open(_LOCK_PATH, "a+")
    locked = False
    try:
        if fcntl:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            locked = True
        elif msvcrt:
            while True:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    locked = True
                    break
                except OSError:
                    time.sleep(0.05)
        yield
    finally:
        try:
            if locked:
                if fcntl:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                elif msvcrt:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            fh.close()


def _write_raw(obj):
    os.makedirs(MODULES_DIR, exist_ok=True)
    try:
        mode = os.stat(HOT_PATH).st_mode & 0o777
    except OSError:
        mode = 0o644
    fd, tmp = tempfile.mkstemp(dir=MODULES_DIR, prefix=".tags_filter.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=4)   # 与原文件缩进一致
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, mode)          # mkstemp 默认 0600，替换后会改掉原文件权限
        except OSError:
            pass
        os.replace(tmp, HOT_PATH)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _load_raw_for_write():
    if os.path.exists(HOT_PATH):
        try:
            raw = _read_raw()
            _parse(raw)                     # 只校验
        except Exception as e:
            raise RuntimeError(
                f"热门文件格式有误，为避免覆盖你的手动修改，本次未写入。\n"
                f"请先修复：{HOT_PATH}\n{e}")
        return raw
    return _default_raw()


def _edit_list(lst, s, k, want):
    """want=True：保证 lst 含 s（已存在则保持原位置与原写法）；want=False：删除所有等价项"""
    lst = _as_list(lst)
    present = any(x is not None and norm_tag(x) == k for x in lst)
    if want:
        if not present:
            lst.append(s)
        return lst
    return [x for x in lst if x is None or norm_tag(x) != k]


def _apply(tag, changes, exclusive=True):
    """changes: {等级: True / False / 'toggle'}；在文件锁内基于磁盘最新内容决定并写入。
    返回写入后的 groups_of(tag)"""
    s = str(tag).strip()
    if not s:
        raise ValueError("Tag 为空")
    for lv in changes:
        if lv not in LEVELS:
            raise ValueError(f"未知热门等级: {lv}")
    k = norm_tag(s)
    added = False
    with _lock, _file_lock():
        raw = _load_raw_for_write()
        dirty = False
        for lv, want in changes.items():
            key = KEY_OF[lv]
            old = _as_list(raw.get(key))
            if want == "toggle":
                want = not any(x is not None and norm_tag(x) == k for x in old)
            new = _edit_list(old, s, k, bool(want))
            if new != old:
                raw[key] = new
                dirty = True
                added = added or bool(want)
        if dirty:
            _write_raw(raw)
    load(force=True)

    if added and exclusive:                     # 与黑名单互斥（在文件锁外调用，避免嵌套锁）
        try:
            import tag_blacklist as _TB
            if _TB.group_of(s):
                _TB.set_group(s, None, exclusive=False)
        except Exception as e:
            print(f"[热门] 同步移出黑名单失败: {e}")
    return groups_of(s)


def set_member(tag, level, on=True, exclusive=True):
    """把 Tag 加入(on=True) / 移出(on=False) 某一个列表，不影响另一个列表"""
    return _apply(tag, {level: bool(on)}, exclusive)


def add(tag, level=LEVEL_HOT, exclusive=True):
    return set_member(tag, level, True, exclusive)


def discard(tag, level):
    return set_member(tag, level, False)


def remove(tag):
    """从两个热门列表都移出"""
    return _apply(tag, {lv: False for lv in LEVELS})


def toggle(tag, level, exclusive=True):
    """只翻转该列表中的成员身份（以磁盘最新内容为准）"""
    return _apply(tag, {level: "toggle"}, exclusive)


def set_levels(tag, levels, exclusive=True):
    """精确设置：Tag 恰好属于 levels 中的列表，其余列表移出。levels 可为空"""
    want = _as_level_set(levels) or set()
    bad = want - set(LEVELS)
    if bad:
        raise ValueError(f"未知热门等级: {bad}")
    return _apply(tag, {lv: (lv in want) for lv in LEVELS}, exclusive)


def set_level(tag, level, exclusive=True):
    """【兼容旧接口】level=None → 从两个列表都移出；否则只把 Tag 加入该列表（不动另一列表）。
    返回主等级"""
    if level is not None and level not in LEVELS:
        raise ValueError(f"未知热门等级: {level}")
    if level is None:
        _apply(tag, {lv: False for lv in LEVELS}, exclusive)
    else:
        _apply(tag, {level: True}, exclusive)
    return level_of(tag)


def strip_overlap(side="hot"):
    """一次性迁移工具：把同时在两边的 Tag 从 side 列表删除（side ∈ {'hot','t'}），写前自动备份。
    返回被删除的条目列表"""
    if side not in ("hot", "t"):
        raise ValueError("side 只能是 'hot' 或 't'")
    with _lock, _file_lock():
        if not os.path.exists(HOT_PATH):
            return []
        raw = _load_raw_for_write()
        hot, t = _as_list(raw.get(KEY_HOT)), _as_list(raw.get(KEY_T))
        hk = {norm_tag(x) for x in hot if x is not None}
        tk = {norm_tag(x) for x in t if x is not None}
        src, other_keys, key = (hot, tk, KEY_HOT) if side == "hot" else (t, hk, KEY_T)
        removed = [x for x in src if x is not None and norm_tag(x) in other_keys]
        if not removed:
            return []
        bak = f"{HOT_PATH}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
        shutil.copy2(HOT_PATH, bak)
        raw[key] = [x for x in src if x is None or norm_tag(x) not in other_keys]
        _write_raw(raw)
        print(f"[热门] 已备份到 {bak}")
    load(force=True)
    return removed


def ensure_file():
    if os.path.exists(HOT_PATH):
        return
    with _lock, _file_lock():
        if not os.path.exists(HOT_PATH):
            _write_raw(_default_raw())


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


# ----------------------------------------------------------------------
# 命令行
# ----------------------------------------------------------------------
def _main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="热门 Tag 工具（HOT_TAGS 与 HOT_TAGS_T 相互独立）")
    p.add_argument("--overlap", action="store_true", help="列出同时在两个列表中的 Tag")
    p.add_argument("--strip-overlap-from", choices=["hot", "t"],
                   help="把重叠项从指定列表删除（hot=HOT_TAGS，t=HOT_TAGS_T），会先备份")
    a = p.parse_args(argv)

    c = counts()
    ov = overlap()
    print(f"文件：{HOT_PATH}")
    if last_error():
        print(f"⚠ 解析失败：{last_error()}")
    print(f"{LEVEL_T} {c[LEVEL_T]} 个 ｜ {LEVEL_HOT} {c[LEVEL_HOT]} 个 ｜ 两者皆有 {len(ov)} 个")
    if a.overlap:
        for t in ov:
            print("  ·", t)
    if a.strip_overlap_from:
        removed = strip_overlap(a.strip_overlap_from)
        key = KEY_HOT if a.strip_overlap_from == "hot" else KEY_T
        print(f"已从 {key} 删除 {len(removed)} 个重叠项")
        for t in removed:
            print("  -", t)


if __name__ == "__main__":
    _main()