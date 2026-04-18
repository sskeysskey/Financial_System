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
                
                # 获取前一天的相关状态
                prev_in_hot = prev_date in category_dates.get("PE_Hot", set())
                prev_in_vol = prev_date in category_dates.get("PE_Volume", set())
                prev_in_short = prev_date in category_dates.get("Short", set())
                prev_in_short_w = prev_date in category_dates.get("Short_W", set())

                # 1. 原有的 PE_Hot 和 PE_Volume 逻辑
                if prev_in_hot and prev_in_vol:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触发 PE_Hot 和 PE_Volume'>[★Hot+Volume->W]</span>"
                elif prev_in_hot:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触发 PE_Hot'>[★接力:Hot->W]</span>"
                elif prev_in_vol:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触发 PE_Volume'>[★Volume->W]</span>"
                
                # 2. 新增：检查 Short 或 Short_W
                if prev_in_short or prev_in_short_w:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触发 Short 或 Short_W'>[★Short->W]</span>"

                # 3. 原有的支撑位逻辑
                prev_in_supp_close = prev_date in category_dates.get("SupportLevel_Close", set())
                prev_in_supp_over = prev_date in category_dates.get("SupportLevel_Over", set())
                if prev_in_supp_close or prev_in_supp_over:
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='前一交易日触及或跌破支撑位'>[★支撑位->W]</span>"
        elif category == "PE_Hot":
            if date_idx - 1 >= 0:
                next_date = sorted_trading_dates[date_idx - 1]
                if next_date in category_dates.get("PE_W", set()):
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='下一交易日触发 PE_W'>[★Hot->W]</span>"
        elif category == "PE_Volume":
            if date_idx - 1 >= 0:
                next_date = sorted_trading_dates[date_idx - 1]
                if next_date in category_dates.get("PE_W", set()):
                    overlap_marker += f" <span style='color:{red}; font-weight:bold;' title='下一交易日触发 PE_W'>[★Volume->W]</span>"
    except ValueError:
        pass
    return overlap_marker


# =========================================================
# 视图 1：按分组 (Category) 渲染
# =========================================================
def search_history_by_category(symbol):
    html_parts = []
    # --- 已移除 sector 相关逻辑 ---
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
    # --- 新增：定义颜色级别 ---
    # 红色 (高权重)
    COLOR_HIGH = "#BF616A" 
    # 柔和的橙色或淡红色 (中权重) - 这里使用 Nord 主题中的一个柔和色，或者你自己喜欢的颜色
    COLOR_MEDIUM = "#D08770" 
    
    # --- 新增：分类映射 ---
    # 高权重组 (保持红色)
    high_weight_categories = {
        "PE_Volume", "Short", "Short_W", "PE_W", "PE_Hot"
    }
    # 中权重组 (换成弱一点的颜色)
    medium_weight_categories = {
        "PE_Volume_up", "PE_Volume_high", 
        "SupportLevel_Close", "SupportLevel_Over", "OverSell_W"
    }
    
    # 依然保留这个集合用于判断是否需要特殊样式背景
    highlight_categories = high_weight_categories.union(medium_weight_categories)
    
    # --- 新增：可配置的需要压缩显示的单一分组 ---
    compress_categories = {"PE_valid"}

    html_parts = []
    # --- 已移除 sector 相关逻辑 ---
    has_data = False

    category_data, date_categories, category_dates, date_items, sorted_trading_dates, err = load_earning_index(symbol)
    if err:
        return f"<p style='color:red'>{err}</p>"

    hit_dates_sorted = sorted(date_items.keys(), reverse=True)
    
    # 用于分离正常日期和需要压缩的日期
    normal_dates = []
    compressed_records = defaultdict(list)

    # 第一次遍历：筛选出需要压缩的日期
    for d_str in hit_dates_sorted:
        items_today = sorted(date_items[d_str], key=lambda x: x[0])
        # 如果当天只有一条记录，且属于需要压缩的分组
        if len(items_today) == 1 and items_today[0][0] in compress_categories:
            category, suf = items_today[0]
            compressed_records[category].append((d_str, suf))
        else:
            normal_dates.append((d_str, items_today))

    # --- 新增：定义需要保持纵向排列的重要组别 ---
    group_a = {"PE_Volume", "PE_Volume_up", "PE_Volume_high", "PE_W",
                "PE_Hot", "Short", "Short_W"}

    # 渲染正常日期的记录
    for d_str, items_today in normal_dates:
        has_data = True
        # 判断当天是否包含 group_a 中的重要分组
        has_group_a = any(cat in group_a for cat, _ in items_today)

        # 先把每一条渲染成 HTML 片段，横纵两种排版共用
        rendered_items = []
        for category, suf in items_today:
            suf_html = build_suffix_html(category, suf)
            overlap_marker = build_overlap_marker(
                category, d_str, suf,
                category_data, date_categories, category_dates, sorted_trading_dates
            )

            # --- 修改核心：根据权重选择颜色 ---
            if category in highlight_categories:
                # 决定使用哪种颜色
                target_color = COLOR_HIGH if category in high_weight_categories else COLOR_MEDIUM
                
                # 构造样式字符串
                display_category = (
                    f"<b style='color:{target_color}; background-color:rgba(191,97,106,0.1); "
                    f"padding:0 4px; border-radius:3px;'>{category}</b>"
                )
            else:
                display_category = f"<b style='color:#88C0D0'>{category}</b>"

            rendered_items.append(f"• {display_category}{suf_html}{overlap_marker}")

        if has_group_a:
            # 重要分组：保持原来的纵向排版（日期作为大标题 + 纵向列表）
            html_parts.append(make_header(d_str, NORD_THEME['success_green']))
            for item in rendered_items:
                html_parts.append(f"&nbsp;&nbsp;{item}<br>")
        else:
            # 非重要分组：日期 + 内容 同一行横向显示
            date_html = (
                f"<span style='color:{NORD_THEME['success_green']}; "
                f"font-weight:bold; font-size:15px;'>{d_str}</span>"
            )
            joined = "&nbsp;&nbsp;&nbsp;&nbsp;".join(rendered_items)
            html_parts.append(
                f"<div style='padding-left: 4px; line-height: 1.8; "
                f"margin-top:2px; margin-bottom:2px;'>"
                f"{date_html}&nbsp;&nbsp;&nbsp;&nbsp;{joined}"
                f"</div>"
            )

    # 渲染被压缩的单一分组记录（统一放在下方）
    for category, records in compressed_records.items():
        has_data = True
        # 使用分组名作为大标题
        html_parts.append(make_header(f"{category} (单一触发)", NORD_THEME['success_green']))
        
        date_strings = []
        for d_str, suf in records:
            suf_html = build_suffix_html(category, suf)
            overlap_marker = build_overlap_marker(
                category, d_str, suf,
                category_data, date_categories, category_dates, sorted_trading_dates
            )
            # 拼接日期和它可能带有的后缀/标记
            date_strings.append(f"<span style='color:{NORD_THEME['text_bright']}'>{d_str}</span>{suf_html}{overlap_marker}")
        
        # 将所有日期用逗号拼接，放在一个 div 中自动换行
        joined_dates = ",&nbsp;&nbsp;".join(date_strings)
        html_parts.append(f"<div style='padding-left: 10px; line-height: 1.6;'>{joined_dates}</div><br>")

    if not has_data:
        return f"<div style='text-align:center; margin-top:20px; color:{NORD_THEME['text_light']}'>在所有文件中<br>未找到 <b>{symbol}</b> 的任何记录。</div>"
    return "".join(html_parts)


