import os
import sys
import json
import datetime
import sqlite3
import subprocess
import re
from collections import OrderedDict
import holidays

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- PyQt6 导入 ---
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QScrollArea, QTextEdit, QDialog,
    QInputDialog, QMenu, QFrame, QLabel, QLineEdit, QMessageBox
)
# 注意: PyQt6 的枚举通常需要全限定名 (Scoped Enums)
from PyQt6.QtCore import Qt, QMimeData, QPoint, QEvent, QTimer, QSize
from PyQt6.QtGui import QFont, QCursor, QDrag, QPainter, QColor, QPen

sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))

# --- 修改: 增加导入 get_options_metrics ---
from Chart_input import plot_financial_data, get_options_metrics

# --- 文件路径配置 ---
CONFIG_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_panel.json")
COLORS_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Colors.json")
DESCRIPTION_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
SECTORS_ALL_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
COMPARE_DATA_PATH = os.path.join(BASE_CODING_DIR, "News", "backup", "Compare_All.txt")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
BLACKLIST_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Blacklist.json")
EARNING_HISTORY_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Earning_History.json")

DISPLAY_LIMITS = {
    'default': 'all',  # 默认显示全部
    "Bonds": 3,
}

categories = [
    ['Must', 'Today', 'PE_Volume_backup', 'PE_Volume_up_backup',
     'PE_Deeper_backup', 'PE_Deep_backup',
     'PE_W_backup', 'OverSell_W_backup'],
    ['PE_valid_backup', 'PE_invalid_backup', 'Strategy12_backup', 'Strategy34_backup', 'Short_backup', 'Short_W_backup'],
    ['Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Technology', 'Energy', 'Industrials',
     'Consumer_Defensive', 'Communication_Services', 'Financial_Services', 'Healthcare', 'Utilities'],
    ['ETFs', 'Bonds', 'Crypto', 'Indices', 'Currencies'],
    ['Economics', 'Commodities'],
]

compare_data = {}
config = {}
keyword_colors = {}
sector_data = {}
json_data = {}
# --- 新增: 全局变量用于存储 Earning History 数据 ---
earning_history = {}

# --- 新增: 交易日计算工具类 ---
class TradingDateHelper:
    """
    使用 holidays 库自动计算美股(NYSE)交易日。
    """
    @staticmethod
    def get_last_trading_date(base_date=None):
        """
        获取相对于 base_date (默认今天) 的最近一个有效交易日。
        返回类型: datetime.date 对象
        """
        if base_date is None:
            base_date = datetime.date.today()
        
        # 获取 NYSE 专属日历 (自动处理周末补休规则)
        nyse_holidays = holidays.NYSE()
        
        # 从"昨天"开始找 (因为今天是盘中或还没开盘，通常看的是昨收)
        target_date = base_date - datetime.timedelta(days=1)
        
        while True:
            # 1. 检查周末 (5=Sat, 6=Sun)
            if target_date.weekday() >= 5:
                target_date -= datetime.timedelta(days=1)
                continue
            
            # 2. 检查 NYSE 节假日 (库会自动处理观察日规则)
            # 例如：如果独立日是周六，库会自动把周五标记为 Holiday
            if target_date in nyse_holidays:
                target_date -= datetime.timedelta(days=1)
                continue
                
            # 既不是周末也不是节假日，就是它了
            return target_date

# --- 控件类定义 ---

# --- 新增: 用于绘制左侧竖排横杠的控件 ---
class BarIndicatorWidget(QWidget):
    def __init__(self, count=0, parent=None):
        super().__init__(parent)
        self._count = count
        # 设置一个固定的宽度，让所有指示器对齐
        self.setFixedWidth(12)

    def setCount(self, count):
        self._count = count
        self.update() # 触发重绘

    def paintEvent(self, event):
        if self._count <= 0:
            return  # 如果计数为0，则不绘制任何内容

        painter = QPainter(self)
        # PyQt6: 枚举变化 QPainter.RenderHint.Antialiasing
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- 横杠属性 ---
        bar_color = QColor("#FFA500")  # 橙色，比较醒目
        bar_height = 2                 # 每根横杠的高度 (即画笔粗细)
        bar_width = 8                  # 每根横杠的宽度
        spacing = 2                    # 横杠之间的垂直间距
        
        # 水平居中绘制
        start_x = (self.width() - bar_width) // 2

        # 计算所有横杠加间距的总高度，以便在控件内垂直居中
        total_content_height = self._count * bar_height + (self._count - 1) * spacing
        if total_content_height < 0: total_content_height = 0
        
        start_y = (self.height() - total_content_height) // 2

        pen = QPen(bar_color, bar_height)
        # PyQt6: Qt.PenCapStyle.FlatCap
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)

        # 循环绘制每一根横杠
        for i in range(self._count):
            # 计算当前横杠的Y轴位置
            y_pos = start_y + i * (bar_height + spacing)
            # 我们画一条线，线的粗细由画笔宽度决定
            painter.drawLine(start_x, y_pos, start_x + bar_width, y_pos)

    def sizeHint(self):
        # 为布局管理器提供一个合适的尺寸建议
        bar_height = 2
        spacing = 2
        height = self._count * (bar_height + spacing)
        return QSize(12, height)


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

        # PyQt6: ev.pos() 依然可用，但建议用 ev.position().toPoint()
        y = ev.position().toPoint().y()
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
            
            y = ev.position().toPoint().y()
            dst = len(widgets)
            for i, w in enumerate(widgets):
                if y < w.geometry().center().y():
                    dst = i
                    break

        self._clear_placeholder()
        ev.acceptProposedAction()

        # 通知 MainWindow
        mw = self.window()
        # 注意: self.window() 在 PyQt6 返回可能是 None，虽然通常都有
        if mw:
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


