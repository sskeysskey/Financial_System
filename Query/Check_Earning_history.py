import sys
import json
import os
import sqlite3
from contextlib import closing
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QTextEdit, QSplitter, QLabel, QWidget
)
from PyQt6.QtGui import QFont, QShortcut, QKeySequence
from PyQt6.QtCore import Qt
from collections import defaultdict

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")
SECTOR_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")

WEEK52_LOW_SECTORS = {
    "Basic_Materials", "Real_Estate", "Energy", "Technology",
    "Consumer_Cyclical", "Utilities", "Consumer_Defensive",
    "Industrials", "Communication_Services", "Financial_Services",
    "Healthcare"
}

# =========================================================
# 规则参数（集中管理，便于调整）
# =========================================================
# SupportLevel 回看 PE_Volume 的交易日窗口
SUPPORT_PE_VOLUME_LOOKBACK = 15
# SupportLevel 回看 Short 的交易日窗口
SUPPORT_SHORT_LOOKBACK = 7
# SupportLevel 回看时视为 "Short 信号" 的分类（与代码其他处 Short/Short_W 同组处理保持一致）
SUPPORT_SHORT_CATEGORIES = ("Short", "Short_W")

# 连续性判定时忽略的"事件型/瞬时型"信号（不参与特征比较，也不计入最低项数）
STREAK_IGNORED_CATEGORIES = {"Short", "Short_W"}

# Short 前一周出现 PE_Volume_high(甲) 时的标记文本（渲染与判定共用，避免文本不一致）
SHORT_PREV_JIA_TAG = "[ + ★Volume_High'甲']"


def load_52week_low_symbols():
    """从 Sectors_panel.json 读取指定板块下的 symbol，作为 52week_low 集合"""
    symbols = set()
    if not os.path.exists(SECTOR_PATH):
        return symbols
    try:
        with open(SECTOR_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"读取 Sectors_panel.json 出错: {e}")
        return symbols
    for sector in WEEK52_LOW_SECTORS:
        for sym in data.get(sector, {}).keys():
            symbols.add(sym.upper())
    return symbols

def load_earning_report_dates(symbol):
    """从 Finance.db 的 Earning 表读取指定 symbol 的所有财报日期（统一为 YYYY-MM-DD）"""
    dates = set()
    if not os.path.exists(DB_PATH):
        return dates
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date FROM Earning WHERE name = ?", (symbol.upper(),))
            for row in cursor.fetchall():
                if row[0]:
                    # 兼容 'YYYY-MM-DD HH:MM:SS' 等带时间格式
                    dates.add(str(row[0]).strip()[:10])
    except Exception as e:
        print(f"读取 Finance.db 出错: {e}")
    return dates

NORD_THEME = {
    'background': '#2E3440',
    'widget_bg': '#3B4252',
    'border': '#4C566A',
    'text_light': '#D8DEE9',
    'text_bright': '#ECEFF4',
    'accent_blue': '#5E81AC',
    'success_green': '#A3BE8C',
    'warning_red': '#BF616A',
    'accent_purple': '#B48EAD'  # 紫色
}

# =========================================================
# 公共辅助函数 & 数据加载
# =========================================================
def make_header(text, color):
    return f"""
    <div style='margin-top: 4px; margin-bottom: 2px;'>
        <span style='color: {color}; font-weight: bold; font-size: 18px;'>
            {text}
        </span>
    </div>
    """

def get_suffix_if_match(item_str, target_symbol):
    if item_str == target_symbol:
        return ""
    if item_str.startswith(target_symbol):
        suffix = item_str[len(target_symbol):]
        if not any(c.isascii() and c.isalpha() for c in suffix):
            return suffix
    return None

