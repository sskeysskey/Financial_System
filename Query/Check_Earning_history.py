import sys
import json
import os
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

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
    'success_green': '#A3BE8C'
}

# --- 2. 界面类 (复用自 chart_input.py) ---
class InfoDialog(QDialog):
    def __init__(self, title, content, font_family, font_size, width, height, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setGeometry(0, 0, width, height)
        self.center_on_screen()
        
        layout = QVBoxLayout(self)
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

# --- 3. 核心逻辑 (已修改，移除了黑名单⚡️标志) ---
def search_history(symbol):
    # 用列表存储 HTML 片段
    html_parts = []

    # 辅助函数：生成美化的标题 HTML
    def make_header(text, color):
        # style: 颜色, 粗体, 字体稍大(1.2倍), 上下外边距
        return f"""
        <div style='margin-top: 10px; margin-bottom: 5px;'>
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
                html_parts.append("<br>")
                
        except Exception as e:
            html_parts.append(f"<p style='color:red'>读取 Sector JSON 出错: {e}</p>")
    else:
        html_parts.append(f"<p style='color:orange'>警告: 找不到 Sector 文件<br>{SECTOR_PATH}</p>")


    # ==============================
    # 任务 2: 检索 Earning History 
    # ==============================
    if not os.path.exists(JSON_PATH):
        return "".join(html_parts) + f"<br><p style='color:red'>错误：找不到 Earning 文件<br>{JSON_PATH}</p>"

    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

            # 遍历所有分类
            for category, date_dict in data.items():
                
                # 如果你想让 _Tag_Blacklist 作为一个普通分类显示出来，可以把下面两行注释掉或删掉。
                # 如果你仍希望在界面上完全隐藏这个分类不显示，请保留这两行：
                if category == "_Tag_Blacklist":
                    continue

                found_dates = []  # 改为存储元组: (日期, 中文后缀)
                
                # 遍历该类下的所有日期
                for date_str, symbol_list in date_dict.items():
                    if isinstance(symbol_list, list):
                        for item in symbol_list:
                            suffix = get_suffix_if_match(item, symbol)
                            if suffix is not None:
                                found_dates.append((date_str, suffix))
                                break  # 当前日期已找到，看下一个日期

                if found_dates:
                    has_data = True
                    # 按日期降序排序 (元组的第一个元素是日期)
                    found_dates.sort(key=lambda x: x[0], reverse=True)
                    
                    html_parts.append(make_header(category, NORD_THEME['success_green']))
                    
                    for d_str, suf in found_dates:
                        # 如果找到了你加的中文后缀（如“黑热”），在UI上以黄色小标签显示
                        suf_html = ""
                        if suf:
                            suf_html = f" <span style='color:#EBCB8B; font-size:14px; font-weight:bold;'>[{suf}]</span>"

                        # 移除了 marker 变量及闪电标志
                        html_parts.append(f"&nbsp;&nbsp;• {d_str}{suf_html}<br>")
                    html_parts.append("<br>")

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
    
    # 显示结果窗口
    dialog = InfoDialog(
        title=f"Info Check: {target_symbol}", # 标题稍微改了一下，因为现在不仅仅是 History
        content=result_content,
        font_family="Arial Unicode MS", 
        font_size=16,
        width=500,
        height=600
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
    # =======================================================

    dialog.exec()
