import sys
import json
import sqlite3
from collections import OrderedDict
import subprocess

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QTextEdit, QDialog,
    QInputDialog, QMenu, QFrame
)
from PyQt5.QtCore import Qt, QMimeData, QPoint
from PyQt5.QtGui import QFont, QCursor, QDrag, QPixmap

# ----------------------------------------------------------------------
# Update sys.path so we can import from custom modules
# ----------------------------------------------------------------------
sys.path.append('/Users/yanzhang/Coding/Financial_System/Query')
from Chart_input import plot_financial_data

# ----------------------------------------------------------------------
# Constants / Global Configurations
# ----------------------------------------------------------------------
CONFIG_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'
COLORS_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Colors.json'
DESCRIPTION_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
SECTORS_ALL_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
# ### 删除 ###: 移除了 SHARES_PATH 和 MARKETCAP_PATH
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'

DISPLAY_LIMITS = {
    'default': 'all',  # 默认显示全部
    "Bonds": 3,
}

# Define categories as a global variable
categories = [
    ['Basic_Materials','Consumer_Cyclical','Real_Estate','Technology','Energy','Industrials',
     'Consumer_Defensive','Communication_Services','Financial_Services', 'Healthcare','Utilities'],
    ['Qualified','Next Week','2 Weeks','3 Weeks'],
    ['Notification','Next_Week','Earning_Filter'],
    ['Watching'],
    ['Bonds','Indices'],
    ['Economics','Commodities'],
    ['Crypto','Currencies'],
]

# Global variables initialized below; placeholders for IDE clarity
symbol_manager = None
compare_data = {}
# ### 删除 ###: 移除了 shares 和 marketcap_pe_data 全局变量
config = {}
keyword_colors = {}
sector_data = {}
json_data = {}

class DraggableGroupBox(QGroupBox):
    def __init__(self, title, group_name, parent=None):
        super().__init__(title, parent)
        self.group_name   = group_name
        self.setAcceptDrops(True)
        self._placeholder = None    # QFrame 线
        self._last_index  = None    # 上次插入位置

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat('application/x-symbol'):
            ev.acceptProposedAction()
            self._clear_placeholder()
            self._last_index = None

    def dragMoveEvent(self, ev):
        if not ev.mimeData().hasFormat('application/x-symbol'):
            return
        ev.acceptProposedAction()

        # 1) 先取出所有“真实” widget（排除 placeholder）
        layout = self.layout()
        widgets = [layout.itemAt(i).widget()
                   for i in range(layout.count())
                   if layout.itemAt(i).widget() is not self._placeholder]

        # 2) 计算应该插到哪个“真实控件”前面
        y = ev.pos().y()
        dst = len(widgets)
        for i, w in enumerate(widgets):
            mid = w.geometry().center().y()
            if y < mid:
                dst = i
                break

        # 3) 只有位置变化时才更新 placeholder
        if dst != self._last_index:
            self._show_placeholder_at(widgets, dst)

    def dropEvent(self, ev):
        data = ev.mimeData().data('application/x-symbol')
        symbol, src = bytes(data).decode().split('|')

        # 用上次计算好的 _last_index，如果没有，就实时算一次
        dst = self._last_index
        if dst is None:
            # 同 dragMoveEvent 里的逻辑
            layout = self.layout()
            widgets = [layout.itemAt(i).widget()
                       for i in range(layout.count())
                       if layout.itemAt(i).widget() is not self._placeholder]
            y = ev.pos().y()
            dst = len(widgets)
            for i, w in enumerate(widgets):
                if y < w.geometry().center().y():
                    dst = i
                    break

        self._clear_placeholder()
        ev.acceptProposedAction()

        # 通知 MainWindow
        mw = self.window()
        mw.reorder_item(symbol, src, self.group_name, dst)

    def dragLeaveEvent(self, ev):
        self._clear_placeholder()

    def _show_placeholder_at(self, widgets, dst):
        self._clear_placeholder()
        layout = self.layout()

        # 计算在 layout 里的插入索引
        full_idx = 0
        for i in range(layout.count()):
            w2 = layout.itemAt(i).widget()
            if w2 is self._placeholder:
                continue
            if widgets and w2 is widgets[0] and dst == 0:
                break
            if w2 is widgets[dst] if dst < len(widgets) else None:
                break
            # 如果当前 w2 不是 placeholder，并且它不是我们要插入前的 widget，就++
            if w2 is not self._placeholder:
                full_idx += 1

        # 创建并插入那条红线
        line = QFrame(self)
        line.setFixedHeight(2)
        line.setStyleSheet("background-color:red;")
        layout.insertWidget(full_idx, line)
        self._placeholder = line
        self._last_index = dst

    def _clear_placeholder(self):
        if self._placeholder:
            self.layout().removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None
            self._last_index  = None