def normalize_category_for_signature(category: str) -> str:
    """
    对连续性判定的分类进行归一化。
    同类指标但细分深度不同的归并为同一组，以便跨交易日连贯统计状态延续。
    """
    cat_lower = category.lower()
    # 支撑位闭合/越过统一为一类
    if cat_lower in ("supportlevel_close", "supportlevel_over"):
        return "SupportLevel_Any"
    # PE low / lower / lowest 统一归一化为 PE_low_any
    if cat_lower in ("pe_low", "pe_lower", "pe_lowest"):
        return "PE_low_any"
    # PE valid / deep / deeper 统一归一化为 PE_depth_any
    if cat_lower in ("pe_valid", "pe_invalid", "pe_deep", "pe_deeper", "oversell_w"):
        return "PE_depth_any"
    return category

def get_prev_dates(d_str, n, sorted_trading_dates):
    """返回 d_str 之前（更早）的 n 个交易日，不含当天；d_str 不存在时返回空列表"""
    try:
        idx = sorted_trading_dates.index(d_str)
    except ValueError:
        return []
    return sorted_trading_dates[idx + 1: idx + 1 + n]

def find_prev_hit_dates(d_str, categories, window, category_dates, sorted_trading_dates):
    """
    在 d_str 之前 window 个交易日内，查找触发了 categories 中任一分类的日期。
    返回 [(date, [命中的分类...]), ...]，按时间降序。
    """
    results = []
    for prev_d in get_prev_dates(d_str, window, sorted_trading_dates):
        hit_cats = [c for c in categories if prev_d in category_dates.get(c, set())]
        if hit_cats:
            results.append((prev_d, hit_cats))
    return results

def load_earning_index(symbol):
    """
    读取 Earning JSON,构建各类索引。
    """
    if not os.path.exists(JSON_PATH):
        return None, None, None, None, None, f"错误：找不到 Earning 文件<br>{JSON_PATH}"

    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return None, None, None, None, None, f"读取 Earning JSON 出错: {e}"

    category_data = defaultdict(list)
    date_categories = defaultdict(set)
    category_dates = defaultdict(set)
    date_items = defaultdict(list)
    all_trading_dates = set()

    for category, date_dict in data.items():
        if category == "_Tag_Blacklist":
            continue
        if not isinstance(date_dict, dict):
            continue
        for date_str, symbol_list in date_dict.items():
            all_trading_dates.add(date_str)
            if isinstance(symbol_list, list):
                for item in symbol_list:
                    if not isinstance(item, str):
                        continue
                    suffix = get_suffix_if_match(item, symbol)
                    if suffix is not None:
                        category_data[category].append((date_str, suffix))
                        date_categories[date_str].add(category)
                        category_dates[category].add(date_str)
                        date_items[date_str].append((category, suffix))
                        break

    sorted_trading_dates = sorted(list(all_trading_dates), reverse=True)
    return category_data, date_categories, category_dates, date_items, sorted_trading_dates, None

def build_earning_marker(d_str, items_today, earning_dates):
    """当天是财报日 且 触发了 PE_Volume_high(甲) 时，返回醒目标识"""
    if d_str not in earning_dates:
        return ""
    has_jia = any(
        cat == "PE_Volume_high" and suf and '甲' in suf
        for cat, suf in items_today
    )
    if has_jia:
        return (
            " <span style='color:#ECEFF4; background-color:#BF616A; "
            "font-weight:bold; padding:1px 7px; border-radius:4px; "
            "font-size:15px;' title='财报日 + PE_Volume_high(甲)'>📊 财报</span>"
        )
    return ""

def build_suffix_html(category, suf):
    if not suf:
        return ""
    if category == "PE_Volume" and '追' in suf:
        processed_suf = suf.replace('追', "<span style='color:red;'>追</span>")
        return f" <span style='color:#EBCB8B; font-size:14px; font-weight:bold;'>[{processed_suf}]</span>"
    return f" <span style='color:#EBCB8B; font-size:14px; font-weight:bold;'>[{suf}]</span>"