# =========================================================
# 修改后的 InfoDialog 类初始化
# =========================================================
class InfoDialog(QDialog):
    def __init__(self, symbol, font_family, font_size, left_width, right_width, height, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Info Check: {symbol}")
        
        # 整体宽度为两栏之和
        self.setGeometry(0, 0, left_width + right_width, height)
        self.center_on_screen()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 用 QSplitter 让两栏并排,并且可以拖拽调整宽度
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # --- 修改点：现在先创建“按时间”面板 ---
        # --- 左栏:按时间 ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        left_title = QLabel("按时间")  # 标题改为“按时间”
        left_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_title.setObjectName("panelTitle")

        self.text_by_date = QTextEdit()
        self.text_by_date.setReadOnly(True)
        self.text_by_date.setFont(QFont(font_family))
        self.text_by_date.setHtml(search_history_by_date(symbol)) # 调用按时间函数

        left_layout.addWidget(left_title)
        left_layout.addWidget(self.text_by_date)

        # --- 修改点：现在后创建“按分组”面板 ---
        # --- 右栏:按分组 ---
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        right_title = QLabel("按分组")  # 标题改为“按分组”
        right_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_title.setObjectName("panelTitle")

        self.text_by_cat = QTextEdit()
        self.text_by_cat.setReadOnly(True)
        self.text_by_cat.setFont(QFont(font_family))
        self.text_by_cat.setHtml(search_history_by_category(symbol)) # 调用按分组函数

        right_layout.addWidget(right_title)
        right_layout.addWidget(self.text_by_cat)

        # 添加到 splitter
        self.splitter.addWidget(left_container)
        self.splitter.addWidget(right_container)
        
        # 设置初始宽度比例 (这里传入具体的宽度值)
        self.splitter.setSizes([left_width, right_width]) 
        self.splitter.setChildrenCollapsible(False)

        layout.addWidget(self.splitter)
        self.setLayout(layout)
        self.apply_nord_style(font_size)

        # 快捷键对应调整：1 现在对应“按时间”，2 现在对应“按分组”
        QShortcut(QKeySequence("1"), self, activated=lambda: self.text_by_date.setFocus())
        QShortcut(QKeySequence("2"), self, activated=lambda: self.text_by_cat.setFocus())

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
        left_width=700,   # 时间栏更宽
        right_width=500,  # 分组栏相对窄一点
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