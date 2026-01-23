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
    'success_green': '#A3BE8C', # 新增一个颜色用于区分板块
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
        
        # [修改点] 这里改成 setHtml，这样才能渲染颜色和字体样式
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

# --- 3. 核心逻辑 (已修改) ---

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

    has_data = False # 标记是否找到了任何数据

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
                # content_dict 是一个字典，例如 {"MOS": "美盛化肥"}
                # 我们只需要判断 symbol 是否是 content_dict 的 key 之一
                if symbol in content_dict:
                    # 如果有备注（value不为空），也可以加上
                    note = content_dict[symbol]
                    if note:
                        found_sectors.append(f"{category} <span style='color:#88C0D0'>({note})</span>") # 备注也可以稍微变色
                    else:
                        found_sectors.append(category)
            
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
            
        # 遍历 JSON 中的所有大类 (如 season, no_season, short 等)
        for category, date_dict in data.items():
            found_dates = []
            
            # 遍历该类下的所有日期
            for date_str, symbol_list in date_dict.items():
                if isinstance(symbol_list, list) and symbol in symbol_list:
                    found_dates.append(date_str)
            
            if found_dates:
                has_data = True
                found_dates.sort(reverse=True)
                
                # [核心修改] 使用 success_green 颜色作为 Earning 标题，并应用 HTML 样式
                html_parts.append(make_header(category, NORD_THEME['success_green']))
                
                for d in found_dates:
                    html_parts.append(f"&nbsp;&nbsp;• {d}<br>")
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
    dialog.exec()