class SymbolButton(QPushButton):
    def __init__(self, text, symbol, group, parent=None):
        super().__init__(text, parent)
        self._symbol = symbol
        self._group  = group
        self._drag_start = QPoint()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_start = ev.pos()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if not (ev.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(ev)
        if (ev.pos() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData('application/x-symbol', f"{self._symbol}|{self._group}".encode())
        drag.setMimeData(mime)

        # 用控件截图作拖拽图标
        pm = self.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(ev.pos())

        drag.exec_(Qt.MoveAction)

class SymbolManager:
    def __init__(self, config_data, all_categories):
        self.symbols = []
        self.current_index = -1
        for category_group in all_categories:
            for sector in category_group:
                if sector in config_data:
                    sector_content = config_data[sector]
                    if isinstance(sector_content, dict):
                        self.symbols.extend(sector_content.keys())
                    else:
                        self.symbols.extend(sector_content)
        if not self.symbols:
            print("Warning: No symbols found based on the provided categories and config.")

    def next_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def previous_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index - 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def set_current_symbol(self, symbol):
        if symbol in self.symbols:
            self.current_index = self.symbols.index(symbol)
        else:
            print(f"Warning: Symbol {symbol} not found in the list.")

    def reset(self):
        self.current_index = -1

# ----------------------------------------------------------------------
# Utility / Helper Functions
# ----------------------------------------------------------------------
def limit_items(items, sector):
    """
    根据配置限制显示数量
    """
    limit = DISPLAY_LIMITS.get(sector, DISPLAY_LIMITS.get('default', 'all'))
    if limit == 'all':
        return items
    return list(items)[:limit]

def load_json(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)


def load_text_data(path):
    """
    加载文本文件的数据。如果数据中包含逗号，则拆分为元组，
    否则直接返回字符串。
    """
    data = {}
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue  # 跳过空行
            # 分割 key 和 value
            key, value = map(str.strip, line.split(':', 1))
            # 提取 key 的最后一个单词
            cleaned_key = key.split()[-1]
            # 如果 value 中包含逗号，则拆分后存储为元组
            if ',' in value:
                parts = [p.strip() for p in value.split(',')]
                data[cleaned_key] = tuple(parts)
            else:
                data[cleaned_key] = value
    return data

# ### 删除 ###: 移除了不再需要的 load_marketcap_pe_data 函数

# ### 新增 ###: 从 b.py 借鉴的数据库查询函数
def fetch_mnspp_data_from_db(db_path, symbol):
    """
    根据股票代码从MNSPP表中查询 shares, marketcap, pe_ratio, pb。
    如果未找到，则返回默认值。
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = "SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?"
        cursor.execute(query, (symbol,))
        result = cursor.fetchone()

    if result:
        # 数据库查到了数据，返回实际值
        shares, marketcap, pe, pb = result
        return shares, marketcap, pe, pb
    else:
        # 数据库没查到，返回默认值
        return "N/A", None, "N/A", "--"
    
def fetch_latest_earning_date(symbol):
    """
    从 earning 表里取 symbol 的最近一次财报日期，
    如果没有记录就返回“无”。
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT date FROM earning WHERE name = ? ORDER BY date DESC LIMIT 1",
                (symbol,)
            )
            row = cursor.fetchone()
            return row[0] if row else "无"
    except Exception as e:
        print(f"查询最新财报日期出错: {e}")
        return "无"

def query_database(db_path, table_name, condition):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
        cursor.execute(query)
        rows = cursor.fetchall()
        if not rows:
            return "今天没有数据可显示。\n"
        columns = [desc[0] for desc in cursor.description]
        # Compute column widths for neat spacing
        col_widths = [max(len(str(row[i])) for row in rows + [columns]) for i in range(len(columns))]

        header = ' | '.join([col.ljust(col_widths[idx]) for idx, col in enumerate(columns)]) + '\n'
        separator = '-' * len(header) + '\n'

        output_lines = [header, separator]
        for row in rows:
            row_str = ' | '.join(str(item).ljust(col_widths[idx]) for idx, item in enumerate(row))
            output_lines.append(row_str + '\n')
        return ''.join(output_lines)

# *** 函数已修改为非阻塞式调用 ***
def execute_external_script(script_type, keyword, group=None, main_window=None):
    base_path = '/Users/yanzhang/Coding/Financial_System'
    python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
    script_configs = {
        'blacklist': f'{base_path}/Operations/Insert_Blacklist.py',
        'similar': f'{base_path}/Query/Search_Similar_Tag.py',
        'tags': f'{base_path}/Operations/Editor_Tags.py',
        'editor_earning': f'{base_path}/Operations/Editor_Earning_DB.py',
        'earning': f'{base_path}/Operations/Insert_Earning.py',
        'event_input': f'{base_path}/Operations/Insert_Events.py',  # <--- 新增这一行
        'event_editor': f'{base_path}/Operations/Editor_Events.py',  # <--- 新增这一行
        'futu': '/Users/yanzhang/Coding/ScriptEditor/Stock_CheckFutu.scpt',
        'kimi': '/Users/yanzhang/Coding/ScriptEditor/CheckKimi_Earning.scpt'
    }

    try:
        # 1) 对于 “编辑 Tags”、“新增事件”、“编辑事件” —— 阻塞调用，跑完后刷新 UI
        if script_type in ('tags', 'event_input', 'event_editor'):
            if script_type in ('futu', 'kimi'):
                cmd = ['osascript', script_configs[script_type], keyword]
            else:
                cmd = [python_path, script_configs[script_type], keyword]
            subprocess.run(cmd)   # ⬅︎ 阻塞，等脚本写完文件

            # 重新 load 外部文件，并刷新面板
            if main_window:
                global json_data, compare_data
                json_data    = load_json(DESCRIPTION_PATH)
                main_window.refresh_selection_window()
        else:
            if script_type in ['futu', 'kimi']:
                subprocess.Popen(['osascript', script_configs[script_type], keyword]) # <--- 修改为 Popen
            else:
                python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
                subprocess.Popen([python_path, script_configs[script_type], keyword]) # <--- 修改为 Popen

        # 注意：因为 Popen 是非阻塞的，如果 'blacklist' 脚本也需要时间运行，
        # delete_item 可能会在脚本完成前执行。
        # 但对于黑名单这种操作，通常很快，所以这里暂时保持不变是可行的。
        if script_type == 'blacklist' and group and main_window:
            main_window.delete_item(keyword, group)

    except subprocess.CalledProcessError as e:
        print(f"执行脚本时出错: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")

def get_tags_for_symbol(symbol):
    """
    根据 symbol 在 json_data 中查找 tag 信息，
    如果在 stocks 或 etfs 中找到则返回 tag 数组，否则返回 "无标签"。
    """
    for item in json_data.get("stocks", []):
        if item.get("symbol", "") == symbol:
            return item.get("tag", "无标签")
    for item in json_data.get("etfs", []):
        if item.get("symbol", "") == symbol:
            return item.get("tag", "无标签")
    return "无标签"

# ----------------------------------------------------------------------
# PyQt5 Main Application Window (已移除小按钮并更新右键菜单)
# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 将全局变量作为实例变量
        global config, symbol_manager
        self.config = config
        self.symbol_manager = symbol_manager

        # 创建一个从内部长名称到UI显示短名称的映射字典
        self.display_name_map = {
            'Communication_Services': 'Communication',
            'Consumer_Defensive': 'Defensive',
            'Consumer_Cyclical': 'Cyclical',
            'Basic_Materials': 'Materials',
            'Financial_Services': 'Financial',
            'Notification': '策略 3',
            'Next_Week': '策略 1/2',
            'Earning_Filter': '策略 4'
        }
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("选择查询关键字")
        # self.setGeometry(100, 100, 1480, 900)
        
        # <--- 第1处修改：设置主窗口的焦点策略，使其能接收键盘事件 ---
        self.setFocusPolicy(Qt.StrongFocus)

        # 创建 QScrollArea 作为主滚动区域
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.setCentralWidget(self.scroll_area)

        # 创建一个容器 QWidget 用于存放所有内容
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)

        # 创建水平布局来容纳垂直的列
        self.main_layout = QHBoxLayout(self.scroll_content)
        self.scroll_content.setLayout(self.main_layout)

        self.apply_stylesheet()
        self.populate_widgets()

    def apply_stylesheet(self):
        """创建并应用 QSS 样式表 (增强了 GroupBox 的可见性)"""
        # 映射颜色到 QSS 样式
        button_styles = {
            "Cyan": ("#008B8B", "white"), "Blue": ("#1E3A8A", "white"),
            "Purple": ("#9370DB", "black"), "Green": ("#276E47", "white"),
            "White": ("#A9A9A9", "black"), "Yellow": ("#BDB76B", "black"),
            "Orange": ("#CD853F", "black"), "Red": ("#912F2F", "#FFFFF0"),
            "Black": ("#333333", "white"), "Default": ("#666666", "black")
        }
        
        qss = ""
        for name, (bg, fg) in button_styles.items():
            qss += f"""
            QPushButton#{name} {{
                background-color: {bg};
                color: {fg};
                font-size: 16px;
                padding: 5px;
                border: 1px solid #333; /* 通用边框，对黑色按钮无效 */
                border-radius: 4px;
            }}
            QPushButton#{name}:hover {{
                background-color: {self.lighten_color(bg)};
            }}
            """
        
        qss += """
        /* 为白色按钮设置一个特殊的、更柔和的灰色边框 */
        QPushButton#White {
            border: 1px solid #B0B0B0;
        }

        /* 为黑色按钮专门设置一个可见的、中等亮度的灰色边框 */
        QPushButton#Black {
            border: 1px solid #888888;
        }
        """

        qss += """
        QGroupBox {
            /* --- 整体视觉增强 --- */
            font-size: 20px;          /* 增大标题默认字体 */
            font-weight: bold;
            
            /* 1. 添加清晰的边框和圆角，形成“卡片”效果 */
            border: 1px solid #A9A9A9; /* 使用一个中等强度的灰色边框 (DarkGray) */
            border-radius: 8px;       /* 边角更圆润，看起来更柔和 */
            
            /* 2. 增加上边距，确保组与组之间有足够间距 */
            margin-top: 15px; 
            
            /* 3. 增加内边距，让内部的按钮不要紧贴边框 */
            /*    上内边距设置得大一些，为标题留出空间 */
            padding: 10px 10px 10px 10px; /* 上(为标题留空)、右、下、左 */
        }

        QGroupBox::title {
            /* --- 标题视觉增强 --- */
            
            /*
             * ### 新增 ###
             * 为标题设置一个明确的、高对比度的字体颜色。
             * 黑色是最清晰的选择。
            */
            color: white;
            
            subcontrol-origin: margin;
            subcontrol-position: top left;
            
            /* 5. 调整位置和内边距，使其看起来像一个标签 */
            left: 15px;               /* 从左边框向内移动一点 */
            padding: 2px 8px;         /* 上下和左右的内边距，让文字更舒展 */
            
            /* ### 移除 ###: 去掉背景色、边框和圆角，让文字直接显示在窗口背景上 */
            /* background-color: #F0F0F0; */
            /* border: 1px solid #A9A9A9; */
            /* border-radius: 4px; */
        }
        """
        self.setStyleSheet(qss)

    def reorder_item(self, symbol, src, dst, dst_index):
        cfg = self.config
        # 1) 先从 src 拿出 item_value
        if isinstance(cfg[src], dict):
            item = cfg[src].pop(symbol)
        else:
            lst = cfg[src]
            lst.remove(symbol)
            item = symbol

        # 2) 确保 dst 存在，并按容器类型插入
        if dst not in cfg:
            cfg[dst] = {} if isinstance(cfg.get(src), dict) else []
        target = cfg[dst]
        if isinstance(target, dict):
            # dict 我们重建 OrderedDict 来保证顺序
            od = OrderedDict()
            keys = list(target.keys())
            vals = list(target.values())
            keys.insert(dst_index, symbol)
            vals.insert(dst_index, item)
            for k,v in zip(keys, vals):
                od[k] = v
            cfg[dst] = od
        else:
            target.insert(dst_index, symbol)

        # 3) 写回并刷新
        with open(CONFIG_PATH,'w',encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        self.refresh_selection_window()
    
    def lighten_color(self, color_name, factor=1.1):
        """一个简单的函数来让颜色变亮，用于:hover效果"""
        from PyQt5.QtGui import QColor
        color = QColor(color_name)
        h, s, l, a = color.getHslF()
        l = min(1.0, l * factor)
        color.setHslF(h, s, l, a)
        return color.name()

    def get_button_style_name(self, keyword):
        """返回按钮的 objectName 以应用 QSS 样式"""
        color_map = {
            "red": "Red", "cyan": "Cyan", "blue": "Blue", "purple": "Purple",
            "yellow": "Yellow", "orange": "Orange", "black": "Black",
            "white": "White", "green": "Green"
        }
        for color, style_name in color_map.items():
            if keyword in keyword_colors.get(f"{color}_keywords", []):
                return style_name
        return "Default"

    def populate_widgets(self):
        """动态创建界面上的所有控件 (已移除小按钮)"""
        column_layouts = [QVBoxLayout() for _ in categories]
        for layout in column_layouts:
            layout.setAlignment(Qt.AlignTop) # 让内容从顶部开始排列
            self.main_layout.addLayout(layout)

        for index, category_group in enumerate(categories):
            for sector in category_group:
                if sector in self.config:
                    keywords = self.config[sector]

                    # —— 在这里加一个空检查 —— 
                    # 如果 keywords 是 dict 或 list，且长度为 0，就跳过
                    if (isinstance(keywords, dict) and not keywords) or \
                       (isinstance(keywords, list) and not keywords):
                        continue

                    # 下面才是原来的代码：
                    display_sector_name = self.display_name_map.get(sector, sector)
                    group_box = DraggableGroupBox(display_sector_name, sector)
                    group_box.setLayout(QVBoxLayout())
                    column_layouts[index].addWidget(group_box)

                    items = limit_items(
                        keywords.items() if isinstance(keywords, dict)
                                         else [(kw, kw) for kw in keywords],
                        sector
                    )

                    # 再一次防护：如果 limit 之后还是空，也直接跳过
                    if not items:
                        continue
                    
                    # 2. 使用获取到的显示名称来构建最终的标题文本。
                    total = len(keywords)
                    shown = len(items)
                    title = (f"{display_sector_name} ({shown}/{total})"
                             if shown != total else display_sector_name)
                    group_box.setTitle(title)

                    for keyword, translation in items:
                        button_container = QWidget()
                        row_layout = QHBoxLayout(button_container)
                        row_layout.setContentsMargins(0, 0, 0, 0)
                        row_layout.setSpacing(5)

                        # 创建主按钮
                        button_text = translation if translation else keyword
                        button_text += f" {compare_data.get(keyword, '')}"
                        button = SymbolButton(button_text, keyword, sector)
                        button.setObjectName(self.get_button_style_name(keyword))
                        button.setCursor(QCursor(Qt.PointingHandCursor))
                        button.clicked.connect(lambda _, k=keyword: self.on_keyword_selected_chart(k))
                        
                        # 设置 Tooltip：先取 tags，再查最新财报日期，组合成一个 HTML
                        tags_info = get_tags_for_symbol(keyword)
                        if isinstance(tags_info, list):
                            tags_info = ", ".join(tags_info)
                        latest_date = fetch_latest_earning_date(keyword)
                        tip_html = (
                            "<div style='font-size:20px;"
                            "background-color:lightyellow; color:black;'>"
                            f"{tags_info}"
                            f"<br>最新财报: {latest_date}"
                            "</div>"
                        )
                        button.setToolTip(tip_html)

                        # 设置右键菜单
                        button.setContextMenuPolicy(Qt.CustomContextMenu)
                        button.customContextMenuRequested.connect(
                            # 收到局部坐标 pos，把它映射为全局坐标，再连同 keyword, group 一并传给 show_context_menu
                            lambda local_pos, btn=button, k=keyword, g=sector:
                                self.show_context_menu(btn.mapToGlobal(local_pos), k, g)
                        )
                        
                        row_layout.addWidget(button)
                        group_box.layout().addWidget(button_container)

    # --------------------------------------------------
    # 新：接收三个参数：global_pos、keyword、group
    # --------------------------------------------------
    def show_context_menu(self, global_pos, keyword, group):
        # 给 menu 指定 parent，防止被垃圾回收
        menu = QMenu(self)

        # --- 通用“移动”子菜单 ---
        move_menu = menu.addMenu("移动")
        for tgt in ("Qualified", "Watching", "Next Week", "2 Weeks", "3 Weeks"):
            act = move_menu.addAction(f"到 {tgt}")
            act.setEnabled(group != tgt)
            # 用 lambda 搭桥：三个参数 keyword, group (当前组), tgt (目标组)
            act.triggered.connect(
                lambda _, k=keyword, src=group, dst=tgt: 
                    self.move_item(k, src, dst)
            )

        # 2) 其他顶层菜单项
        menu.addSeparator()
        menu.addAction("删除",          lambda: self.delete_item(keyword, group))
        menu.addAction("编辑 Tags",    lambda: execute_external_script('tags', keyword, group, self))
        menu.addSeparator()
        menu.addAction("改名",          lambda: self.rename_item(keyword, group))
        menu.addAction("编辑 Earing DB", lambda: execute_external_script('editor_earning', keyword))
        menu.addSeparator()
        menu.addAction("添加新事件",    lambda: execute_external_script('event_input', keyword, group, self))
        menu.addAction("编辑事件",      lambda: execute_external_script('event_editor', keyword, group, self))
        menu.addSeparator()
        menu.addAction("在富途中搜索",   lambda: execute_external_script('futu', keyword))
        menu.addAction("查询 DB...",    lambda: self.on_keyword_selected(keyword))
        menu.addAction("Kimi检索财报",  lambda: execute_external_script('kimi', keyword))
        menu.addAction("添加到 Earning", lambda: execute_external_script('earning', keyword))
        menu.addSeparator()
        menu.addAction("找相似",        lambda: execute_external_script('similar', keyword))
        menu.addSeparator()
        menu.addAction("加入黑名单",     lambda: execute_external_script('blacklist', keyword, group, self))

        # 3) 显示菜单
        menu.exec_(global_pos)

    def refresh_selection_window(self):
        """重新加载配置并刷新UI"""
        global config
        config = load_json(CONFIG_PATH)
        self.config = config
        
        # 清空现有布局
        while self.main_layout.count():
            layout_item = self.main_layout.takeAt(0)
            if layout_item.widget():
                layout_item.widget().deleteLater()
            elif layout_item.layout():
                # 递归清空子布局
                self.clear_layout(layout_item.layout())

        self.populate_widgets()

    def clear_layout(self, layout):
        """辅助函数，用于递归删除布局中的所有控件"""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout())

    # ### 修改 ###: 更新此方法以使用新的数据库查询函数
    def on_keyword_selected_chart(self, value):
        # —— 在真正 plot 之前，先 reload 一下外部可能改动过的文件 —— 
        global json_data, compare_data
        try:
            json_data    = load_json(DESCRIPTION_PATH)
        except Exception as e:
            print("重新加载 description/compare 数据出错:", e)
        sector = next((s for s, names in sector_data.items() if value in names), None)
        if sector:
            self.symbol_manager.set_current_symbol(value)
            compare_value = compare_data.get(value, "N/A")
            
            # 从数据库获取 shares, marketcap, pe, pb
            shares_val, marketcap_val, pe_val, pb_val = fetch_mnspp_data_from_db(DB_PATH, value)
            
            # 调用绘图函数，注意参数的变化：
            # - shares_value 现在是一个包含 (shares, pb) 的元组
            plot_financial_data(
                DB_PATH, sector, value, compare_value, (shares_val, pb_val),
                marketcap_val, pe_val, json_data, '1Y', False
            )
            # <--- 第2处修改：在绘图后让主窗口重新获得焦点，以便响应键盘事件 ---
            self.setFocus()

    def on_keyword_selected(self, value):
        sector = next((s for s, names in sector_data.items() if value in names), None)
        if sector:
            condition = f"name = '{value}'"
            result = query_database(DB_PATH, sector, condition)
            self.create_db_view_window(result)
            
    def create_db_view_window(self, content):
        """使用 QDialog 创建一个新的窗口来显示数据库查询结果"""
        dialog = QDialog(self)
        dialog.setWindowTitle("数据库查询结果")
        dialog.setGeometry(200, 200, 900, 600)
        
        layout = QVBoxLayout(dialog)
        text_area = QTextEdit()
        text_area.setFont(QFont("Courier", 14)) # Courier是等宽字体
        text_area.setPlainText(content)
        text_area.setReadOnly(True)
        
        layout.addWidget(text_area)
        dialog.setLayout(layout)
        dialog.exec_() # 使用 exec_() 以模态方式显示

    def handle_arrow_key(self, direction):
        if direction == 'down':
            symbol = self.symbol_manager.next_symbol()
        else:
            symbol = self.symbol_manager.previous_symbol()
        if symbol:
            self.on_keyword_selected_chart(symbol)

    def keyPressEvent(self, event):
        """重写键盘事件处理器"""
        key = event.key()
        if key == Qt.Key_Escape:
            self.close()
        elif key == Qt.Key_Down:
            self.handle_arrow_key('down')
        elif key == Qt.Key_Up:
            self.handle_arrow_key('up')
        else:
            # 对于其他按键，调用父类的实现，以保留默认行为（例如，如果需要的话）
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """关闭窗口时重置 symbol_manager"""
        self.symbol_manager.reset()
        QApplication.quit()

    # --- 功能函数，现在是类的方法 ---
    def delete_item(self, keyword, group):
        if group in self.config and keyword in self.config[group]:
            if isinstance(self.config[group], dict):
                del self.config[group][keyword]
            else:
                self.config[group].remove(keyword)
            with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
                json.dump(self.config, file, ensure_ascii=False, indent=4)
            print(f"已成功删除 {keyword} from {group}")
            self.refresh_selection_window()
        else:
            print(f"{keyword} 不存在于 {group} 中")

    def rename_item(self, keyword, group):
        new_name, ok = QInputDialog.getText(self, "重命名", f"请为 {keyword} 输入新名称：")
        if ok and new_name.strip():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
                config_data = json.load(file)
            if group in config_data and keyword in config_data[group]:
                config_data[group][keyword] = new_name.strip()
                with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
                    json.dump(config_data, file, ensure_ascii=False, indent=4)
                print(f"已将 {keyword} 的描述更新为: {new_name}")
                self.refresh_selection_window()
            else:
                print(f"未找到 {keyword} 在 {group} 中")
        else:
            print("重命名被取消或输入为空。")

    def move_item(self, keyword, source_group, target_group):
        """
        通用：将 keyword 从 source_group 移到 target_group。
        config 中允许 list<str> 或 dict<str,any> 两种类型。
        """
        cfg = self.config

        # 1) 检查源分组
        if source_group not in cfg:
            print(f"[错误] 源分组 '{source_group}' 不存在。")
            return

        # 2) 根据源分组类型取出并删除 item_value
        if isinstance(cfg[source_group], dict):
            if keyword not in cfg[source_group]:
                print(f"[错误] 在 {source_group} 中找不到 {keyword}")
                return
            item_value = cfg[source_group].pop(keyword)
        elif isinstance(cfg[source_group], list):
            if keyword not in cfg[source_group]:
                print(f"[错误] 在 {source_group} 中找不到 {keyword}")
                return
            cfg[source_group].remove(keyword)
            item_value = keyword
        else:
            print(f"[错误] 源分组 '{source_group}' 类型不支持：{type(cfg[source_group])}")
            return

        # 3) 确保目标分组存在，类型和源分组一致或默认 dict
        if target_group not in cfg:
            # 如果源是 dict，则新建 dict，否则新建 list
            cfg[target_group] = {} if isinstance(item_value, (dict,)) or isinstance(cfg[source_group], dict) else []
        elif not isinstance(cfg[target_group], dict) and not isinstance(cfg[target_group], list):
            print(f"[错误] 目标分组 '{target_group}' 类型不支持：{type(cfg[target_group])}")
            return

        # 4) 插入到目标分组
        if isinstance(cfg[target_group], dict):
            cfg[target_group][keyword] = item_value
        else:
            cfg[target_group].append(keyword)

        # 5) 保存文件 & 刷新
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            print(f"已将 {keyword} 从 {source_group} 移动到 {target_group}")
            self.refresh_selection_window()
        except Exception as e:
            print(f"[错误] 保存配置失败：{e}")

if __name__ == '__main__':
    # Load data
    keyword_colors = load_json(COLORS_PATH)
    config = load_json(CONFIG_PATH)
    json_data = load_json(DESCRIPTION_PATH)
    sector_data = load_json(SECTORS_ALL_PATH)
    compare_data = load_text_data(COMPARE_DATA_PATH)
    # ### 删除 ###: 移除了对 shares 和 marketcap_pe_data 的加载
    
    symbol_manager = SymbolManager(config, categories)

    # Create and run PyQt5 application
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.showMaximized()
    sys.exit(app.exec_())