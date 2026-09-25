"""
tag_blacklist.py —— Tag 黑名单共享读写层（纯 Python，不依赖 Qt；PyQt5 / PyQt6 程序都能直接用）

数据文件：~/Coding/Financial_System/Modules/Tag_Blacklist.json
{
  "_说明": "...",
  "确定": ["枪支", ...],
  "疑似": ["xxx", ...]
}

* 匹配规则：整词精确匹配（忽略首尾空格 / 大小写 / 全半角），不做子串匹配
* 同一 Tag 只属于一个分组；手动编辑时若两组都写了，以「确定」为准
* 写入：跨进程文件锁 + 临时文件 + os.replace 原子替换
* 文件被手动改坏：读取时沿用上次正确内容；写入时拒绝覆盖（避免冲掉手工修改）
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

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
MODULES_DIR = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules")
BLACKLIST_PATH = os.path.join(MODULES_DIR, "Tag_Blacklist.json")
_LOCK_PATH = os.path.join(MODULES_DIR, ".Tag_Blacklist.lock")

GROUP_SURE = "确定"
GROUP_MAYBE = "疑似"
GROUPS = (GROUP_SURE, GROUP_MAYBE)
DEFAULT_ACTIVE = frozenset({GROUP_SURE})
GROUP_COLORS = {GROUP_SURE: "#BF616A", GROUP_MAYBE: "#D08770"}

_NOTE_KEY = "_说明"
_NOTE = ("手动编辑说明：只认「确定」「疑似」两个键，值为 Tag 字符串数组；"
         "整词精确匹配（忽略首尾空格/大小写/全半角）；同一 Tag 两组都写时以「确定」为准；"
         "保存后 Check_Group / Chart / Editor_Tags 约 1 秒内自动生效。")

_lock = threading.RLock()
_state = {"sig": None, "data": {g: [] for g in GROUPS}, "map": {}, "error": None}


def norm_tag(tag):
    return unicodedata.normalize("NFKC", str(tag)).strip().casefold()


def signature(path=BLACKLIST_PATH):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def _empty():
    return {g: [] for g in GROUPS}


def _parse(raw):
    if not isinstance(raw, dict):
        raise ValueError("顶层必须是 JSON 对象 {...}")
    data, m = _empty(), {}
    for g in GROUPS:
        lst = raw.get(g, [])
        if lst is None:
            lst = []
        if isinstance(lst, str):
            lst = [lst]
        if not isinstance(lst, (list, tuple)):
            raise ValueError(f"「{g}」必须是数组")
        for t in lst:
            if t is None:
                continue
            s = str(t).strip()
            if not s:
                continue
            k = norm_tag(s)
            if k in m:
                continue
            m[k] = g
            data[g].append(s)
    return data, m


def _read_raw(path=BLACKLIST_PATH):
    with open(path, "r", encoding="utf-8-sig") as f:
        txt = f.read()
    if not txt.strip():
        return {}
    return json.loads(txt, object_pairs_hook=OrderedDict)


def load(force=False):
    """返回 {'确定': [...], '疑似': [...]} 的副本；按文件签名缓存"""
    with _lock:
        sig = signature()
        if force or sig != _state["sig"]:
            if not os.path.exists(BLACKLIST_PATH):
                _state.update(data=_empty(), map={}, error=None)
            else:
                try:
                    data, m = _parse(_read_raw())
                    _state.update(data=data, map=m, error=None)
                except Exception as e:
                    _state["error"] = f"{type(e).__name__}: {e}"
                    print(f"[黑名单] 解析 {BLACKLIST_PATH} 失败，沿用上次内容: {e}")
            _state["sig"] = sig
        return {g: list(v) for g, v in _state["data"].items()}


def last_error():
    load()
    return _state["error"]


def tag_map():
    load()
    return dict(_state["map"])


def group_of(tag):
    load()
    return _state["map"].get(norm_tag(tag))


def counts():
    d = load()
    return {g: len(d[g]) for g in GROUPS}


def blacklisted_tags(tags, groups=None):
    """返回 [(原tag, 分组), ...]；groups=None 表示所有分组"""
    if not tags:
        return []
    if isinstance(tags, str):
        tags = [tags]
    load()
    m = _state["map"]
    out, seen = [], set()
    for t in tags:
        k = norm_tag(t)
        g = m.get(k)
        if g and (groups is None or g in groups) and k not in seen:
            seen.add(k)
            out.append((str(t), g))
    return out


def is_blacklisted(tags, groups=None):
    return bool(blacklisted_tags(tags, groups))


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


def _compose(raw, data):
    out = OrderedDict()
    out[_NOTE_KEY] = (raw or {}).get(_NOTE_KEY, _NOTE)
    for g in GROUPS:
        out[g] = data[g]
    for k, v in (raw or {}).items():
        if k not in out:
            out[k] = v          # 保留你手动加的其他键
    return out


def _write_raw(obj):
    os.makedirs(MODULES_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=MODULES_DIR, prefix=".Tag_Blacklist.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, BLACKLIST_PATH)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def set_group(tag, group):
    """把 tag 放进 group（'确定'/'疑似'）；group=None 表示移出黑名单。返回新分组"""
    s = str(tag).strip()
    if not s:
        raise ValueError("Tag 为空")
    if group is not None and group not in GROUPS:
        raise ValueError(f"未知分组: {group}")
    with _lock, _file_lock():
        if os.path.exists(BLACKLIST_PATH):
            try:
                raw = _read_raw()
                data, _ = _parse(raw)
            except Exception as e:
                raise RuntimeError(
                    f"黑名单文件格式有误，为避免覆盖你的手动修改，本次未写入。\n"
                    f"请先修复：{BLACKLIST_PATH}\n{e}")
        else:
            raw, data = {}, _empty()
        k = norm_tag(s)
        for g in GROUPS:
            data[g] = [t for t in data[g] if norm_tag(t) != k]
        if group:
            data[group].append(s)
        _write_raw(_compose(raw, data))
    load(force=True)
    return group


def add(tag, group=GROUP_SURE):
    return set_group(tag, group)


def remove(tag):
    return set_group(tag, None)


def toggle(tag, group):
    return set_group(tag, None if group_of(tag) == group else group)


def ensure_file():
    if os.path.exists(BLACKLIST_PATH):
        return
    with _lock, _file_lock():
        if not os.path.exists(BLACKLIST_PATH):
            _write_raw(_compose({}, _empty()))


def open_in_editor():
    ensure_file()
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", BLACKLIST_PATH])
        elif sys.platform == "win32":
            os.startfile(BLACKLIST_PATH)   # noqa
        else:
            subprocess.Popen(["xdg-open", BLACKLIST_PATH])
    except Exception as e:
        print(f"[黑名单] 打开文件失败: {e}")