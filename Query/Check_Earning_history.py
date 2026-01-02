import sys
import json
import os
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

# --- 1. 配置部分 ---

JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Earning_History.json'
SECTOR_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'  # <--- 新增路径

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
        text_box.setText(content)
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
    output_lines = []
    output_lines.append(f"查询对象: {symbol}\n")
    
    # ==============================
    # 任务 1: 检索 Sector Panel (新增功能)
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
                        found_sectors.append(f"{category} ({note})")
                    else:
                        found_sectors.append(category)
            
            if found_sectors:
                output_lines.append("【 所属板块/分组 】")
                for s in found_sectors:
                    output_lines.append(f"  ★ {s}")
                output_lines.append("") # 空行分隔
            else:
                # 如果没找到，也可以选择不显示，或者显示未归类
                # output_lines.append("【 所属板块/分组 】\n  (未在 Panel 中找到)\n")
                pass

        except Exception as e:
            output_lines.append(f"读取 Sector JSON 出错: {e}\n")
    else:
        output_lines.append(f"警告: 找不到 Sector 文件\n{SECTOR_PATH}\n")

    # ==============================
    # 任务 2: 检索 Earning History (原有功能)
    # ==============================
    if not os.path.exists(JSON_PATH):
        return "\n".join(output_lines) + f"\n错误：找不到 Earning 文件\n{JSON_PATH}"

    found_history = False
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
                found_history = True
                found_dates.sort(reverse=True)
                
                output_lines.append(f"【 {category} 】")
                for d in found_dates:
                    output_lines.append(f"  • {d}")
                output_lines.append("") # 空行分隔

    except Exception as e:
        return f"读取 Earning JSON 出错: {e}"

    if not found_history and len(output_lines) <= 2: 
        # 如果既没找到 Sector 也没找到 History (output_lines 只有标题)
        return f"在所有文件中中\n未找到 {symbol} 的任何记录。"
    
    return "\n".join(output_lines)

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
