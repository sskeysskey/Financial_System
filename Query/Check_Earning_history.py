import sys
import json
import os
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

NORD_THEME = {
    'background': '#2E3440',
    'widget_bg': '#3B4252',
    'border': '#4C566A',
    'text_light': '#D8DEE9',
    'text_bright': '#ECEFF4',
    'accent_blue': '#5E81AC',
    'success_green': '#A3BE8C',
    'warning_red': '#BF616A'
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


def build_sector_html(symbol):
    """检索 Sector Panel，返回 (html_str, has_data)"""
    html_parts = []
    has_data = False
    if not os.path.exists(SECTOR_PATH):
        return "", False
    try:
        with open(SECTOR_PATH, 'r', encoding='utf-8') as f:
            sector_data = json.load(f)
        found_sectors = []
        for category, content_dict in sector_data.items():
            for key, note in content_dict.items():
                suffix = get_suffix_if_match(key, symbol)
                if suffix is not None:
                    display_text = category
                    if suffix:
                        display_text += f" <span style='color:#EBCB8B'>[{suffix}]</span>"
                    if note:
                        display_text += f" <span style='color:#88C0D0'>({note})</span>"
                    found_sectors.append(display_text)
                    break
        if found_sectors:
            has_data = True
            html_parts.append(make_header("所属板块/分组", NORD_THEME['success_green']))
            for s in found_sectors:
                html_parts.append(f"&nbsp;&nbsp;★ {s}<br>")
    except Exception as e:
        html_parts.append(f"<p style='color:red'>读取 Sector JSON 出错: {e}</p>")
    return "".join(html_parts), has_data


def load_earning_index(symbol):
    """
    读取 Earning JSON,构建各类索引。
    返回:
        category_data: dict[category] -> [(date, suffix), ...]
        date_categories: dict[date] -> set(categories)
        category_dates: dict[category] -> set(dates)
        date_items: dict[date] -> [(category, suffix), ...]
        sorted_trading_dates: list[str] (降序)
        error: str or None
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
    """把原来那一大串标记检测逻辑封装进来,两种视图共用"""
    overlap_marker = ""
    red = NORD_THEME['warning_red']

    # 1. 同日 PE_Volume & Short / Short_W
    combinations = [
        {"tags": {"PE_Volume", "Short"}, "label": "PE_Volume & Short"},
        {"tags": {"PE_Volume", "Short_W"}, "label": "PE_Volume & Short_W"}
    ]
    for combo in combinations:
        if combo["tags"].issubset(date_categories[d_str]):
            if category in combo["tags"]:
                overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='同一天同时触发 {combo['label']}'>[★多重触发]</span>"
                break

    # 最新一天 PE_Volume_high(抄底) & Short/Short_W
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

    # PE_Volume_high(抄底) & PE_W
    if "PE_W" in date_categories[d_str] and "PE_Volume_high" in date_categories[d_str]:
        is_chaodi = False
        if category == "PE_Volume_high":
            is_chaodi = (suf and '抄底' in suf)
        else:
            for d, s in category_data.get("PE_Volume_high", []):
                if d == d_str and s and '抄底' in s:
                    is_chaodi = True
                    break
        if is_chaodi and category in ["PE_Volume_high", "PE_W"]:
            overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='同一天触发 PE_Volume_high(抄底) 和 PE_W'>[★多重触发:抄底+W]</span>"

    # A 组 & 支撑位
    group_a = {"PE_Volume", "PE_Volume_up", "PE_Volume_high", "PE_W",
               "PE_Deeper", "PE_Deep", "OverSell_W", "PE_Hot", "Short", "Short_W"}
    if category in group_a:
        if "SupportLevel_Close" in date_categories[d_str]:
            overlap_marker += f" <span style='color:{red}; font-weight:bold;'>[接近支撑位]</span>"
        if "SupportLevel_Over" in date_categories[d_str]:
            overlap_marker += f" <span style='color:{red}; font-weight:bold;'>[超过支撑位]</span>"

    # 2. 跨日接力
    try:
        date_idx = sorted_trading_dates.index(d_str)
        if category == "PE_W":
            if date_idx + 1 < len(sorted_trading_dates):
                prev_date = sorted_trading_dates[date_idx + 1]
                prev_in_hot = prev_date in category_dates.get("PE_Hot", set())
                prev_in_vol = prev_date in category_dates.get("PE_Volume", set())
                if prev_in_hot and prev_in_vol:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触发 PE_Hot 和 PE_Volume'>[★接力:hot+vol->w]</span>"
                elif prev_in_hot:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触发 PE_Hot'>[★接力:hot->w]</span>"
                elif prev_in_vol:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触发 PE_Volume'>[★接力:vol->w]</span>"
                prev_in_supp_close = prev_date in category_dates.get("SupportLevel_Close", set())
                prev_in_supp_over = prev_date in category_dates.get("SupportLevel_Over", set())
                if prev_in_supp_close or prev_in_supp_over:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触及或跌破支撑位'>[★支撑位->W]</span>"
        elif category == "PE_Hot":
            if date_idx - 1 >= 0:
                next_date = sorted_trading_dates[date_idx - 1]
                if next_date in category_dates.get("PE_W", set()):
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='下一交易日触发 PE_W'>[★接力:hot->w]</span>"
        elif category == "PE_Volume":
            if date_idx - 1 >= 0:
                next_date = sorted_trading_dates[date_idx - 1]
                if next_date in category_dates.get("PE_W", set()):
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='下一交易日触发 PE_W'>[★接力:vol->w]</span>"
    except ValueError:
        pass
    return overlap_marker


# =========================================================
# 视图 1：按分组 (Category) 渲染
# =========================================================
def search_history_by_category(symbol):
    html_parts = []
    sector_html, sector_has_data = build_sector_html(symbol)
    html_parts.append(sector_html)
    has_data = sector_has_data

    category_data, date_categories, category_dates, date_items, sorted_trading_dates, err = load_earning_index(symbol)
    if err:
        return "".join(html_parts) + f"<br><p style='color:red'>{err}</p>"

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
    # --- 新增：定义需要高亮的组别 ---
    highlight_categories = {
        "PE_Volume", "PE_Volume_up", "PE_Volume_high", 
        "Short", "Short_W", "SupportLevel_Close", 
        "SupportLevel_Over", "OverSell_W", "PE_W"
    }
    # -------------------------------

    html_parts = []
    sector_html, sector_has_data = build_sector_html(symbol)
    html_parts.append(sector_html)
    has_data = sector_has_data

    category_data, date_categories, category_dates, date_items, sorted_trading_dates, err = load_earning_index(symbol)
    if err:
        return "".join(html_parts) + f"<br><p style='color:red'>{err}</p>"

    hit_dates_sorted = sorted(date_items.keys(), reverse=True)
    for d_str in hit_dates_sorted:
        has_data = True
        html_parts.append(make_header(d_str, NORD_THEME['success_green']))
        items_today = sorted(date_items[d_str], key=lambda x: x[0])
        
        for category, suf in items_today:
            suf_html = build_suffix_html(category, suf)
            overlap_marker = build_overlap_marker(
                category, d_str, suf,
                category_data, date_categories, category_dates, sorted_trading_dates
            )
            
            # --- 修改：判断是否需要高亮 ---
            if category in highlight_categories:
                # 使用鲜艳的颜色（例如 Nord 主题中的 warning_red 或自定义颜色）
                display_category = f"<b style='color:#BF616A; background-color:rgba(191,97,106,0.1); padding:0 4px; border-radius:3px;'>{category}</b>"
            else:
                display_category = f"<b style='color:#88C0D0'>{category}</b>"
            # ---------------------------
            
            html_parts.append(
                f"&nbsp;&nbsp;• {display_category}{suf_html}{overlap_marker}<br>"
            )

    if not has_data:
        return f"<div style='text-align:center; margin-top:20px; color:{NORD_THEME['text_light']}'>在所有文件中<br>未找到 <b>{symbol}</b> 的任何记录。</div>"
    return "".join(html_parts)


# =========================================================
# 对话框（Tab 版）
# =========================================================
class InfoDialog(QDialog):
    def __init__(self, symbol, font_family, font_size, width, height, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Info Check: {symbol}")
        # 两栏并排,宽度加倍
        self.setGeometry(0, 0, width * 2, height)
        self.center_on_screen()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 用 QSplitter 让两栏并排,并且可以拖拽调整宽度
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # --- 左栏:按分组 ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        left_title = QLabel("按分组")
        left_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_title.setObjectName("panelTitle")

        self.text_by_cat = QTextEdit()
        self.text_by_cat.setReadOnly(True)
        self.text_by_cat.setFont(QFont(font_family))
        self.text_by_cat.setHtml(search_history_by_category(symbol))

        left_layout.addWidget(left_title)
        left_layout.addWidget(self.text_by_cat)

        # --- 右栏:按时间 ---
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        right_title = QLabel("按时间")
        right_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_title.setObjectName("panelTitle")

        self.text_by_date = QTextEdit()
        self.text_by_date.setReadOnly(True)
        self.text_by_date.setFont(QFont(font_family))
        self.text_by_date.setHtml(search_history_by_date(symbol))

        right_layout.addWidget(right_title)
        right_layout.addWidget(self.text_by_date)

        # 添加到 splitter
        self.splitter.addWidget(left_container)
        self.splitter.addWidget(right_container)
        self.splitter.setSizes([width, width])  # 初始宽度五五开
        self.splitter.setChildrenCollapsible(False)

        layout.addWidget(self.splitter)
        self.setLayout(layout)
        self.apply_nord_style(font_size)

        # 快捷键可以保留也可以删,这里让 1/2 聚焦到对应面板
        QShortcut(QKeySequence("1"), self, activated=lambda: self.text_by_cat.setFocus())
        QShortcut(QKeySequence("2"), self, activated=lambda: self.text_by_date.setFocus())

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
        width=500,      # 每一栏的宽度
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