def build_overlap_marker(category, d_str, suf,
                        category_data, date_categories,
                        category_dates, sorted_trading_dates):
    """标记检测逻辑封装"""
    overlap_marker = ""
    red = NORD_THEME['warning_red']
    purple = NORD_THEME['accent_purple']

    # 1. 最新一天 PE_Volume_high(抄底) & Short/Short_W
    if sorted_trading_dates and d_str == sorted_trading_dates[0]:
        has_short = "Short" in date_categories[d_str] or "Short_W" in date_categories[d_str]
        has_pe_vol_high = "PE_Volume_high" in date_categories[d_str]
        if has_short and has_pe_vol_high:
            is_chaodi = False
            if category == "PE_Volume_high":
                is_chaodi = bool(suf and '抄底' in suf)
            else:
                for d, s in category_data.get("PE_Volume_high", []):
                    if d == d_str and s and '抄底' in s:
                        is_chaodi = True
                        break
            if is_chaodi and category in ["PE_Volume_high", "Short", "Short_W"]:
                overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='最新交易日触发 PE_Volume_high(抄底) 和 Short/Short_W'>[★最新日:抄底+Short]</span>"

    # PE_Volume_high 且后缀包含 '甲' 时，往前推15天检查是否重复
    if category == "PE_Volume_high" and suf and '甲' in suf:
        prev_15_dates = set(get_prev_dates(d_str, 15, sorted_trading_dates))
        has_previous_jia = any(
            record_d in prev_15_dates and record_suf and '甲' in record_suf
            for record_d, record_suf in category_data.get("PE_Volume_high", [])
        )
        if has_previous_jia:
            overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='15个交易日内重复触发 PE_Volume_high(甲)'>[ x 2]</span>"

    # Short 往前推一周（5个交易日）检查是否出现过 PE_Volume_high 且后缀含 '甲'
    if category == "Short":
        prev_5_dates = get_prev_dates(d_str, 5, sorted_trading_dates)
        jia_dates = {
            record_d for record_d, record_suf in category_data.get("PE_Volume_high", [])
            if record_suf and '甲' in record_suf
        }
        found_jia_date = next((d for d in prev_5_dates if d in jia_dates), "")
        if found_jia_date:
            overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='一周内（5个交易日）曾触发 PE_Volume_high(甲): {found_jia_date}'>{SHORT_PREV_JIA_TAG}</span>"

    # SupportLevel_Close / SupportLevel_Over：
    #   往前推 15 个交易日检查 PE_Volume；往前推 7 个交易日检查 Short（含 Short_W）
    if category in ("SupportLevel_Close", "SupportLevel_Over"):
        pe_vol_hits = find_prev_hit_dates(
            d_str, ("PE_Volume",), SUPPORT_PE_VOLUME_LOOKBACK,
            category_dates, sorted_trading_dates
        )
        if pe_vol_hits:
            dates_str = ", ".join(d for d, _ in pe_vol_hits)
            overlap_marker += (
                f"<br>&nbsp;&nbsp;<span style='color:{purple}; font-weight:bold;' "
                f"title='{SUPPORT_PE_VOLUME_LOOKBACK}个交易日内曾触发 PE_Volume'>"
                f"★PE_Volume: {dates_str}</span>"
            )

        short_hits = find_prev_hit_dates(
            d_str, SUPPORT_SHORT_CATEGORIES, SUPPORT_SHORT_LOOKBACK,
            category_dates, sorted_trading_dates
        )
        if short_hits:
            labels = []
            for d, cats in short_hits:
                cat_set = set(cats)
                if cat_set == {"Short_W"}:
                    labels.append(f"{d}(W)")
                elif "Short_W" in cat_set:
                    labels.append(f"{d}(+W)")
                else:
                    labels.append(d)
            dates_str = ", ".join(labels)
            overlap_marker += (
                f"<br>&nbsp;&nbsp;<span style='color:{purple}; font-weight:bold;' "
                f"title='{SUPPORT_SHORT_LOOKBACK}个交易日内曾触发 Short/Short_W（W=Short_W）'>"
                f"★Short: {dates_str}</span>"
            )

    # 跨日接力 及 PE_W 15天重复检测
    try:
        date_idx = sorted_trading_dates.index(d_str)
        if category == "PE_W":
            prev_15_dates = sorted_trading_dates[date_idx + 1 : date_idx + 16]
            pe_w_dates = category_dates.get("PE_W", set())
            pe_w_count = sum(1 for prev_d in prev_15_dates if prev_d in pe_w_dates)

            if pe_w_count > 0:
                total_count = pe_w_count + 1
                overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='15个交易日内重复触发 PE_W'>[ x {total_count}]</span>"

            if date_idx + 1 < len(sorted_trading_dates):
                prev_date = sorted_trading_dates[date_idx + 1]
                prev_in_hot = prev_date in category_dates.get("PE_Hot", set())
                prev_in_vol = prev_date in category_dates.get("PE_Volume", set())
                prev_in_short = prev_date in category_dates.get("Short", set())
                prev_in_short_w = prev_date in category_dates.get("Short_W", set())

                if prev_in_hot and prev_in_vol:
                    overlap_marker += f" <span style='color:{purple}; font-weight:bold;' title='前一交易日触发 PE_Hot 和 PE_Volume'>[★Hot+Volume->W]</span>"
                elif prev_in_hot:
                    overlap_marker += f" <span style='color:{purple}; font-weight:bold;' title='前一交易日触发 PE_Hot'>[★接力:Hot->W]</span>"
                elif prev_in_vol:
                    overlap_marker += f" <span style='color:{purple}; font-weight:bold;' title='前一交易日触发 PE_Volume'>[★Volume->W]</span>"
                
                if prev_in_short or prev_in_short_w:
                    overlap_marker += f" <span style='color:{purple}; font-weight:bold;' title='前一交易日触发 Short 或 Short_W'>[★Short->W]</span>"

        elif category == "PE_Hot":
            if date_idx - 1 >= 0:
                next_date = sorted_trading_dates[date_idx - 1]
                if next_date in category_dates.get("PE_W", set()):
                    overlap_marker += f" <span style='color:{purple}; font-weight:bold;' title='下一交易日触发 PE_W'>[★Hot->W]</span>"
        
        elif category == "PE_Volume":
            if date_idx - 1 >= 0:
                next_date = sorted_trading_dates[date_idx - 1]
                if next_date in category_dates.get("PE_W", set()):
                    overlap_marker += f" <span style='color:{purple}; font-weight:bold;' title='下一交易日触发 PE_W'>[★Volume->W]</span>"
    except ValueError:
        pass
    return overlap_marker

