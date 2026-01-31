import sys
import os
import json
import sqlite3
import subprocess
from decimal import Decimal
from datetime import datetime

# --- PyQt6 核心组件 ---
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QScrollArea, QLabel, 
                             QTabWidget, QFrame, QMenu, QMessageBox)
from PyQt6.QtGui import QCursor, QAction, QColor, QKeyEvent

# --- 路径配置 (根据你的环境) ---
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# 目标数据文件
EARNING_HISTORY_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")

# 辅助数据文件
DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
WEIGHT_CONFIG_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "tags_weight.json")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")

# --- 尝试导入绘图模块 ---
chart_input_path = os.path.join(BASE_CODING_DIR, "Financial_System", "Query")
if chart_input_path not in sys.path:
    sys.path.append(chart_input_path)

try:
    from Chart_input import plot_financial_data
except ImportError:
    print(f"警告：无法从路径 '{chart_input_path}' 导入 'plot_financial_data'。点击Symbol可能无法绘图。")
    def plot_financial_data(*args, **kwargs):
        print("plot_financial_data 模拟调用:", args)

# --- 核心逻辑函数 (复用与简化) ---

def load_json_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取 {file_path} 失败: {e}")
        return {}

def load_weight_groups():
    try:
        with open(WEIGHT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            return {Decimal(k): v for k, v in raw_data.items()}
    except Exception:
        return {}

def fetch_mnspp_data_from_db(db_path, symbol):
    try:
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            cur = conn.cursor()
            cur.execute("SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?", (symbol,))
            row = cur.fetchone()
        return row if row else ("N/A", None, "N/A", "--")
    except Exception:
        return ("N/A", None, "N/A", "--")

def load_compare_data(file_path):
    data = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if ':' in line:
                    s, v = line.split(':', 1)
                    data[s.strip()] = v.strip()
    except Exception: pass
    return data

def find_tags_by_symbol(symbol, data, tags_weight_config):
    tags_with_weight = []
    default_weight = Decimal('1')
    for category in ['stocks', 'etfs']:
        for item in data.get(category, []):
            if item.get('symbol') == symbol:
                for tag in item.get('tag', []):
                    weight = tags_weight_config.get(tag, default_weight)
                    tags_with_weight.append((tag, weight))
                return tags_with_weight
    return []

def execute_external_script(script_type, keyword):
    # 简化的脚本执行器，仅保留部分常用功能
    script_configs = {
        'futu':     os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_CheckFutu.scpt'),
        'tags':     os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Tags.py'),
        'similar':  os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Find_Similar_Tag.py'),
    }
    path = script_configs.get(script_type)
    if not path: return
    try:
        if script_type == 'futu':
            subprocess.Popen(['osascript', path, keyword])
        else:
            subprocess.Popen([sys.executable, path, keyword])
    except Exception as e: print(f"执行脚本错误: {e}")

# --- 自定义 UI 组件 ---

class SymbolButton(QPushButton):
    """复用你的按钮样式和右键菜单"""
    def __init__(self, symbol, parent=None):
        super().__init__(symbol, parent)
        self.symbol = symbol
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedWidth(80)
        self.setFixedHeight(30)
        self.setObjectName("SymbolButton")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        actions = [
            ("在富途中搜索", lambda: execute_external_script('futu', self.symbol)),
            ("找相似",       lambda: execute_external_script('similar', self.symbol)),
            ("编辑 Tags",     lambda: execute_external_script('tags', self.symbol)),
        ]
        for text, func in actions:
            act = QAction(text, self)
            act.triggered.connect(func)
            menu.addAction(act)
        menu.exec(self.mapToGlobal(pos))

class SymbolCard(QWidget):
    """显示单个 Symbol 及其 Tags 的卡片"""
    def __init__(self, symbol, all_data, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.all_data = all_data
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 10)
        layout.setSpacing(2)

        # 1. Symbol 按钮行
        top_layout = QHBoxLayout()
        btn = SymbolButton(self.symbol)
        btn.clicked.connect(self.on_click)
        
        # 获取一些基本数据用于显示颜色（简单模拟）
        shares, mcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, self.symbol)
        # 这里简单根据 PE 是否存在变色，你可以根据需要复用更复杂的逻辑
        if pe != "N/A":
             btn.setStyleSheet("color: #00AEEF;") # 蓝色表示有数据
        else:
             btn.setStyleSheet("color: white;")

        top_layout.addWidget(btn)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # 2. Tags 显示
        tags = find_tags_by_symbol(self.symbol, self.all_data['description'], self.all_data['tags_weight'])
        if tags:
            tag_html = []
            highlight = "#F9A825"
            for t, w in tags:
                # 权重高的显示为高亮色
                if float(w) > 1.0:
                    tag_html.append(f"<font color='{highlight}'>{t}</font>")
                else:
                    tag_html.append(f"<font color='#888888'>{t}</font>") # 普通tag灰色
            
            tags_label = QLabel(", ".join(tag_html))
            tags_label.setWordWrap(True)
            tags_label.setStyleSheet("font-size: 13px;")
            layout.addWidget(tags_label)
        else:
            no_tag = QLabel("No Tags")
            no_tag.setStyleSheet("color: #555; font-size: 12px; font-style: italic;")
            layout.addWidget(no_tag)

        # 底部边框线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #444;")
        line.setFixedHeight(1)
        layout.addWidget(line)

    def on_click(self):
        # 准备数据调用 plot_financial_data
        desc_data = self.all_data['description']
        sector_data = self.all_data['sectors']
        compare_data = self.all_data['compare']
        
        sector = next((s for s, names in sector_data.items() if self.symbol in names), None)
        comp = compare_data.get(self.symbol, "N/A")
        shares, mcap, pe, pb = fetch_mnspp_data_from_db(DB_PATH, self.symbol)
        
        try:
            plot_financial_data(DB_PATH, sector, self.symbol, comp, (shares, pb), mcap, pe, desc_data, '1Y', False)
        except Exception as e:
            QMessageBox.critical(self, "绘图错误", str(e))

