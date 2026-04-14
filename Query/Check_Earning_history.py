import sys
import json
import os
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt
from collections import defaultdict

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置部分 ---
JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")
SECTOR_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")

# 复用你的 NORD 主题，保持视觉一致性
NORD_THEME = {
    'background': '#2E3440',
    'widget_bg': '#3B4252',
    'border': '#4C566A',
    'text_light': '#D8DEE9',
    'text_bright': '#ECEFF4',
    'accent_blue': '#5E81AC',
    'success_green': '#A3BE8C',
    'warning_red': '#BF616A' # 新增红色用于特殊标记
}

# --- 2. 界面类 ---
class InfoDialog(QDialog):
    def __init__(self, title, content, font_family, font_size, width, height, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setGeometry(0, 0, width, height)
        self.center_on_screen()
        
        layout = QVBoxLayout(self)
        # 移除布局的内边距，让内容更紧凑
        layout.setContentsMargins(5, 5, 5, 5)
        
        text_box = QTextEdit(self)
        text_box.setReadOnly(True)
        text_box.setFont(QFont(font_family))
        
        # 渲染 HTML 内容
        text_box.setHtml(content) 
        
        layout.addWidget(text_box)
        self.setLayout(layout)
        self.apply_nord_style(font_size)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def apply_nord_style(self, font_size):
        qss = f"""
        QDialog {{ background-color: {NORD_THEME['background']}; }}
        QTextEdit {{
            background-color: {NORD_THEME['widget_bg']}; color: {NORD_THEME['text_bright']};
            border: 1px solid {NORD_THEME['border']}; border-radius: 5px;
            font-size: {font_size}px; padding: 10px;
        }}
        """
        self.setStyleSheet(qss)

# --- 3. 核心逻辑 ---
def search_history(symbol):
    # 用列表存储 HTML 片段
    html_parts = []

    # --- 修改点 1: 缩小标题的上下边距 ---
    def make_header(text, color):
        # 将 margin-top 从 10px 缩小到 4px，margin-bottom 从 5px 缩小到 2px
        return f"""
        <div style='margin-top: 4px; margin-bottom: 2px;'>
            <span style='color: {color}; font-weight: bold; font-size: 18px;'>
                {text}
            </span>
        </div>
        """

    # --- [新增] 辅助函数：模糊匹配并提取中文后缀 ---
    def get_suffix_if_match(item_str, target_symbol):
        """
        判断 item_str 是否匹配 target_symbol。
        如果匹配，返回附加的后缀（如 '黑', '听热'）；如果不匹配，返回 None。
        """
        if item_str == target_symbol:
            return ""  # 完全匹配，无后缀
        
        if item_str.startswith(target_symbol):
            suffix = item_str[len(target_symbol):]
            # 确保后缀里没有英文字母，防止搜索 "EW" 时错误匹配到真正的股票 "EWH"
            if not any(c.isascii() and c.isalpha() for c in suffix):
                return suffix
        return None

    has_data = False  # 标记是否找到了任何数据

    # ==============================
    # 任务 1: 检索 Sector Panel
    # ==============================
    if os.path.exists(SECTOR_PATH):
        try:
            with open(SECTOR_PATH, 'r', encoding='utf-8') as f:
                sector_data = json.load(f)

            found_sectors = []
            # 遍历每一个板块 (Category) 和它里面的内容 (Content)
            for category, content_dict in sector_data.items():
                # content_dict 是一个字典，遍历它的 key (股票代码)
                for key, note in content_dict.items():
                    suffix = get_suffix_if_match(key, symbol)
                    if suffix is not None:  # 匹配成功
                        display_text = category
                        # 如果有加中文后缀，用 Nord 主题的黄色显示出来
                        if suffix:
                            display_text += f" <span style='color:#EBCB8B'>[{suffix}]</span>"
                        # 如果有字典 value 中的备注，用蓝色显示
                        if note:
                            display_text += f" <span style='color:#88C0D0'>({note})</span>"
                        
                        found_sectors.append(display_text)
                        break  # 这个板块找到了，跳出内层循环找下一个板块

            if found_sectors:
                has_data = True
                # 使用 success_green 颜色作为板块标题
                html_parts.append(make_header("所属板块/分组", NORD_THEME['success_green']))
                for s in found_sectors:
                    # 使用 &nbsp; 做缩进，<br> 换行
                    html_parts.append(f"&nbsp;&nbsp;★ {s}<br>")
                # --- 修改点 2: 移除这里的 html_parts.append("<br>") 以缩小大组之间的间距 ---
                
        except Exception as e:
            html_parts.append(f"<p style='color:red'>读取 Sector JSON 出错: {e}</p>")

    # ==============================
    # 任务 2: 检索 Earning History 
    # ==============================
    if not os.path.exists(JSON_PATH):
        return "".join(html_parts) + f"<br><p style='color:red'>错误：找不到 Earning 文件<br>{JSON_PATH}</p>"

    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

            # --- 修改点：先收集所有匹配的数据，用于检测同一天的多重出现 ---
            # 结构: category_data[category] = [(date_str, suffix), ...]
            # 统计每个日期出现的分类: date_categories[date_str] = set([category1, category2, ...])
            # 统计每个分类包含的日期（仅针对当前symbol）: category_dates[category] = set([date1, date2, ...])
            category_data = defaultdict(list)
            date_categories = defaultdict(set)
            category_dates = defaultdict(set)
            
            # 收集 JSON 中所有的交易日期，用于判断“昨天”和“今天”
            all_trading_dates = set()

            for category, date_dict in data.items():
                
                # 如果你想让 _Tag_Blacklist 作为一个普通分类显示出来，可以把下面两行注释掉或删掉。
                # 如果你仍希望在界面上完全隐藏这个分类不显示，请保留这两行：
                if category == "_Tag_Blacklist":
                    continue

                for date_str, symbol_list in date_dict.items():
                    all_trading_dates.add(date_str) # 收集所有日期
                    
                    if isinstance(symbol_list, list):
                        for item in symbol_list:
                            suffix = get_suffix_if_match(item, symbol)
                            if suffix is not None:
                                category_data[category].append((date_str, suffix))
                                date_categories[date_str].add(category)
                                category_dates[category].add(date_str)
                                break 

            # 将所有交易日期降序排列（索引 0 是最新日期，索引越大日期越旧）
            sorted_trading_dates = sorted(list(all_trading_dates), reverse=True)

            # 构建 HTML
            for category, found_dates in category_data.items():
                if found_dates:
                    has_data = True
                    # 按日期降序排序 (元组的第一个元素是日期)
                    found_dates.sort(key=lambda x: x[0], reverse=True)
                    
                    html_parts.append(make_header(category, NORD_THEME['success_green']))
                    
                    for d_str, suf in found_dates:
                        # 如果找到了你加的中文后缀（如“黑热”），在UI上以黄色小标签显示
                        suf_html = ""
                        if suf:
                            # 检查是否为 PE_Volume 分类且后缀包含'追'
                            if category == "PE_Volume" and '追' in suf:
                                # 将'追'字用红色span包裹，其他部分保持原来的黄色
                                processed_suf = suf.replace('追', "<span style='color:red;'>追</span>")
                                suf_html = f" <span style='color:#EBCB8B; font-size:14px; font-weight:bold;'>[{processed_suf}]</span>"
                            else:
                                # 其他情况，保持原样
                                suf_html = f" <span style='color:#EBCB8B; font-size:14px; font-weight:bold;'>[{suf}]</span>"

                        # --- 修改点：仅当该日期同时存在于 PE_Volume 和 Short 时，才在这两个分组里标记 ---
                        overlap_marker = ""
                        
                        # 1. 同日多重触发检测
                        combinations = [
                            {"tags": {"PE_Volume", "Short"}, "label": "PE_Volume & Short"},
                            {"tags": {"PE_Volume", "Short_W"}, "label": "PE_Volume & Short_W"}
                        ]
                        
                        # 检查当前日期是否触发了任何组合
                        for combo in combinations:
                            # 检查 date_categories[d_str] 是否包含了该组合中的所有 tag
                            if combo["tags"].issubset(date_categories[d_str]):
                                # 如果当前分类属于该组合中的任意一个，就显示标记
                                if category in combo["tags"]:
                                    overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;' title='同一天同时触发 {combo['label']}'>[★多重触发]</span>"
                                    break 

                        # =======================================================
                        # [新增规则]: PE_Volume_high (带'抄底') & PE_W 同日触发
                        # =======================================================
                        if "PE_W" in date_categories[d_str] and "PE_Volume_high" in date_categories[d_str]:
                            # 检查 PE_Volume_high 的这条记录后缀是否包含 '抄底'
                            is_chaodi = False
                            if category == "PE_Volume_high":
                                is_chaodi = (suf and '抄底' in suf)
                            else:
                                # 如果当前正在处理的是 PE_W（或其他），我们需要去查一下 PE_Volume_high 里的后缀
                                for d, s in category_data.get("PE_Volume_high", []):
                                    if d == d_str and s and '抄底' in s:
                                        is_chaodi = True
                                        break
                            
                            # 如果确认包含'抄底'，且当前分类是这两个之一，则添加红色标记
                            if is_chaodi and category in ["PE_Volume_high", "PE_W"]:
                                overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;' title='同一天触发 PE_Volume_high(抄底) 和 PE_W'>[★多重触发:抄底+W]</span>"

                        # =======================================================
                        # [新增规则]: A分组群 与 支撑位(B分组群) 同日触发
                        # =======================================================
                        group_a = {"PE_Volume", "PE_Volume_up", "PE_Volume_high", "PE_W", "PE_Deeper", "PE_Deep", "OverSell_W", "PE_Hot", "Short", "Short_W"}
                        if category in group_a:
                            if "SupportLevel_Close" in date_categories[d_str]:
                                overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;'>[接近支撑位]</span>"
                            if "SupportLevel_Over" in date_categories[d_str]:
                                overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;'>[超过支撑位]</span>"

                        # 2. 跨日接力触发检测 (pe_w 与 pe_hot / PE_Volume)
                        try:
                            date_idx = sorted_trading_dates.index(d_str)
                            
                            if category == "PE_W":
                                # 检查前一个交易日 (date_idx + 1) 是否在 PE_Hot 或 PE_Volume 中
                                if date_idx + 1 < len(sorted_trading_dates):
                                    prev_date = sorted_trading_dates[date_idx + 1]
                                    prev_in_hot = prev_date in category_dates.get("PE_Hot", set())
                                    prev_in_vol = prev_date in category_dates.get("PE_Volume", set())
                                    
                                    if prev_in_hot and prev_in_vol:
                                        overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;' title='前一交易日触发 PE_Hot 和 PE_Volume'>[★接力:hot+vol->w]</span>"
                                    elif prev_in_hot:
                                        overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;' title='前一交易日触发 PE_W'>[★接力:hot->w]</span>"
                                    elif prev_in_vol:
                                        overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;' title='前一交易日触发 PE_Volume'>[★接力:vol->w]</span>"
                            
                            elif category == "PE_Hot":
                                # 检查后一个交易日 (date_idx - 1) 是否在 pe_w 中
                                if date_idx - 1 >= 0:
                                    next_date = sorted_trading_dates[date_idx - 1]
                                    if next_date in category_dates.get("pe_w", set()):
                                        overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;' title='下一交易日触发 PE_W'>[★接力:hot->w]</span>"
                                        
                            elif category == "PE_Volume":
                                # 检查后一个交易日 (date_idx - 1) 是否在 pe_w 中
                                if date_idx - 1 >= 0:
                                    next_date = sorted_trading_dates[date_idx - 1]
                                    if next_date in category_dates.get("pe_w", set()):
                                        overlap_marker += f" <span style='color:{NORD_THEME['warning_red']}; font-weight:bold;' title='下一交易日触发 PE_W'>[★接力:vol->w]</span>"
                                        
                        except ValueError:
                            pass

                        html_parts.append(f"&nbsp;&nbsp;• {d_str}{suf_html}{overlap_marker}<br>")

    except Exception as e:
        return f"<p style='color:red'>读取 Earning JSON 出错: {e}</p>"

    if not has_data:
        return f"<div style='text-align:center; margin-top:20px; color:{NORD_THEME['text_light']}'>在所有文件中<br>未找到 <b>{symbol}</b> 的任何记录。</div>"

    return "".join(html_parts)


# --- 4. 程序入口 ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 获取传入的参数 (Symbol)
    target_symbol = "UNKNOWN"
    if len(sys.argv) > 1:
        target_symbol = sys.argv[1]
    
    result_content = search_history(target_symbol)
    
    # --- 修改点 4: 增大界面的高度 (height 从 600 改为 850) ---
    dialog = InfoDialog(
        title=f"Info Check: {target_symbol}", # 标题稍微改了一下，因为现在不仅仅是 History
        content=result_content,
        font_family="Arial Unicode MS", 
        font_size=16,
        width=500,
        height=850  # 这里调大了高度
    )

    # =======================================================
    # 新增：解决 macOS 窗口在 Dock 弹跳而不置前的问题
    # =======================================================
    
    # 1. PyQt 原生窗口置前请求
    dialog.raise_()
    dialog.activateWindow()

    # 2. (可选推荐) 如果你希望这个查询窗口始终悬浮在主图表之上，取消下面这行的注释：
    # dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

    # 3. macOS 终极杀手锏：利用 AppleScript 强制将当前 PID 进程推到最前
    import platform
    import subprocess
    if platform.system() == "Darwin":
        try:
            # 告诉 macOS 系统事件：把当前进程 ID 的应用设为最前
            subprocess.run([
                'osascript', '-e',
                f'tell application "System Events" to set frontmost of the first process whose unix id is {os.getpid()} to true'
            ], check=False)
        except Exception as e:
            print(f"macOS 强制置前执行失败: {e}")

    dialog.exec()