# =========================================================
# 视图 1：按分组 (Category) 渲染
# =========================================================
def search_history_by_category(symbol):
    html_parts = []
    has_data = False 

    category_data, date_categories, category_dates, date_items, sorted_trading_dates, err = load_earning_index(symbol)
    if err:
        return f"<p style='color:red'>{err}</p>"

    for category, found_dates in category_data.items():
        if not found_dates:
            continue
        has_data = True
        found_dates_sorted = sorted(found_dates, key=lambda x: x[0], reverse=True)
        html_parts.append(make_header(category, NORD_THEME['success_green']))
        for d_str, suf in found_dates_sorted:
            suf_html = build_suffix_html(category, suf)
            overlap_marker = build_overlap_marker(
                category, d_str, suf,
                category_data, date_categories, category_dates, sorted_trading_dates
            )
            html_parts.append(f"&nbsp;&nbsp;• {d_str}{suf_html}{overlap_marker}<br>")

    if not has_data:
        return f"<div style='text-align:center; margin-top:20px; color:{NORD_THEME['text_light']}'>在所有文件中<br>未找到 <b>{symbol}</b> 的任何记录。</div>"
    return "".join(html_parts)

# =========================================================
# 视图 2：按时间 (Date) 渲染
# =========================================================
def search_history_by_date(symbol):
    COLOR_HIGH = "#BF616A"      # 红色
    COLOR_MEDIUM = "#D08770"    # 橙色
    COLOR_BLUE = "#88C0D0"      # 蓝色

    high_weight_categories = {
        "PE_Volume", "Short", "Short_W", "PE_W", "PE_Hot", "season", "SupportLevel_Over"
    }
    medium_weight_categories = {
        "PE_Volume_up", "PE_Volume_high",
        "SupportLevel_Close", "OverSell_W"
    }

    highlight_categories = high_weight_categories.union(medium_weight_categories)
    compress_categories = {"PE_valid"}

    html_parts = []
    has_data = False

    category_data, date_categories, category_dates, date_items, sorted_trading_dates, err = load_earning_index(symbol)
    if err:
        return f"<p style='color:red'>{err}</p>"

    week52_low_symbols = load_52week_low_symbols()
    is_52week_low = symbol.upper() in week52_low_symbols
    earning_dates = load_earning_report_dates(symbol)

    hit_dates_sorted = sorted(date_items.keys(), reverse=True)
    latest_hit_date = hit_dates_sorted[0] if hit_dates_sorted else None

    normal_dates = []
    compressed_records = defaultdict(list)

    # 计算每个命中日期的归一化"核心特征"集合
    # 事件型信号（Short / Short_W）不参与连续性比较，也不计入最低项数
    date_signature = {}
    for d_str in hit_dates_sorted:
        mapped_items = set()
        for cat, suf in date_items[d_str]:
            if cat in STREAK_IGNORED_CATEGORIES:
                continue
            mapped_items.add(normalize_category_for_signature(cat))
        date_signature[d_str] = mapped_items

    # 连续相同/超集项的最低数量阈值（按核心特征计）
    MIN_STREAK_ITEMS = 2
    # 允许的最大连续空窗交易日数量（在此范围内且标的完全无信号时允许桥接）
    MAX_EMPTY_GAP_DAYS = 5

    def get_streak_position(d_str):
        """
        返回该日期在“核心特征保持/只增不减”连续段里的位置（最早那天=1）。
        规则：
        1. 核心特征 = 当天全部分类经归一化后，剔除 STREAK_IGNORED_CATEGORIES（Short/Short_W）。
        2. 当天核心特征数需达到 MIN_STREAK_ITEMS。
        3. 沿时序往前（更早交易日）回溯：
           - 若前序交易日该标的完全无记录（空窗日），在不超过 MAX_EMPTY_GAP_DAYS 容纳内允许跳过空窗桥接。
           - 若遇到有记录交易日，要求较新交易日核心特征集必须包含较早交易日（chain_sig >= older_sig，只增不减）。
           - 若中间出现破坏性记录（有指标但核心特征不合规，包括仅有 Short 的日子）或空窗超限，则连续性终止。
        """
        if d_str not in sorted_trading_dates:
            return 1

        curr_sig = date_signature.get(d_str)
        if not curr_sig or len(curr_sig) < MIN_STREAK_ITEMS:
            return 1

        idx = sorted_trading_dates.index(d_str)
        count = 1
        chain_sig = curr_sig  # 状态锚点
        empty_gap = 0         # 连续无信号空窗计数器

        j = idx + 1  # 降序列表中，索引递增 = 更早的交易日
        while j < len(sorted_trading_dates):
            older_date = sorted_trading_dates[j]
            # 判定中间交易日该股票是否完全无任何记录
            is_empty_day = (older_date not in date_items)

            if is_empty_day:
                empty_gap += 1
                if empty_gap > MAX_EMPTY_GAP_DAYS:
                    break
                j += 1
                continue

            older_sig = date_signature.get(older_date)
            if not older_sig or len(older_sig) < MIN_STREAK_ITEMS:
                break

            if chain_sig >= older_sig:
                count += 1
                chain_sig = older_sig
                empty_gap = 0
                j += 1
            else:
                break

        return count

    # 第一次遍历：筛选出需要压缩的日期
    for d_str in hit_dates_sorted:
        items_today = sorted(date_items[d_str], key=lambda x: x[0])
        if len(items_today) == 1 and items_today[0][0] in compress_categories:
            category, suf = items_today[0]
            compressed_records[category].append((d_str, suf))
        else:
            normal_dates.append((d_str, items_today))

    group_a = {"PE_Volume", "PE_Volume_up", "PE_Volume_high", "PE_W",
                "PE_Hot", "Short", "Short_W", "SupportLevel_Close", "SupportLevel_Over",
                "PE_Deep", "PE_Deeper"}

    # 渲染正常日期的记录
    for d_str, items_today in normal_dates:
        has_data = True
        has_group_a = any(cat in group_a for cat, _ in items_today)

        # 连续记录标识
        streak_pos = get_streak_position(d_str)
        if streak_pos >= 2:
            streak_marker = (
                f" <span style='color:#C4A7E7; font-weight:bold; "
                f"background-color:rgba(235,203,139,0.15); padding:0 4px; "
                f"border-radius:3px;' title='核心指标连续保持（忽略Short/Short_W，支持只增不减及短期平稳空窗容差）'>"
                f"[⟳连续第{streak_pos}天]</span>"
            )
        else:
            streak_marker = ""

        # 财报日标识
        earning_marker = build_earning_marker(d_str, items_today, earning_dates)

        rendered_items = []
        for category, suf in items_today:
            suf_html = build_suffix_html(category, suf)
            overlap_marker = build_overlap_marker(
                category, d_str, suf,
                category_data, date_categories, category_dates, sorted_trading_dates
            )

            if category == "PE_Deeper":
                target_color = COLOR_HIGH
            elif category == "PE_Deep":
                target_color = COLOR_MEDIUM
            elif category in highlight_categories:
                if category == "PE_Volume_up":
                    target_color = COLOR_MEDIUM
                elif category in high_weight_categories:
                    target_color = COLOR_HIGH
                elif category == "PE_Volume_high" and suf and '甲' in suf:
                    target_color = COLOR_HIGH
                else:
                    target_color = COLOR_MEDIUM
            else:
                target_color = COLOR_BLUE

            extra_style = ""
            # 修复：原代码判断的标记文本与实际生成的文本不一致，导致高亮永不生效
            if category == "Short" and SHORT_PREV_JIA_TAG in overlap_marker:
                extra_style = "border: 1px solid #BF616A; background-color: rgba(191,97,106,0.25);"

            display_category = (
                f"<b style='color:{target_color}; background-color:rgba(191,97,106,0.1); "
                f"padding:0 4px; border-radius:3px; {extra_style}'>{category}</b>"
            )

            rendered_items.append(f"• {display_category}{suf_html}{overlap_marker}")

        # 在最新交易日追加 52week_low 标记（橘色）
        if is_52week_low and d_str == latest_hit_date:
            rendered_items.append(
                "• <b style='color:#D08770; background-color:rgba(208,135,112,0.15); "
                "padding:0 4px; border-radius:3px;'>X_week_low</b>"
            )

        if has_group_a:
            html_parts.append(make_header(d_str + streak_marker + earning_marker, NORD_THEME['success_green']))
            for item in rendered_items:
                html_parts.append(f"&nbsp;&nbsp;{item}<br>")
        else:
            date_html = (
                f"<span style='color:{NORD_THEME['success_green']}; "
                f"font-weight:bold; font-size:15px;'>{d_str}</span>"
            )
            joined = "&nbsp;&nbsp;&nbsp;&nbsp;".join(rendered_items)
            html_parts.append(
                f"<div style='padding-left: 4px; line-height: 1.8; "
                f"margin-top:2px; margin-bottom:2px;'>"
                f"{date_html}{streak_marker}{earning_marker}&nbsp;&nbsp;&nbsp;&nbsp;{joined}"
                f"</div>"
            )

    # 渲染被压缩的单一分组记录 (PE_valid)
    sort_order = {"PE_valid": 1}
    sorted_compressed_keys = sorted(compressed_records.keys(), key=lambda x: sort_order.get(x, 99))

    for category in sorted_compressed_keys:
        records = compressed_records[category]
        has_data = True
        html_parts.append(make_header(f"{category} (单一触发)", NORD_THEME['success_green']))

        date_strings = []
        for d_str, suf in records:
            suf_html = build_suffix_html(category, suf)
            overlap_marker = build_overlap_marker(
                category, d_str, suf,
                category_data, date_categories, category_dates, sorted_trading_dates
            )
            date_strings.append(f"<span style='color:{NORD_THEME['text_bright']}'>{d_str}</span>{suf_html}{overlap_marker}")

        joined_dates = ",&nbsp;&nbsp;".join(date_strings)
        html_parts.append(f"<div style='padding-left: 10px; line-height: 1.6;'>{joined_dates}</div><br>")

    if not has_data:
        return f"<div style='text-align:center; margin-top:20px; color:{NORD_THEME['text_light']}'>在所有文件中<br>未找到 <b>{symbol}</b> 的任何记录。</div>"
    return "".join(html_parts)

