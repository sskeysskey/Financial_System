import sys
import json
import os
import sqlite3
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
    """从 Finance.db 的 Earning 表读取指定 symbol 的所有财报日期"""
    dates = set()
    if not os.path.exists(DB_PATH):
        return dates
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT date FROM Earning WHERE name = ?", (symbol.upper(),))
        for row in cursor.fetchall():
            if row[0]:
                dates.add(str(row[0]))
        conn.close()
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
    if cat_lower in ("pe_valid", "pe_invalid", "pe_deep", "pe_deeper"):
        return "PE_depth_any"
    return category

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
        for date_str, symbol_list in date_dict.items():
            all_trading_dates.add(date_str)
            if isinstance(symbol_list, list):
                for item in symbol_list:
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
                is_chaodi = (suf and '抄底' in suf)
            else:
                for d, s in category_data.get("PE_Volume_high", []):
                    if d == d_str and s and '抄底' in s:
                        is_chaodi = True
                        break
            if is_chaodi and category in ["PE_Volume_high", "Short", "Short_W"]:
                overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='最新交易日触发 PE_Volume_high(抄底) 和 Short/Short_W'>[★最新日:抄底+Short]</span>"

    # PE_Volume_high 且后缀包含 '甲' 时，往前推15天检查是否重复
    if category == "PE_Volume_high" and suf and '甲' in suf:
        try:
            date_idx = sorted_trading_dates.index(d_str)
            prev_15_dates = sorted_trading_dates[date_idx + 1 : date_idx + 16]
            
            pe_vol_high_records = category_data.get("PE_Volume_high", [])
            has_previous_jia = False
            for prev_d in prev_15_dates:
                for record_d, record_suf in pe_vol_high_records:
                    if record_d == prev_d and record_suf and '甲' in record_suf:
                        has_previous_jia = True
                        break
                if has_previous_jia:
                    break
            
            if has_previous_jia:
                overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='15个交易日内重复触发 PE_Volume_high(甲)'>[ x 2]</span>"
        except ValueError:
            pass

    # Short 往前推一周（5个交易日）检查是否出现过 PE_Volume_high 且后缀含 '甲'
    if category == "Short":
        try:
            date_idx = sorted_trading_dates.index(d_str)
            prev_5_dates = sorted_trading_dates[date_idx + 1 : date_idx + 6]
            
            pe_vol_high_records = category_data.get("PE_Volume_high", [])
            has_jia_in_week = False
            found_jia_date = ""
            for prev_d in prev_5_dates:
                for record_d, record_suf in pe_vol_high_records:
                    if record_d == prev_d and record_suf and '甲' in record_suf:
                        has_jia_in_week = True
                        found_jia_date = prev_d
                        break
                if has_jia_in_week:
                    break
            
            if has_jia_in_week:
                overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='一周内（5个交易日）曾触发 PE_Volume_high(甲): {found_jia_date}'>[ + ★Volume_High'甲']</span>"
        except ValueError:
            pass

    # SupportLevel_Close 或 SupportLevel_Over 往前推15天检查 PE_Volume
    if category in ["SupportLevel_Close", "SupportLevel_Over"]:
        try:
            date_idx = sorted_trading_dates.index(d_str)
            prev_15_dates = sorted_trading_dates[date_idx + 1 : date_idx + 16]
            
            pe_volume_dates = category_dates.get("PE_Volume", set())
            found_dates = [prev_d for prev_d in prev_15_dates if prev_d in pe_volume_dates]
            
            if found_dates:
                dates_str = ", ".join(found_dates)
                overlap_marker += f"<br>&nbsp;&nbsp;<span style='color:{purple}; font-weight:bold;' title='15个交易日内曾触发 PE_Volume'>★PE_Volume: {dates_str}</span>"
        except ValueError:
            pass

    # 跨日接力 及 PE_W 15天重复检测
    try:
        date_idx = sorted_trading_dates.index(d_str)
        if category == "PE_W":
            prev_15_dates = sorted_trading_dates[date_idx + 1 : date_idx + 16]
            pe_w_count = 0
            for prev_d in prev_15_dates:
                if prev_d in category_dates.get("PE_W", set()):
                    pe_w_count += 1
            
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

    # 计算每个命中日期的归一化特征集合（set 结构方便包含运算）
    date_signature = {}
    for d_str in hit_dates_sorted:
        mapped_items = set()
        for cat, suf in date_items[d_str]:
            norm_cat = normalize_category_for_signature(cat)
            mapped_items.add(norm_cat)
        date_signature[d_str] = mapped_items

    # 连续相同/超集项的最低数量阈值
    MIN_STREAK_ITEMS = 2

    def get_streak_position(d_str):
        """
        返回该日期在“核心特征保持/只增不减”连续段里的位置（最早那天=1）。
        规则：
        1. 当天特征数需达到 MIN_STREAK_ITEMS。
        2. 沿时序往前（更早交易日）回溯时，较新的一天必须是更早一天的超集（只能增不能减）。
        3. 更早的一天也必须满足 MIN_STREAK_ITEMS 门槛，且中间不可断档。
        """
        if d_str not in sorted_trading_dates:
            return 1

        curr_sig = date_signature.get(d_str)
        if not curr_sig or len(curr_sig) < MIN_STREAK_ITEMS:
            return 1

        idx = sorted_trading_dates.index(d_str)
        count = 1
        chain_sig = curr_sig  # 状态锚点

        j = idx + 1  # 降序列表中，索引递增 = 更早的交易日
        while j < len(sorted_trading_dates):
            older_date = sorted_trading_dates[j]
            older_sig = date_signature.get(older_date)

            # 中间交易日没有记录或特征少于阈值，则连续终止
            if not older_sig or len(older_sig) < MIN_STREAK_ITEMS:
                break

            # 只能增不能减：当前较新交易日 chain_sig 必须包含更早交易日 older_sig 的所有元素
            if chain_sig >= older_sig:
                count += 1
                chain_sig = older_sig  # 状态收敛为更早日期的集合，继续向前验证
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
                f"border-radius:3px;' title='核心指标连续保持（支持只增不减）'>"
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
                elif category in ["OverSell_W"]:
                    target_color = COLOR_MEDIUM
                else:
                    target_color = COLOR_MEDIUM
            else:
                target_color = COLOR_BLUE

            extra_style = ""
            if category == "Short" and "[★Short+前周甲]" in overlap_marker:
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
                "padding:0 4px; border-radius:3px;'>52week_low</b>"
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
        
        self.setGeometry(0, 0, left_width, height)
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
        screen_geometry = screen.geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

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
    target_symbol = sys.argv[1] if len(sys.argv) > 1 else "UNKNOWN"

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