# --- 修改: 移除 SymbolButton 的角标逻辑，回归简单按钮 ---
class SymbolButton(QPushButton):
    # 移除 __init__ 中的 badge_count 参数
    def __init__(self, text, symbol, group, parent=None):
        super().__init__(text, parent)
        self._symbol = symbol
        self._group  = group
        self._drag_start = QPoint()

    def mousePressEvent(self, ev):
        # PyQt6: Qt.MouseButton.LeftButton
        if ev.button() == Qt.MouseButton.LeftButton:
            mods = ev.modifiers()
            # PyQt6: Qt.KeyboardModifier.AltModifier
            if mods & Qt.KeyboardModifier.AltModifier:
                execute_external_script('similar', self._symbol)
                return
            # PyQt6: Qt.KeyboardModifier.ShiftModifier
            if mods & Qt.KeyboardModifier.ShiftModifier:
                execute_external_script('futu', self._symbol)
                return
            self._drag_start = ev.position().toPoint()
        
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        # PyQt6: ev.buttons() & Qt.MouseButton.LeftButton
        if not (ev.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(ev)

        if (ev.position().toPoint() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData('application/x-symbol', f"{self._symbol}|{self._group}".encode())
        drag.setMimeData(mime)

        # 用控件截图作拖拽图标
        pm = self.grab()
        drag.setPixmap(pm)
        # hotSpot 
        drag.setHotSpot(ev.position().toPoint() - self.rect().topLeft()) 

        # PyQt6: exec 替代 exec_, 且使用 DropAction 枚举
        drag.exec(Qt.DropAction.MoveAction)


# --- 辅助函数 ---

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

def fetch_mnspp_data_from_db(db_path, symbol):
    """
    根据股票代码从MNSPP表中查询 shares, marketcap, pe_ratio, pb。
    如果未找到，则返回默认值。
    """
    with sqlite3.connect(db_path, timeout=60.0) as conn:
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
        with sqlite3.connect(DB_PATH, timeout=60.0) as conn:
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
    with sqlite3.connect(db_path, timeout=60.0) as conn:
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

def get_color_decision_data(db_path, sector_data, symbol):
    """
    获取决定按钮颜色所需的所有数据，逻辑完全移植自 b.py。
    1. 从 Earning 表获取最近两次财报日期和最新的 price。
    2. 从 sector 表获取这两天的收盘价。
    3. 比较收盘价得出趋势。
    4. 如果最新一期财报的日期不是在当前系统日期往前推一个半月之内的话，则该symbol显示为白色。
    5. 如果某个symbol只有一个财报日期，那么即使他的财报日期是在1个半月之内的，也仍然显示为白色。

    返回: (latest_earning_price, stock_price_trend, latest_earning_date)
          - stock_price_trend: 'rising', 'falling', 'single', 或 None
            'single' 表示只有一条财报记录，此时仅根据 earning price 正负着色。
    """
    try:
        # 步骤 1: 获取最近两次财报信息
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT date, price FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 2",
                (symbol,)
            )
            earning_rows = cursor.fetchall()
        
        if not earning_rows:
            return None, None, None # 没有财报记录

        latest_earning_date_str, latest_earning_price_str = earning_rows[0]
        latest_earning_date = datetime.datetime.strptime(latest_earning_date_str, "%Y-%m-%d").date()
        latest_earning_price = float(latest_earning_price_str) if latest_earning_price_str is not None else 0.0

        # --- 规则：如果最新财报在75天前，则强制为白色 ---
        days_diff = (datetime.date.today() - latest_earning_date).days
        if days_diff > 75:
            # 返回None趋势，使调用处逻辑判定为白色
            return latest_earning_price, None, latest_earning_date

        # --- 规则：如果只有一条财报记录，使用 'single' 模式 ---
        if len(earning_rows) < 2:
            return latest_earning_price, 'single', latest_earning_date

        # 存在至少两条财报记录，继续计算趋势
        previous_earning_date_str, _ = earning_rows[1]
        previous_earning_date = datetime.datetime.strptime(previous_earning_date_str, "%Y-%m-%d").date()

        # 步骤 2: 查找 sector 表名
        sector_table = next((s for s, names in sector_data.items() if symbol in names), None)
        if not sector_table:
            # 找不到板块，也无法比较
            return latest_earning_price, None, latest_earning_date

        # 步骤 3: 获取两个日期的收盘价
        with sqlite3.connect(db_path, timeout=60.0) as conn:
            cursor = conn.cursor()
            
            # 获取最新财报日的收盘价
            cursor.execute(
                f'SELECT price FROM "{sector_table}" WHERE name = ? AND date = ?',
                (symbol, latest_earning_date.isoformat())
            )
            latest_stock_price_row = cursor.fetchone()
            
            # 获取前一次财报日的收盘价
            cursor.execute(
                f'SELECT price FROM "{sector_table}" WHERE name = ? AND date = ?',
                (symbol, previous_earning_date.isoformat())
            )
            previous_stock_price_row = cursor.fetchone()

        if not latest_stock_price_row or not previous_stock_price_row:
            # 缺少任一天的股价数据
            return latest_earning_price, None, latest_earning_date

        latest_stock_price = float(latest_stock_price_row[0])
        previous_stock_price = float(previous_stock_price_row[0])
        
        # 步骤 4: 判断趋势
        trend = 'rising' if latest_stock_price > previous_stock_price else 'falling'
        
        return latest_earning_price, trend, latest_earning_date

    except Exception as e:
        print(f"[颜色决策数据获取错误] {symbol}: {e}")
        return None, None, None

def execute_external_script(script_type, keyword, group=None, main_window=None):
    python_path = sys.executable
    script_configs = {
        'similar': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Query', 'Search_Similar_Tag.py'),
        'tags': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Tags.py'),
        'editor_earning': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Earning_DB.py'),
        'earning': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Earning.py'),
        'event_input': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Insert_Events.py'),
        'event_editor': os.path.join(BASE_CODING_DIR, 'Financial_System', 'Operations', 'Editor_Events.py'),
        'futu': os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Stock_CheckFutu.scpt'),
        'doubao': os.path.join(BASE_CODING_DIR, 'ScriptEditor', 'Check_Earning.scpt')
    }

    try:
        # 1) 对于 “编辑 Tags”、“新增事件”、“编辑事件” ---- 阻塞调用，跑完后刷新 UI
        if script_type in ('tags', 'event_input', 'event_editor'):
            if script_type in ('futu', 'doubao'):
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
            if script_type in ['futu', 'doubao']:
                subprocess.Popen(['osascript', script_configs[script_type], keyword])
            else:
                python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
                subprocess.Popen([python_path, script_configs[script_type], keyword])

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

# ### 新增函数 ###: 用于过滤正收益的Symbol并保存配置
def filter_positive_symbols(config_dict, compare_dict, config_file_path):
    """
    遍历指定的板块，检查 Compare_All.txt 中的数据。
    如果百分比为正数，则从配置中删除该 Symbol，并更新文件。
    """
    target_sectors = [
        'Real_Estate', 'Technology', 'Energy', 'Industrials',
        'Consumer_Defensive', 'Communication_Services', 'Basic_Materials',
        'Financial_Services', 'Healthcare', 'Utilities', 'Consumer_Cyclical'
    ]
    
    modified = False
    
    for sector in target_sectors:
        if sector not in config_dict:
            continue
            
        # 获取当前板块的 Symbol 列表（支持 dict 或 list）
        current_group = config_dict[sector]
        symbols_to_remove = []
        
        # 确定迭代对象
        iterable_symbols = list(current_group.keys()) if isinstance(current_group, dict) else list(current_group)
        
        for symbol in iterable_symbols:
            # 检查 Symbol 是否在 compare_data 中
            if symbol in compare_dict:
                # 获取 compare 文本 (例如: "3.90%*+" 或 "-0.94%")
                # 注意：如果 load_text_data 返回的是 tuple，取第一个元素或转为字符串
                raw_value = compare_dict[symbol]
                if isinstance(raw_value, tuple):
                    raw_value = str(raw_value[0])
                else:
                    raw_value = str(raw_value)
                
                # 使用正则提取百分比数值
                match = re.search(r"([-+]?\d+(?:\.\d+)?)%", raw_value)
                if match:
                    try:
                        percentage = float(match.group(1))
                        # 如果百分比大于 0，标记为删除
                        if percentage > 0:
                            symbols_to_remove.append(symbol)
                            print(f"[自动清理] {symbol} ({sector}) 涨幅 {percentage}% > 0，已移除。")
                    except ValueError:
                        pass
        
        # 执行删除操作
        if symbols_to_remove:
            modified = True
            for s in symbols_to_remove:
                if isinstance(current_group, dict):
                    del current_group[s]
                else:
                    current_group.remove(s)
    
    # 如果有修改，写回文件
    if modified:
        try:
            with open(config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, ensure_ascii=False, indent=4)
            print("Sectors_panel.json 已更新：移除了正收益的 Symbol。")
        except Exception as e:
            print(f"[错误] 更新配置文件失败: {e}")

# --- 主窗口 ---

class MainWindow(QMainWindow):
    # --- 修改: __init__ 接受 Earning History 数据 ---
    def __init__(self, earning_history_data):
        super().__init__()
        # 将全局变量作为实例变量
        global config
        self.config = config
        # --- 新增: 存储 Earning History 数据 ---
        self.earning_history = earning_history_data
        
        ### <<< 修改: 将 highlighted_info 改为 highlighted_buttons 列表
        self.highlighted_buttons = []

        # <--- 新增: 用于方向键导航的变量
        self.ordered_symbols_on_screen = []
        self.current_symbol_index = -1
        # <--- 新增: 用于存储每个 Symbol 对应的分组显示名称
        self.ordered_groups_on_screen = [] 

        # 创建一个从内部长名称到UI显示短名称的映射字典
        self.display_name_map = {
            'Communication_Services': 'Communication',
            'Consumer_Defensive': 'Defensive',
            'Consumer_Cyclical': 'Cyclical',
            'Basic_Materials': 'Materials',
            'Financial_Services': 'Financial',
            'Strategy34': '策略 3、3.5、4',
            'Strategy12': '策略 1、2、2.5'
        }
        
        self.init_ui()

    def handle_chart_callback(self, deleted_symbol, action):
        """
        当 b.py 发生特定动作（如删除、上一页、下一页）时被调用
        """
        # --- 情况 1: 删除操作 ---
        if action == 'deleted':
            # 获取当前索引
            current_idx = self.current_symbol_index
            
            # === 修改逻辑 START ===
            # 1. 记录“旧列表”中，当前索引之前有多少个 deleted_symbol
            old_preceding_count = 0
            if 0 <= current_idx < len(self.ordered_symbols_on_screen):
                # 切片取出当前位置之前的所有元素
                preceding_items = self.ordered_symbols_on_screen[:current_idx]
                old_preceding_count = preceding_items.count(deleted_symbol)
            
            print(f"检测到 {deleted_symbol} 删除。旧索引: {current_idx}, 前方旧副本数: {old_preceding_count}")

            # 2. 将 current_idx 和 old_preceding_count 一起传给 open_next_symbol
            # 我们推迟到刷新后再计算到底需要减多少
            QTimer.singleShot(100, lambda: self.open_next_symbol(deleted_symbol, current_idx, old_preceding_count))
            # === 修改逻辑 END ===
        
        # --- 情况 2: 导航操作 (保持不变) ---
        elif action in ('next', 'prev'):
            # 立即保存当前索引，防止窗口切换时的干扰
            current_idx = self.current_symbol_index
            
            # 使用 QTimer 稍微延迟，确保旧窗口完全关闭，避免视觉冲突
            QTimer.singleShot(50, lambda: self.navigate_to_adjacent_symbol(action, current_idx))


    # >>> 新增方法: 处理左右跳转 >>>
    def navigate_to_adjacent_symbol(self, direction, current_idx):
        """
        根据方向打开上一个或下一个 Symbol。
        因为 ordered_symbols_on_screen 包含所有分组，所以跨组跳转会自动完成。
        """
        total_count = len(self.ordered_symbols_on_screen)
        if total_count == 0:
            return

        new_index = current_idx
        
        if direction == 'next':
            new_index += 1
        elif direction == 'prev':
            new_index -= 1
            
        # 边界检查
        # 如果到了最后一个，按右键是否要循环回第一个？通常为了防呆，停在最后即可，或者循环。
        # 这里写成循环模式 (Cycle)，如果你不想循环，可以用 if 0 <= new_index < total_count: 判断
        
        # 循环模式逻辑：
        if new_index >= total_count:
            new_index = 0 # 到底了，回到第一个
            print("已到达列表末尾，循环回到开头。")
        elif new_index < 0:
            new_index = total_count - 1 # 到头了，去最后一个
            print("已到达列表开头，循环跳到末尾。")
            
        # 取出新的 Symbol
        next_symbol = self.ordered_symbols_on_screen[new_index]
        print(f"导航跳转: {next_symbol} (Index: {new_index})")
        
        # 打开图表 (传入新的精确索引)
        self.on_keyword_selected_chart(next_symbol, btn_index=new_index)
    
    # === 修改方法的参数，增加 old_preceding_count ===
    def open_next_symbol(self, deleted_symbol, old_index, old_preceding_count):
        """
        根据删除前的信息和删除后的新列表，计算正确的跳转位置。
        """
        # 1. 刷新界面 (ordered_symbols_on_screen 更新为新列表)
        self.refresh_selection_window()
        
        # === 核心修复逻辑 START ===
        # 2. 在“新列表”中，计算同样的 old_index 之前，现在有多少个 deleted_symbol
        new_preceding_count = 0
        
        # 获取新列表
        current_list = self.ordered_symbols_on_screen
        
        # 如果 old_index 超过了新列表长度，切片会自动截止到末尾，不会报错
        preceding_items_new = current_list[:old_index]
        new_preceding_count = preceding_items_new.count(deleted_symbol)
        
        # 3. 计算“前方实际被删除的数量”
        # offset = 旧的前方数量 - 新的前方数量
        # 正数：说明前方少了元素（删除了前面的副本），索引需要前移
        # 负数：说明前方多了元素（比如移动到了前面的分组），索引需要后移
        offset = old_preceding_count - new_preceding_count
        # if offset < 0: offset = 0 # 防御性编程
        
        # 4. 得出最终目标索引
        # 如果 offset 是 -1 (前方多了1个)，则 target = old - (-1) = old + 1 (向后修补1位)
        target_index = old_index - offset
        
        print(f"刷新完毕。前方新副本数: {new_preceding_count}。偏移量: {offset}。最终索引: {target_index}")
        # === 核心修复逻辑 END ===

        # 5. 打开目标索引 (后续逻辑保持原有框架，但使用 target_index)
        if 0 <= target_index < len(self.ordered_symbols_on_screen):
            # 取出这个位置上的新 Symbol
            next_symbol = self.ordered_symbols_on_screen[target_index]
            
            print(f"自动打开下一个: {next_symbol} (Target Index: {target_index})")
            
            # 打开它
            self.on_keyword_selected_chart(next_symbol, btn_index=target_index)
            
        else:
            # 处理边界情况：如果你删的是列表里最后一个元素
            if self.ordered_symbols_on_screen:
                print("已删除最后一个元素，选中新的列表末尾。")
                new_last_index = len(self.ordered_symbols_on_screen) - 1
                next_symbol = self.ordered_symbols_on_screen[new_last_index]
                self.on_keyword_selected_chart(next_symbol, btn_index=new_last_index)
            else:
                print("列表已空。")

    
    # --- 新增: 计算角标数字的核心逻辑 ---
    def get_consecutive_day_count(self, symbol, group):
        """ 
        根据规则计算symbol连续出现的天数。
        修改版: 
        1. 建立了 UI分组名 到 History键名 的映射。
        2. 兼容模式: 同时查找对应的精确分组(如 PE_W) 和 旧的通用分组(no_season)。
        """
        
        # --- 1. 定义映射关系: UI上的组名 -> Earning_History.json 中的 Key ---
        # 只要你在第一个脚本里生成了新的 Key，这里就需要对应上
        # 左边是 UI 上的 group 参数，右边是 History json 里的 key
        group_mapping = {
            # UI 分组名 : JSON 键名
            "PE_valid_backup": "PE_valid",
            "PE_invalid_backup": "PE_invalid",
            "PE_W_backup": "PE_W",
            "Short_backup": "Short",
            "Short_W_backup": "Short_W",
            "PE_Deep_backup": "PE_Deep",
            "PE_Deeper_backup": "PE_Deeper",
            "PE_Volume_backup": "PE_Volume",
            "PE_Volume_up_backup": "PE_Volume_up",
            "OverSell_W_backup": "OverSell_W",
            
            # 兼容不带 _backup 后缀的情况 (如果有)
            "PE_valid": "PE_valid",
            "PE_invalid": "PE_invalid",
            "PE_W": "PE_W",
            "PE_Deep": "PE_Deep",
            "PE_Volume": "PE_Volume",
            "PE_Volume_up": "PE_Volume_up",
            "OverSell_W": "OverSell_W"
        }

        # --- 2. 确定需要检查的历史数据 Key 列表 ---
        keys_to_check = []

        if group in group_mapping:
            # 逻辑: 优先查具体的分组(如 PE_W)，但也查 no_season (为了兼容以前的历史数据)
            target_key = group_mapping[group]
            keys_to_check = [target_key, 'no_season']
        
        elif group in {"Strategy12_backup", "Strategy34_backup", "Strategy12", "Strategy34"}:
            # 情况 B: 是 Season 策略组 -> 查 'season'
            keys_to_check = ['season']
        
        elif group in {"Must", "Today"}:
            # 情况 C: 是汇总组 -> 查所有已知的具体 Key (不再查 no_season)
            keys_to_check = [
                'season', 'no_season',
                'PE_valid', 'PE_invalid', 
                'PE_W', 'PE_Deep', 'OverSell_W'
            ]
        else:
            # 默认情况 (比如其他没在映射里的组)
            keys_to_check = ['no_season']

        # --- 3. 开始回溯计数 ---
        count = 0
        day_offset = 1
        today = datetime.date.today()
        
        # 使用 holidays.NYSE() 获取美股假期
        market_holidays = holidays.NYSE() 
        
        while day_offset <= 365:
            current_date = today - datetime.timedelta(days=day_offset)
            date_str = current_date.strftime('%Y-%m-%d')
            
            found_on_this_date = False
            
            # 遍历所有相关的 Key 查找 symbol
            for key in keys_to_check:
                # 获取该 Key 下的历史数据
                hist_data = self.earning_history.get(key, {})
                # 检查 symbol 是否存在于当天的列表中
                if symbol in hist_data.get(date_str, []):
                    found_on_this_date = True
                    break # 只要在任意一个相关组里找到了，就视为当天存在，跳出内层循环
            
            if found_on_this_date:
                # 如果找到了，计数器加一，继续检查前一天
                count += 1
                day_offset += 1
            else:
                # 判断周末 (5=周六, 6=周日) 或 节假日
                is_weekend = current_date.weekday() >= 5
                is_holiday = current_date in market_holidays
                
                # 如果是周末 或者 是节假日，则算作“非交易日”，不应中断连续性
                if is_weekend or is_holiday:
                    day_offset += 1
                else:
                    # 是工作日 且 不是节假日，但没有数据 -> 连续性中断
                    break
                    
        return count

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                # 从后台回到前台（窗口被激活）
                self.refresh_selection_window()
                
    def init_ui(self):
        self.setWindowTitle("选择查询关键字")
        
        # <--- 第1处修改：设置主窗口的焦点策略，使其能接收键盘事件 ---
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
        """
        创建并应用 QSS 样式表。
        - 所有 QPushButton 统一了字体、内边距、圆角和边框
        - 每个按钮根据 objectName 只需定义背景色和前景色，以及 hover 效果
        - GroupBox 保持原有视觉增强
        """
        # 1. 定义各按钮的背景色和文字色（只在这里集中配置）
    #     button_styles = {
    #         "Cyan":   ("#008B8B", "white"),
    #         "Blue":   ("#1E3A8A", "white"),
    #         "Purple": ("#9370DB", "black"),
    #         "Green":  ("#276E47", "white"),
    #         "White":  ("#A9A9A9", "black"),
    #         "Yellow": ("#BDB76B", "black"),
    #         "Orange": ("#CD853F", "black"),
    #         "Red":    ("#912F2F", "#FFFFF0"),
    #         "Black":  ("#333333", "white"),
    #         "Default":("#666666", "black"),
    #     }

        button_styles = {
            "Cyan": ("#333333", "white"), "Blue": ("#333333", "white"),
            "Purple": ("#333333", "white"), "Green": ("#333333", "white"),
            "White": ("#333333", "white"), "Yellow": ("#333333", "white"),
            "Orange": ("#333333", "white"), "Red": ("#333333", "white"),
            "Black": ("#333333", "white"), "Default": ("#333333", "white")
        }

        # 2. 公共 QPushButton 样式
        qss = """
        QPushButton {
            font-size: 22px;
            padding: 2px;
            border: 1px solid #333;    /* 通用边框 */
            border-radius: 4px;        /* 圆角 */
        }
        """

        # 3. 针对每个 ID（objectName）单独设置背景/文字色和 hover 效果
        for name, (bg, fg) in button_styles.items():
            qss += f"""
            QPushButton#{name} {{
                background-color: {bg};
                color: {fg};
            }}
            QPushButton#{name}:hover {{
                background-color: {self.lighten_color(bg)};
            }}
            """

        # 4. QGroupBox 的“卡片”效果 & 标题样式
        qss += """
        QGroupBox {
            font-size: 20px;
            font-weight: bold;
            border: 1px solid #A9A9A9;
            border-radius: 8px;
            margin-top: 15px;
            padding: 0px;
        }
        QGroupBox::title {
            color: gray;
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 15px;
            padding: 0px 2px;
        }
        """

        # 最后应用
        self.setStyleSheet(qss)

    def clear_group(self, group_name):
        """
        清空 config 中指定分组的所有内容，
        然后写回 CONFIG_PATH 并刷新 UI。
        """
        if group_name not in self.config:
            print(f"[错误] 分组 '{group_name}' 不存在。")
            return
        # 根据原来的类型，清空 dict 或 list
        if isinstance(self.config[group_name], dict):
            self.config[group_name].clear()
        elif isinstance(self.config[group_name], list):
            self.config[group_name].clear()
        else:
            print(f"[错误] 分组 '{group_name}' 类型不支持：{type(self.config[group_name])}")
            return
        # 写回文件并刷新
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            print(f"已清空分组 '{group_name}'")
            self.refresh_selection_window()
        except Exception as e:
            print(f"[错误] 清空分组并保存失败: {e}")

    def reorder_item(self, symbol, src, dst, dst_index):
        cfg = self.config

        # 如果是同一个组内部排序，先算出自己原来的位置
        same_group = (src == dst)
        if same_group:
            if isinstance(cfg[src], dict):
                orig_keys = list(cfg[src].keys())
                orig_index = orig_keys.index(symbol)
            else:
                orig_list = cfg[src]
                orig_index = orig_list.index(symbol)
        # 1) 从 src 拿出 item_value
        if isinstance(cfg[src], dict):
            item = cfg[src].pop(symbol)
        else:
            lst = cfg[src]
            lst.remove(symbol)
            item = symbol

        # —— 新增：在同组内移动时，源位置在目标位置之前，要把索引减 1 —— 
        if same_group and dst_index > orig_index:
            dst_index -= 1

        # 2) 确保 dst 存在，并插入
        if dst not in cfg:
            cfg[dst] = {} if isinstance(cfg.get(src), dict) else []
            
        target = cfg[dst]
        if isinstance(target, dict):
            od = OrderedDict()
            keys = list(target.keys())
            vals = list(target.values())
            keys.insert(dst_index, symbol)
            vals.insert(dst_index, item)
            for k, v in zip(keys, vals):
                od[k] = v
            cfg[dst] = od
        else:
            target.insert(dst_index, symbol)

        # 3) 写回并刷新
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        self.refresh_selection_window()

    def lighten_color(self, color_name, factor=1.1):
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

    # ### 新增方法 START ###: 用于为自定义排序生成排序键
    def get_custom_sort_key(self, keyword, original_index):
        """
        根据 compare_data 中的字符串为 symbol 生成一个排序键。
        排序规则: 1. 数字 (小->大), 2. 标志 ('前'->'后'->'未'), 3. 原始顺序。
        """
        compare_str = compare_data.get(keyword, "")
        
        # 匹配 "数字" + "前/后/未" 的模式
        match = re.search(r'(\d+)(前|后|未)', compare_str)
        if match:
            number = int(match.group(1))
            suffix = match.group(2)
            
            # 将 "前", "后", "未" 映射为整数以便排序
            suffix_map = {'前': 0, '后': 1, '未': 2}
            suffix_val = suffix_map.get(suffix, 3) # 默认值 3
            
            return (number, suffix_val, original_index)
        else:
            # 如果没有匹配到 "数字+标志" 模式，则将它们排在最后，并保持原始顺序
            return (float('inf'), float('inf'), original_index)

    # --- 修改: populate_widgets 方法以添加 BarIndicatorWidget ---
    def populate_widgets(self):
        """动态创建界面上的所有控件"""
        # <--- 新增: 在填充控件前，清空屏幕符号列表
        self.ordered_symbols_on_screen.clear()

        column_layouts = [QVBoxLayout() for _ in categories]
        for layout in column_layouts:
            # PyQt6: Qt.AlignmentFlag.AlignTop
            layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.main_layout.addLayout(layout)

        # ### 修改 ###: 定义需要特殊排序的组
        target_sort_groups = {
            # 原有的板块
            'Basic_Materials','Consumer_Cyclical','Real_Estate','Technology','Energy',
            'Industrials','Consumer_Defensive','Communication_Services','Financial_Services',
            'Healthcare','Utilities',
            
            # 策略分组 (原名)
            'Must','Today','Short','Short_W',
            'PE_valid','PE_invalid','Strategy12','Strategy34',
            'PE_Deep','OverSell_W','PE_W','PE_Deeper','PE_Volume', 'PE_Volume_up',
            
            # 策略分组 (Backup 版本 - 实际上 UI 中正在使用的 key)
            'PE_valid_backup', 'PE_invalid_backup', 
            'Strategy12_backup', 'Strategy34_backup',
            'PE_Deep_backup', 'PE_W_backup', 'PE_Deeper_backup',
            'OverSell_W_backup', 'PE_W_backup', 'PE_Volume_backup', 'PE_Volume_up_backup',
            'Short_backup', 'Short_W_backup'
        }

        # ==========================================================
        # 1. 定义哪些组需要显示左侧的计数条 (把 get_consecutive_day_count 里的组搬过来)
        # ==========================================================
        groups_with_indicators = {
            # no_season_groups
            "PE_valid_backup", "PE_invalid_backup", "PE_W_backup",
            "PE_Deep_backup", "OverSell_W_backup", "PE_Deeper_backup",
            # season_groups
            "Strategy12_backup", "Strategy34_backup",
            # combined_groups
            "Must", "Today", "Short_backup", "Short_W_backup",
            # Volume Sector
            "PE_Volume_backup", "PE_Volume_up_backup",
        }

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

                    # ===== 在这里增加排序 =====
                    items_list = []
                    if isinstance(keywords, dict):
                        items_list = list(keywords.items())
                    else:
                        items_list = [(kw, kw) for kw in keywords]

                    # ### 修改 START ###: 根据分组应用不同的排序逻辑
                    if sector in target_sort_groups:
                        # 对需要特殊排序的组应用新逻辑
                        # 1. 使用 enumerate 获取原始索引
                        indexed_items = list(enumerate(items_list))
                        
                        # 2. 使用新的排序键进行排序
                        #    lambda item: self.get_custom_sort_key(keyword, original_index)
                        #    item[0] is original_index, item[1] is (keyword, translation)
                        #    item[1][0] is keyword
                        indexed_items.sort(key=lambda item: self.get_custom_sort_key(item[1][0], item[0]))
                        
                        # 3. 去掉索引，得到排好序的列表
                        items_list = [item[1] for item in indexed_items]
                    else:
                        # 对其他组，使用旧的排序逻辑
                        if isinstance(keywords, dict):
                            items_list.sort(key=lambda kv: (
                                int(m.group(1)) if (m := re.match(r'\s*(\d+)', kv[1])) else float('inf')
                            ))

                    items = limit_items(items_list, sector)
                    if not items:
                        continue
                    
                    # 2. 使用获取到的显示名称来构建最终的标题文本。
                    total = len(keywords)
                    shown = len(items)
                    title = (f"{display_sector_name} ({shown}/{total})"
                             if shown != total else display_sector_name)
                    group_box.setTitle(title)
                    
                    for keyword, translation in items:
                        # <--- 新增: 将排序后的 keyword 添加到新列表中
                        self.ordered_symbols_on_screen.append(keyword)
                        
                        # <--- 新增: 同步添加当前的分组显示名称 (display_sector_name)
                        self.ordered_groups_on_screen.append(display_sector_name)
                        
                        # <--- 新增: 获取刚才添加进去的这个 keyword 的确切索引
                        current_btn_index = len(self.ordered_symbols_on_screen) - 1 
                        
                        # --- 1. 获取横杠数量 ---
                        bar_count = self.get_consecutive_day_count(keyword, sector)

                        button_container = QWidget()
                        row_layout = QHBoxLayout(button_container)
                        row_layout.setContentsMargins(0, 0, 0, 0)
                        row_layout.setSpacing(5)

                        # ==========================================================
                        # 2. 修改这里：只有当 sector 属于指定组时，才添加指示器控件
                        # ==========================================================
                        if sector in groups_with_indicators:
                            bar_widget = BarIndicatorWidget(count=bar_count)
                            row_layout.addWidget(bar_widget)
                        
                        # 如果不属于这些组，就不添加 bar_widget，这样就没有那 12px 的空档了

                        # --- 3. 创建普通按钮 ---
                        button = SymbolButton(
                            translation if translation else keyword,
                            keyword,
                            sector
                        )
                        
                        button.setObjectName(self.get_button_style_name(keyword))
                        # PyQt6: Qt.CursorShape.PointingHandCursor
                        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        # <--- 关键修改: lambda 中增加 idx 参数，并将 current_btn_index 传进去
                        button.clicked.connect(lambda _, k=keyword, idx=current_btn_index: self.on_keyword_selected_chart(k, idx))

                        # (设置按钮颜色、Tooltip、右键菜单的代码保持不变)
                        earning_price, price_trend, _ = get_color_decision_data(DB_PATH, sector_data, keyword)

                        # 2. 根据 b.py 的规则确定颜色
                        color = 'white'  # 默认颜色
                        if earning_price is not None and price_trend is not None:
                            if price_trend == 'single':
                                if earning_price > 0:
                                    color = 'red'
                                elif earning_price < 0:
                                    color = 'green'
                            else:
                                is_price_positive = earning_price > 0
                                is_trend_rising = price_trend == 'rising'
                                if is_trend_rising and is_price_positive:
                                    color = 'red'
                                elif not is_trend_rising and is_price_positive:
                                    color = '#008B8B'  # Dark Cyan
                                elif is_trend_rising and not is_price_positive:
                                    color = '#912F2F'  # Dark Red
                                elif not is_trend_rising and not is_price_positive:
                                    color = 'green'

                        # 3. 应用字体颜色
                        # 注意：这里会覆盖 QSS 中通过 objectName 设置的 color 属性，但保留 background-color
                        current_style = button.styleSheet()
                        button.setStyleSheet(f"{current_style}; color: {color};")
                        
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
                        
                        # PyQt6: Qt.ContextMenuPolicy.CustomContextMenu
                        button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                        button.customContextMenuRequested.connect(
                            # 收到局部坐标 pos，把它映射为全局坐标，再连同 keyword, group 一并传给 show_context_menu
                            lambda local_pos, btn=button, k=keyword, g=sector:
                                self.show_context_menu(btn.mapToGlobal(local_pos), k, g)
                        )

                        row_layout.addWidget(button)
                        row_layout.addStretch()        # ← 这一行

                        # 2) 解析 compare_data 并生成富文本
                        raw_compare = compare_data.get(keyword, "").strip()
                        formatted_compare_html = ""

                        # --- 修改开始: 针对 target_sort_groups 使用新的显示逻辑 ---
                        if sector in target_sort_groups:
                            parts = []
                            
                            # 1. 处理前缀 (只保留 03后, 02前, 未 等字样)
                            # 如果没有匹配到，前缀部分为空
                            match_prefix = re.search(r"(\d+(?:前|后|未))", raw_compare)
                            if match_prefix:
                                prefix = match_prefix.group(1)
                                # 默认颜色为橙色
                                prefix_color = 'orange'
                                
                                # 尝试从前缀中提取MMDD格式的日期
                                date_match = re.search(r"(\d{4})", prefix)
                                if date_match:
                                    date_str = date_match.group(1)  # "0128"
                                    try:
                                        current_year = datetime.date.today().year
                                        display_date = datetime.datetime.strptime(f"{current_year}{date_str}", "%Y%m%d").date()
                                        
                                        # 获取今天系统日期的前一天
                                        yesterday = datetime.date.today() - datetime.timedelta(days=1)
                                        
                                        # 如果显示日期小于昨天，则颜色变为白色
                                        if display_date < yesterday:
                                            prefix_color = 'white'
                                    except ValueError:
                                        # 如果日期格式无效 (例如 "9999前")，则忽略，颜色保持默认的橙色
                                        pass
                                        
                                # 使用动态设置的颜色来生成HTML
                                parts.append(f"<span style='color:{prefix_color};'>{prefix}</span>")
                            
                            # 2. 获取 Options Metrics
                            metrics = get_options_metrics(keyword)
                            if metrics:
                                # --- 核心修改: 日期校验逻辑 使用 holidays 库 ---
                                # 目标日期: 最近的一个有效交易日
                                target_date = TradingDateHelper.get_last_trading_date()
                                data_date = metrics.get('date1') # 获取最新数据的日期对象
                                
                                # 判断日期是否有效 (注意: data_date 通常是 datetime.date 类型)
                                is_valid_date = (data_date == target_date)
                                
                                if is_valid_date:
                                    # --- 日期正确，才处理数据显示 ---
                                    
                                    # A. 处理 IV
                                    iv_val, iv_str = metrics['iv1']
                                    if iv_str != "--":
                                        if iv_val > 0: iv_color = "red"
                                        elif iv_val < 0: iv_color = "green"
                                        else: iv_color = "gray"
                                        parts.append(f"<span style='color:{iv_color};'>{iv_str}</span>")
                                    
                                    # B. 处理 Change+Price (Sum)
                                    sum_val = metrics['sum1']
                                    # sum_val 通常是 float，直接判断是否显示
                                    # 这里假设只要日期对，sum_val 就是有效的数值
                                    if sum_val > 0: sum_color = "red"
                                    elif sum_val < 0: sum_color = "green"
                                    else: sum_color = "gray"
                                    parts.append(f"<span style='color:{sum_color};'>{sum_val:.2f}</span>")
                                
                                else:
                                    # 日期不对，不显示数据，只显示可能的前缀
                                    pass

                            # 只有当有内容时才组合 HTML
                            if parts:
                                # 使用两个空格作为分隔符
                                display_html = "&nbsp;&nbsp;".join(parts)
                                formatted_compare_html = (
                                    f'<a href="{keyword}" '
                                    f'style="color:gray; text-decoration:none;">'
                                    f'{display_html}</a>'
                                )
                            else:
                                # 如果 parts 为空 (既没有前缀，数据也是 --)，则显示空字符串
                                formatted_compare_html = ""

                        else:
                            # --- 原有逻辑: 其他组保持不变 ---
                            if raw_compare:
                                # 找百分号及前面的数字
                                m = re.search(r"([-+]?\d+(?:\.\d+)?)%", raw_compare)
                                if m:
                                    # 1) 把捕获组里的数字转成 float，再格式化到一位小数
                                    num = float(m.group(1))
                                    percent_fmt = f"{num:.2f}%"

                                    # 2) 找到原始字符串中百分号片段，用来切 prefix/suffix
                                    orig = m.group(0)
                                    idx  = raw_compare.find(orig)
                                    prefix, suffix = raw_compare[:idx].strip(), raw_compare[idx + len(orig):]

                                    # 3) 拼 HTML
                                    prefix_html = f"<span style='color:orange;'>{prefix}</span>"
                                    
                                    # 定义需要特殊颜色处理的分组
                                    special_color_groups = {"Bonds", "Crypto", "Indices", "Economics", "Commodities", "Currencies"}
                                    color_val = "gray"
                                    
                                    if sector in special_color_groups:
                                        if num > 0: color_val = "red"
                                        elif num == 0: color_val = "gray"
                                        else: color_val = "green"
                                    
                                    percent_html = f"<span style='color:{color_val};'>{percent_fmt}</span>"
                                    suffix_html  = f"<span>{suffix}</span>"
                                    
                                    display_html = prefix_html + percent_html + suffix_html
                                    
                                    formatted_compare_html = (
                                        f'<a href="{keyword}" '
                                        f'style="color:gray; text-decoration:none;">'
                                        f'{display_html}</a>'
                                    )
                                else:
                                    # 整段无 %，全橙色
                                    formatted_compare_html = (
                                        f"<span style='color:orange;'>"
                                        f"{raw_compare}</span>"
                                    )
                        # --- 修改结束 ---

                        # 3) 用 QLabel 显示富文本
                        compare_label = QLabel()
                        # PyQt6: Qt.TextFormat.RichText
                        compare_label.setTextFormat(Qt.TextFormat.RichText)
                        compare_label.setText(formatted_compare_html)
                        compare_label.setStyleSheet("font-size:22px;") 
                        compare_label.linkActivated.connect(self.on_keyword_selected_chart)
                        row_layout.addWidget(compare_label)  

                        # 最后把 container 加到 groupbox
                        group_box.layout().addWidget(button_container)

    # --------------------------------------------------
    # 新：接收三个参数：global_pos、keyword、group
    ### 修改 ###: 将“加入黑名单”改为一个带有“newlow”和“earning”选项的子菜单
    # --------------------------------------------------
    def show_context_menu(self, global_pos, keyword, group):
        # 给 menu 指定 parent，防止被垃圾回收
        menu = QMenu(self)

        menu.addAction("删除",          lambda: self.delete_item(keyword, group))
        # ### 新增：添加“查重”选项 ###
        menu.addAction("查重", lambda: self.find_and_highlight_symbol(keyword.upper()))
        
        # 2) 其他顶层菜单项
        menu.addSeparator()
        menu.addAction("编辑 Tags",    lambda: execute_external_script('tags', keyword, group, self))
        # --- 通用“移动”子菜单 ---
        move_menu = menu.addMenu("移动")
        for tgt in ("Must", "Today"):
            act = move_menu.addAction(f"到 {tgt}")
            act.setEnabled(group != tgt)
            # 用 lambda 搭桥：三个参数 keyword, group (当前组), tgt (目标组)
            act.triggered.connect(
                lambda _, k=keyword, src=group, dst=tgt: 
                    self.move_item(k, src, dst)
            )
        menu.addSeparator()
        menu.addAction("改名",          lambda: self.rename_item(keyword, group))
        menu.addAction("编辑 Earing DB", lambda: execute_external_script('editor_earning', keyword))
        menu.addSeparator()
        menu.addAction("添加新事件",    lambda: execute_external_script('event_input', keyword, group, self))
        menu.addAction("编辑事件",      lambda: execute_external_script('event_editor', keyword, group, self))
        menu.addSeparator()
        menu.addAction("在富途中搜索",   lambda: execute_external_script('futu', keyword))
        menu.addAction("查询 DB...",    lambda: self.on_keyword_selected(keyword))
        menu.addAction("doubao检索财报",  lambda: execute_external_script('doubao', keyword))
        menu.addAction("添加到 Earning", lambda: execute_external_script('earning', keyword))
        menu.addSeparator()
        menu.addAction("找相似",        lambda: execute_external_script('similar', keyword))
        
        menu.addSeparator()
        
        # --- 新的黑名单子菜单 ---
        blacklist_menu = menu.addMenu("加入黑名单")
        blacklist_menu.addAction("newlow", lambda: self.add_to_blacklist(keyword, 'newlow', group))
        blacklist_menu.addAction("Earning", lambda: self.add_to_blacklist(keyword, 'Earning', group))
        
        menu.addSeparator()
        menu.addAction("清空 Short_W_backup 分组", lambda: self.clear_group("Short_W_backup"))
        menu.addAction("清空 Short_backup 分组", lambda: self.clear_group("Short_backup"))
        menu.addAction("清空 PE_Deep_backup 分组", lambda: self.clear_group("PE_Deep_backup"))
        menu.addAction("清空 OverSell_W_backup 分组", lambda: self.clear_group("OverSell_W_backup"))
        menu.addAction("清空 Strategy12_backup 分组", lambda: self.clear_group("Strategy12_backup"))
        menu.addAction("清空 Strategy34_backup 分组", lambda: self.clear_group("Strategy34_backup"))
        menu.addAction("清空 PE_valid_backup 分组", lambda: self.clear_group("PE_valid_backup"))
        menu.addAction("清空 PE_invalid_backup 分组", lambda: self.clear_group("PE_invalid_backup"))
        menu.addAction("清空 PE_W_backup 分组", lambda: self.clear_group("PE_W_backup"))
        
        # PyQt6: exec 替代 exec_
        menu.exec(global_pos)

    ### 新增 ###: 直接在程序内处理黑名单逻辑的方法
    def add_to_blacklist(self, keyword, blacklist_category, group):
        """
        将指定的 keyword 添加到 blacklist.json 文件的特定 category 中，并从当前UI移除。
        """
        try:
            # 1. 读取现有的黑名单数据
            if os.path.exists(BLACKLIST_PATH):
                with open(BLACKLIST_PATH, 'r', encoding='utf-8') as f:
                    blacklist_data = json.load(f)
            else:
                blacklist_data = {}
        except (FileNotFoundError, json.JSONDecodeError):
            blacklist_data = {} # 如果文件不存在或格式错误，则创建一个新的

        # 2. 获取或创建对应的分类列表
        if blacklist_category not in blacklist_data:
            blacklist_data[blacklist_category] = []
        
        # 3. 如果 keyword 不在列表中，则添加
        if keyword not in blacklist_data[blacklist_category]:
            blacklist_data[blacklist_category].append(keyword)
            
            # 4. 写回 JSON 文件
            try:
                with open(BLACKLIST_PATH, 'w', encoding='utf-8') as f:
                    json.dump(blacklist_data, f, ensure_ascii=False, indent=4)
                print(f"已将 {keyword} 加入黑名单 '{blacklist_category}' 组。")
                
                # 5. 从当前界面删除该项（复用 delete_item 的刷新逻辑）
                self.delete_item(keyword, group)
            except Exception as e:
                print(f"[错误] 写入黑名单文件失败: {e}")
        else:
            print(f"{keyword} 已存在于黑名单 '{blacklist_category}' 组中，无需重复添加。")
            # 即使已存在，也从当前UI中删除
            self.delete_item(keyword, group)

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
        
        # self.highlighted_buttons = [] # 根据需要，如果你想保留高亮可以注释掉这行，或者保留
        self.highlighted_buttons = []
        # <--- 新增: 刷新时清空分组列表
        self.ordered_groups_on_screen = []

        # >>>>>>>>> 关键修改 START >>>>>>>>>
        # 绝对不要在这里把索引重置为 -1！
        # 这就是导致“连续操作后丢失位置”的罪魁祸首。
        # 删除或注释掉下面这行：
        # self.current_symbol_index = -1 
        # <<<<<<<<< 关键修改 END <<<<<<<<<
        
        self.populate_widgets()

        # >>>>>>>>> 新增安全检查 >>>>>>>>>
        # 刷新后，如果列表变短了（比如删除了最后一个），我们需要把索引修正回来，
        # 防止它指向一个不存在的空位。
        total_symbols = len(self.ordered_symbols_on_screen)
        if total_symbols > 0:
            if self.current_symbol_index >= total_symbols:
                self.current_symbol_index = total_symbols - 1
        else:
            self.current_symbol_index = -1
        # <<<<<<<<< 新增安全检查 END <<<<<<<<<


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
    def on_keyword_selected_chart(self, value, btn_index=None):
        # —— 在真正 plot 之前，先 reload 一下外部可能改动过的文件 —— 
        global json_data, compare_data
        try:
            json_data = load_json(DESCRIPTION_PATH) # 注意这里你原代码是 DESCRIPTION_PATH
        except Exception as e:
            pass # 略过错误处理细节，保持原逻辑
            
        sector = next((s for s, names in sector_data.items() if value in names), None)
        if sector:
            # <--- 关键修改 START: 优先使用传入的精确索引 --->
            if btn_index is not None:
                # 如果传了精确索引，直接信赖它（解决了重复 Symbol 定位错误的问题）
                self.current_symbol_index = btn_index
            elif value in self.ordered_symbols_on_screen:
                # 只有在没传索引（比如通过键盘按键触发）时，才使用模糊查找
                # 为了防止键盘导航时跳回第一个重复项，加一个判断：
                # 如果当前索引所指的正好就是 value，保持不动；否则才搜索
                if not (0 <= self.current_symbol_index < len(self.ordered_symbols_on_screen) and \
                        self.ordered_symbols_on_screen[self.current_symbol_index] == value):
                    self.current_symbol_index = self.ordered_symbols_on_screen.index(value)
            # <--- 新增: 准备窗口标题 --->
            # 默认为 sector (DB表名)，如果能找到对应的 UI 分组名，则使用 UI 分组名
            window_title = sector
            if 0 <= self.current_symbol_index < len(self.ordered_groups_on_screen):
                group_name = self.ordered_groups_on_screen[self.current_symbol_index]
                
                # 1. 计算该组在屏幕上的总数
                total_in_group = self.ordered_groups_on_screen.count(group_name)
                
                # 2. 计算当前是第几个
                # 逻辑：截取列表到当前索引位置（包含当前），统计其中该组名出现的次数
                current_in_group = self.ordered_groups_on_screen[:self.current_symbol_index + 1].count(group_name)
                
                # 3. 拼接标题，例如: "Strategy12 3/12"
                window_title = f"{group_name}  {current_in_group}/{total_in_group}"
            # <--- 修改部分结束 --->

            compare_value = compare_data.get(value, "N/A")
            shares_val, marketcap_val, pe_val, pb_val = fetch_mnspp_data_from_db(DB_PATH, value)
            
            # <--- 修改: 将 window_title 传入 plot_financial_data
            plot_financial_data(
                DB_PATH, sector, value, compare_value, (shares_val, pb_val),
                marketcap_val, pe_val, json_data, '1Y', False,
                callback=lambda action: self.handle_chart_callback(value, action),
                window_title_text=window_title  # <--- 传参
            )
            
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
        # PyQt6: exec 替代 exec_
        dialog.exec()

    def handle_arrow_key(self, direction):
        """根据屏幕视觉顺序处理上/下箭头键导航"""
        num_symbols = len(self.ordered_symbols_on_screen)
        if num_symbols == 0:
            return

        if direction == 'down':
            self.current_symbol_index = (self.current_symbol_index + 1) % num_symbols
        else: # 'up'
            self.current_symbol_index = (self.current_symbol_index - 1 + num_symbols) % num_symbols
        
        symbol = self.ordered_symbols_on_screen[self.current_symbol_index]
        self.on_keyword_selected_chart(symbol)

    def open_search_dialog(self):
        """
        打开一个输入对话框让用户输入 symbol，然后触发查找和高亮。
        """
        text, ok = QInputDialog.getText(self, "搜索 Symbol", "请输入 Symbol:")
        if ok and text:
            # 清理输入，并转换为大写以便不区分大小写匹配
            symbol_to_find = text.strip().upper()
            if symbol_to_find:
                self.find_and_highlight_symbol(symbol_to_find)

    ### <<< 修改: 完全重写 find_and_highlight_symbol 方法以支持多重高亮
    def find_and_highlight_symbol(self, symbol):
        """
        查找所有具有指定 symbol 的按钮，高亮它们。
        1. 如果找到 1 个：直接跳转，不弹窗（视觉对焦即可）。
        2. 如果找到 > 1 个：跳转到第 1 个，并弹窗提示数量。
        3. 如果没找到：弹窗提示未找到。
        """
        # 1. 恢复上一次搜索中所有高亮的按钮
        for button, original_style in self.highlighted_buttons:
            # 检查按钮是否仍然有效（可能在UI刷新后被删除）
            if button:
                try:
                    button.setStyleSheet(original_style)
                except RuntimeError:
                    # 如果按钮已经被删除，会抛出 RuntimeError，忽略即可
                    pass
        self.highlighted_buttons = []

        # 2. 查找所有 SymbolButton 并收集所有匹配项
        found_buttons = []
        all_buttons = self.findChildren(SymbolButton)
        
        # 清理输入字符串
        target_symbol = symbol.strip().upper()
        
        for button in all_buttons:
            if button._symbol.strip().upper() == target_symbol:
                found_buttons.append(button)

        # 3. 如果找到按钮，则高亮所有匹配项并滚动到第一个
        if found_buttons:
            highlight_style = "border: 3px solid #FFD700;" # 金色粗边框
            
            # 遍历并高亮
            for button in found_buttons:
                # 存储当前按钮和它的原始样式
                original_style = button.styleSheet()
                self.highlighted_buttons.append((button, original_style))
                
                # 应用高亮样式（在原有样式上追加一个醒目的边框）
                button.setStyleSheet(f"{original_style}; {highlight_style}")
            
            # --- 关键修复 ---
            # 定义一个内部函数，将“滚动”和“弹窗”都放在这里面
            def perform_jump_and_notify():
                try:
                    # 再次检查按钮是否还存在（防止极端情况下的崩溃）
                    if not found_buttons or not found_buttons[0].isVisible():
                        return

                    # A. 执行滚动
                    self.scroll_area.ensureWidgetVisible(found_buttons[0], 50, 50)
                    found_buttons[0].setFocus()

                    # B. 执行弹窗 (只有在滚动完成后，且需要弹窗时才执行)
                    if len(found_buttons) > 1:
                        QMessageBox.information(
                            self, 
                            "搜索结果", 
                            f"共找到 {len(found_buttons)} 个 '{target_symbol}'。\n已自动跳转至第一个结果。"
                        )
                except Exception as e:
                    print(f"跳转或弹窗时出错: {e}")

            # 使用 QTimer 延迟 200 毫秒执行
            # 增加延时是为了给 QInputDialog 足够的关闭和销毁时间
            QTimer.singleShot(200, perform_jump_and_notify)
            
            print(f"已找到并高亮显示 {len(found_buttons)} 个 {target_symbol}。")

        else:
            # 未找到的情况，也建议稍微延迟一点弹窗，避免焦点冲突
            def show_not_found():
                QMessageBox.warning(self, "未找到", f"在列表中未找到 Symbol: {target_symbol}")
            
            QTimer.singleShot(100, show_not_found)
            print(f"在列表中未找到 Symbol: {target_symbol}")

    def keyPressEvent(self, event):
        """重写键盘事件处理器"""
        key = event.key()
        # PyQt6: 使用 Qt.Key 枚举
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Down:
            self.handle_arrow_key('down')
        elif key == Qt.Key.Key_Up:
            self.handle_arrow_key('up')
        elif key == Qt.Key.Key_G:
            print("快捷键 'g' 按下：正在重新加载配置并刷新界面...")
            self.refresh_selection_window()
        elif key == Qt.Key.Key_F:
            self.open_search_dialog()
        else:
            # 对于其他按键，调用父类的实现，以保留默认行为（例如，如果需要的话）
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 退出时把最新的主配置 copy 到备份，保留主配置不变
    # ------------------------------------------------------------------
    def closeEvent(self, event):
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
        # 1) 先从 config 里拿到当前的“翻译”／描述
        current_desc = ""
        if group in self.config:
            grp = self.config[group]
            if isinstance(grp, dict) and keyword in grp:
                current_desc = grp[keyword]
            # 如果原来是 list 的结构，你可能没有“描述”，就留空

        # 2) 创建一个 QInputDialog 实例
        dialog = QInputDialog(self)
        dialog.setWindowTitle("重命名")
        dialog.setLabelText(f"请为 {keyword} 输入新名称：")
        # 把旧名字塞进去
        dialog.setTextValue(current_desc)
        dialog.setOkButtonText("确定")
        dialog.setCancelButtonText("取消")
        dialog.setModal(True)

        # 3) 全选默认文字
        #    注意：findChild 要在 setTextValue 之后再调用才找得到 QLineEdit
        lineedit = dialog.findChild(QLineEdit)
        if lineedit:
            # 如果 dialog 还没 show，这里调用也会生效，exec_ 时就已全选
            lineedit.selectAll()
        
        # PyQt6: exec 替代 exec_
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = dialog.textValue().strip()
            if new_name:
                # 5) 读旧的 config 文件，然后更新并写回
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config_data = json.load(f, object_pairs_hook=OrderedDict)
                if group in config_data and keyword in config_data[group]:
                    config_data[group][keyword] = new_name
                    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, ensure_ascii=False, indent=4)
                    print(f"已将 {keyword} 的描述更新为: {new_name}")
                    self.refresh_selection_window()
                else:
                    print(f"[重命名失败] 未在分组 {group} 中找到 {keyword}")
            else:
                print("重命名输入为空，操作取消。")
        else:
            print("重命名已取消。")

    def move_item(self, keyword, source_group, target_group):
        """
        通用：将 keyword 从 source_group 移到 target_group。
        config 中允许 list<str> 或 dict<str,any> 两种类型。
        """
        # --- 新增逻辑开始 ---
        # 如果目标是 'Watching' 且该 symbol 已存在于 'Today' 分组
        if source_group != 'Today' and target_group == 'Watching' and keyword in self.config.get('Today', {}):
            print(f"'{keyword}' 已存在于 'Today' 分组中。将仅从源分组 '{source_group}' 删除，而不添加到 'Watching'。")
            # 直接调用删除方法，该方法会处理删除、保存和刷新UI
            self.delete_item(keyword, source_group)
            # 操作完成，直接返回，不再执行后续的移动逻辑
            return
        
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

# --- 主程序入口修改 ---
if __name__ == '__main__':
    # Load data
    keyword_colors = load_json(COLORS_PATH)
    config = load_json(CONFIG_PATH)
    json_data = load_json(DESCRIPTION_PATH)
    sector_data = load_json(SECTORS_ALL_PATH)
    compare_data = load_text_data(COMPARE_DATA_PATH)
    # --- 新增: 加载 Earning History 数据 ---
    earning_history = load_json(EARNING_HISTORY_PATH)
    
    filter_positive_symbols(config, compare_data, CONFIG_PATH)
    
    app = QApplication(sys.argv)
    # --- 修改: 将 Earning History 数据传入主窗口 ---
    main_window = MainWindow(earning_history)
    main_window.showMaximized()
    # PyQt6: exec 替代 exec_
    sys.exit(app.exec())