# =========================================================
# 对话框界面
# =========================================================
class InfoDialog(QDialog):
    def __init__(self, symbol, font_family, font_size, left_width, right_width, height, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Info Check: {symbol}")
        
        self.resize(left_width, height)
        self.center_on_screen()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # 左栏: 按时间
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        left_title = QLabel("按时间")
        left_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_title.setObjectName("panelTitle")

        self.text_by_date = QTextEdit()
        self.text_by_date.setReadOnly(True)
        self.text_by_date.setFont(QFont(font_family))
        self.text_by_date.setHtml(search_history_by_date(symbol))

        left_layout.addWidget(left_title)
        left_layout.addWidget(self.text_by_date)

        self.splitter.addWidget(left_container)
        self.splitter.setSizes([left_width])
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter)
        self.setLayout(layout)
        self.apply_nord_style(font_size)

        QShortcut(QKeySequence("1"), self, activated=lambda: self.text_by_date.setFocus())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()  # 排除 Dock / 菜单栏，并考虑多屏偏移
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(max(geo.x(), x), max(geo.y(), y))

    def apply_nord_style(self, font_size):
        qss = f"""
        QDialog {{ background-color: {NORD_THEME['background']}; }}
        QWidget {{ background-color: {NORD_THEME['background']}; }}

        QLabel#panelTitle {{
            color: {NORD_THEME['text_bright']};
            background-color: {NORD_THEME['widget_bg']};
            font-weight: bold;
            font-size: 14px;
            padding: 6px;
            border: 1px solid {NORD_THEME['border']};
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}

        QTextEdit {{
            background-color: {NORD_THEME['widget_bg']};
            color: {NORD_THEME['text_bright']};
            border: 1px solid {NORD_THEME['border']};
            border-top: none;
            border-bottom-left-radius: 4px;
            border-bottom-right-radius: 4px;
            font-size: {font_size}px;
            padding: 10px;
        }}

        QSplitter::handle {{
            background-color: {NORD_THEME['border']};
            width: 4px;
        }}
        QSplitter::handle:hover {{
            background-color: {NORD_THEME['accent_blue']};
        }}
        """
        self.setStyleSheet(qss)

# =========================================================
# 程序入口
# =========================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    target_symbol = sys.argv[1].strip().upper() if len(sys.argv) > 1 else "UNKNOWN"

    dialog = InfoDialog(
        symbol=target_symbol,
        font_family="Arial Unicode MS",
        font_size=16,
        left_width=700,
        right_width=500,
        height=850
    )
    dialog.raise_()
    dialog.activateWindow()

    import platform
    import subprocess
    if platform.system() == "Darwin":
        try:
            subprocess.run([
                'osascript', '-e',
                f'tell application "System Events" to set frontmost of the first process whose unix id is {os.getpid()} to true'
            ], check=False)
        except Exception as e:
            print(f"macOS 强制置前执行失败: {e}")

    dialog.exec()