class DateSection(QWidget):
    """日期折叠组件"""
    def __init__(self, date_str, symbols, all_data, parent=None):
        super().__init__(parent)
        self.date_str = date_str
        self.symbols = symbols
        self.all_data = all_data
        self.is_expanded = False
        
        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 头部按钮 (点击展开/折叠)
        self.toggle_btn = QPushButton(f"▶  {self.date_str}  ({len(self.symbols)})")
        self.toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                text-align: left; 
                padding: 8px 15px; 
                background-color: #333; 
                border: none;
                color: #E0E0E0;
                font-size: 16px;
                font-weight: bold;
                border-bottom: 1px solid #444;
            }
            QPushButton:hover { background-color: #404040; }
        """)
        self.toggle_btn.clicked.connect(self.toggle_content)
        self.main_layout.addWidget(self.toggle_btn)

        # 内容区域 (初始隐藏)
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(20, 5, 5, 15) # 左侧缩进
        self.content_layout.setSpacing(5)
        
        # 填充 Symbols
        for sym in self.symbols:
            card = SymbolCard(sym, self.all_data)
            self.content_layout.addWidget(card)

        self.content_area.setVisible(False)
        self.main_layout.addWidget(self.content_area)

    def toggle_content(self):
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            self.content_area.setVisible(True)
            self.toggle_btn.setText(f"▼  {self.date_str}  ({len(self.symbols)})")
            self.toggle_btn.setStyleSheet(self.toggle_btn.styleSheet() + "background-color: #3A3A3A;")
        else:
            self.content_area.setVisible(False)
            self.toggle_btn.setText(f"▶  {self.date_str}  ({len(self.symbols)})")
            self.toggle_btn.setStyleSheet(self.toggle_btn.styleSheet().replace("background-color: #3A3A3A;", ""))

class EarningHistoryViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Earning History Viewer")
        self.setGeometry(100, 100, 600, 900)
        
        # 加载所有必要数据
        self.load_all_data()
        
        self.init_ui()
        self.apply_stylesheet()

    def load_all_data(self):
        self.earning_data = load_json_data(EARNING_HISTORY_PATH)
        self.desc_data = load_json_data(DESCRIPTION_PATH)
        self.sector_data = load_json_data(SECTORS_ALL_PATH)
        self.compare_data = load_compare_data(COMPARE_DATA_PATH)
        
        w_groups = load_weight_groups()
        # 展平权重配置
        self.tags_weight = {tag: w for w, tags in w_groups.items() for tag in tags}

        # 打包传递给子组件的数据包
        self.all_data_pack = {
            "description": self.desc_data,
            "sectors": self.sector_data,
            "compare": self.compare_data,
            "tags_weight": self.tags_weight
        }

    def init_ui(self):
        # 主 Tab 控件
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # 获取所有组名并排序（保证顺序一致）
        sorted_groups = sorted(self.earning_data.keys())

        # 遍历添加 Tab
        for group_name in sorted_groups:
            dates_dict = self.earning_data[group_name]
            self.create_group_tab(group_name, dates_dict)
        
        # 设置默认选中的 Tab 为 "PE_Volume_up"
        default_tab_name = "PE_Volume_up"
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == default_tab_name:
                self.tabs.setCurrentIndex(i)
                break

    def create_group_tab(self, group_name, dates_dict):
        tab_page = QWidget()
        tab_layout = QVBoxLayout(tab_page)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        content_layout.setSpacing(1) # 日期之间的间距

        # 排序日期：最新的在上面
        sorted_dates = sorted(dates_dict.keys(), reverse=True)

        for date_str in sorted_dates:
            symbols = dates_dict[date_str]
            # 过滤掉空列表
            if not symbols: continue
            
            date_section = DateSection(date_str, symbols, self.all_data_pack)
            content_layout.addWidget(date_section)

        scroll.setWidget(content_widget)
        tab_layout.addWidget(scroll)
        
        self.tabs.addTab(tab_page, group_name)

    def keyPressEvent(self, event: QKeyEvent):
        """监听按键事件，按下 ESC 关闭窗口"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #2E2E2E; }
            QTabWidget::pane { border: 0; }
            QTabBar::tab {
                background: #333;
                color: #AAA;
                padding: 10px 20px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-size: 14px;
            }
            QTabBar::tab:selected {
                background: #444;
                color: #00AEEF;
                font-weight: bold;
            }
            QScrollArea { background-color: #2E2E2E; border: none; }
            QWidget { background-color: #2E2E2E; color: #E0E0E0; }
            
            /* 滚动条样式 */
            QScrollBar:vertical {
                border: none;
                background: #2E2E2E;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            #SymbolButton {
                background-color: #2E2E2E;
                border: 1px solid #666;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            #SymbolButton:hover {
                background-color: #3A3A3A;
                border: 1px solid #00AEEF;
            }
        """)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 检查文件是否存在
    if not os.path.exists(EARNING_HISTORY_PATH):
        QMessageBox.critical(None, "错误", f"找不到文件:\n{EARNING_HISTORY_PATH}")
        sys.exit(1)

    window = EarningHistoryViewer()
    window.show()
    sys.exit(app.exec())