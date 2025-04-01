import os
import sys
import json
import pyperclip
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QMainWindow, QAction, QScrollArea, QToolButton, QSizePolicy
)
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
import sqlite3

# JSON 文件路径
json_path = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"


class ClickableLabel(QLabel):
    """
    自定义的可点击标签，同时允许鼠标选择文本
    """
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        # 允许选择文本
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # 修改鼠标悬停的指针样式为输入箭头（IBeam）
        self.setCursor(Qt.IBeamCursor)
        # 设置左对齐
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._mouse_pressed_pos = None

    def mousePressEvent(self, event):
        self._mouse_pressed_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mouse_pressed_pos is not None:
            # 如果鼠标移动距离较短，则认为是点击
            if (event.pos() - self._mouse_pressed_pos).manhattanLength() < 5:
                self.clicked.emit()
        super().mouseReleaseEvent(event)


class SearchWorker(QThread):
    results_ready = pyqtSignal(object)

    def __init__(self, keywords, json_path):
        super().__init__()
        self.keywords = keywords
        self.json_path = json_path
        self.compare_data = load_compare_data()

    def run(self):
        # 耗时搜索操作
        matched_names_stocks, matched_names_etfs = search_json_for_keywords(self.json_path, self.keywords)
        (matched_names_stocks_tag, matched_names_etfs_tag, 
         matched_names_stocks_name, matched_names_etfs_name,
         matched_names_stocks_symbol, matched_names_etfs_symbol) = search_tag_for_keywords(self.json_path, self.keywords)

        self.results = {
            'matched_names_stocks': matched_names_stocks,
            'matched_names_etfs': matched_names_etfs,
            'matched_names_stocks_tag': matched_names_stocks_tag,
            'matched_names_etfs_tag': matched_names_etfs_tag,
            'matched_names_stocks_name': matched_names_stocks_name,
            'matched_names_etfs_name': matched_names_etfs_name,
            'matched_names_stocks_symbol': matched_names_stocks_symbol,
            'matched_names_etfs_symbol': matched_names_etfs_symbol
        }

        # 发射搜索结果信号
        self.results_ready.emit(self.results)


class CollapsibleWidget(QWidget):
    """
    可折叠控件：上方显示标题与折叠按钮，点击后可隐藏或显示下方的内容区域
    """
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        # 创建标题按钮，显示组名与箭头
        self.toggle_button = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_button.setStyleSheet("QToolButton { border: none; font: bold 16px; }")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.clicked.connect(self.on_toggle)

        # 内容区域（存放组内搜索结果项）
        self.content_area = QWidget()
        self.content_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(20, 0, 0, 0)
        self.content_area.setLayout(self.content_layout)

        # 主布局：标题按钮 + 内容区域
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

    def on_toggle(self):
        """点击标题按钮时切换内容显示/隐藏，并更新箭头方向"""
        checked = self.toggle_button.isChecked()
        self.content_area.setVisible(checked)
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def addContentWidget(self, widget: QWidget):
        """向内容区域添加控件"""
        self.content_layout.addWidget(widget)


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def search_json_for_keywords(json_path, keywords):
    with open(json_path, 'r') as file:
        data = json.load(file)
    keywords_lower = [keyword.strip().lower() for keyword in keywords.split()]

    def search_category(category):
        if category == 'stocks':
            return [
                (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', []))) 
                for item in data.get(category, [])
                if all(keyword in ' '.join([item['description1'], item['description2']]).lower() for keyword in keywords_lower)
            ]
        else:  # ETFs
            return [
                (item['symbol'], ' '.join(item.get('tag', []))) 
                for item in data.get(category, [])
                if all(keyword in ' '.join([item['description1'], item['description2']]).lower() for keyword in keywords_lower)
            ]

    return search_category('stocks'), search_category('etfs')


def search_tag_for_keywords(json_path, keywords, max_distance=1):
    with open(json_path, 'r') as file:
        data = json.load(file)
    keywords_lower = [keyword.strip().lower() for keyword in keywords.split()]

    def fuzzy_match(text, keyword):
        if len(keyword) <= 1:
            return keyword in text.lower()
        words = text.lower().split()
        return any(levenshtein_distance(word, keyword) <= max_distance for word in words)

    def two_step_search(category, search_field):
        search_term = keywords.strip().lower()
        search_term_lower = search_term

        def exact_match(item):
            if search_field == 'name':
                return item.get('name', '').lower() == search_term_lower
            elif search_field == 'symbol':
                return item.get('symbol', '').lower() == search_term_lower
            return False

        def partial_match(item):
            if search_field == 'name':
                return all(keyword in item.get('name', '').lower() for keyword in keywords_lower)
            elif search_field == 'symbol':
                return all(keyword in item.get('symbol', '').lower() for keyword in keywords_lower)
            return False

        def fuzzy_match_item(item):
            if search_field == 'name':
                return all(fuzzy_match(item.get('name', ''), keyword) for keyword in keywords_lower)
            elif search_field == 'symbol':
                return all(fuzzy_match(item.get('symbol', ''), keyword) for keyword in keywords_lower)
            return False

        exact_matches = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', []))) 
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if exact_match(item)
        ]

        partial_matches = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', [])))
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if not exact_match(item) and partial_match(item)
        ]

        fuzzy_matches = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', [])))
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if not exact_match(item) and not partial_match(item) and fuzzy_match_item(item)
        ]

        return exact_matches + partial_matches + fuzzy_matches

    def search_category_for_tag(category):
        def match_score(item):
            tags = item[2].lower() if category == 'stocks' else item[1].lower()
            exact_matches = sum(keyword in tags for keyword in keywords_lower)
            fuzzy_matches = sum(any(fuzzy_match(tag.lower(), keyword) for tag in tags.split()) for keyword in keywords_lower)
            return (exact_matches, fuzzy_matches)

        exact_results = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', [])))
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if all(keyword in ' '.join(item.get('tag', [])).lower() for keyword in keywords_lower)
        ]
        if exact_results:
            return sorted(exact_results, key=match_score, reverse=True)

        return [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', [])))
            if category == 'stocks'
            else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if all(any(fuzzy_match(tag, keyword) for tag in item.get('tag', [])) for keyword in keywords_lower)
        ]

    return (
        search_category_for_tag('stocks'),
        search_category_for_tag('etfs'),
        two_step_search('stocks', 'name'),
        two_step_search('etfs', 'name'),
        two_step_search('stocks', 'symbol'),
        two_step_search('etfs', 'symbol')
    )


def get_latest_etf_volume(etf_name):
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 查询最新的 volume
    cursor.execute("SELECT volume FROM ETFs WHERE name = ? ORDER BY date DESC LIMIT 1", (etf_name,))
    result = cursor.fetchone()

    conn.close()

    if result and result[0] is not None:
        volume = result[0]
        # 将 volume 转换为 K 单位返回
        return f"{int(volume / 1000)}K"
    else:
        return "N/A"


def load_compare_data():
    compare_data = {}
    try:
        with open("/Users/yanzhang/Documents/News/backup/Compare_All.txt", "r") as f:
            for line in f:
                if ":" in line:
                    symbol, value = line.strip().split(":", 1)
                    compare_data[symbol.strip()] = value.strip()
    except Exception as e:
        print(f"读取Compare_All.txt出错: {e}")
        return {}
    return compare_data


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("公司、股票和ETF搜索")
        self.setGeometry(350, 200, 800, 600)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # 搜索输入区域
        self.input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setFixedHeight(30)
        self.input_field.setFont(QFont("Arial", 18))
        self.search_button = QPushButton("搜索")
        self.search_button.setFixedSize(60, 30)
        self.input_layout.addWidget(self.input_field, 7)
        self.input_layout.addWidget(self.search_button, 1)
        self.layout.addLayout(self.input_layout)

        # 搜索中提示
        self.loading_label = QLabel("正在搜索...", self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Arial", 14))
        self.loading_label.hide()
        self.layout.addWidget(self.loading_label)

        # 结果展示区域：使用 QScrollArea 存放折叠分组
        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_container = QWidget()
        self.results_layout = QVBoxLayout(self.result_container)
        self.results_layout.setAlignment(Qt.AlignTop)
        self.result_container.setLayout(self.results_layout)
        self.result_scroll.setWidget(self.result_container)
        self.layout.addWidget(self.result_scroll)

        self.search_button.clicked.connect(self.start_search)
        self.input_field.returnPressed.connect(self.start_search)

        # 添加 ESC 键快捷关闭功能
        self.shortcut_close = QKeySequence("Esc")
        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(self.shortcut_close)
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)

        self.compare_data = {}

    def start_search(self):
        keywords = self.input_field.text()
        if not keywords.strip():
            return  # 空输入直接返回
        # 刷新 compare 数据
        self.compare_data = load_compare_data()
        self.loading_label.show()
        self.clear_results()
        self.search_button.setEnabled(False)
        self.input_field.setEnabled(False)

        self.worker = SearchWorker(keywords, json_path)
        self.worker.results_ready.connect(self.show_results)
        self.worker.start()

    def clear_results(self):
        # 清除结果区域中所有子控件
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def show_results(self, results):
        self.loading_label.hide()
        self.search_button.setEnabled(True)
        self.input_field.setEnabled(True)

        # 解包搜索结果
        matched_names_stocks = results['matched_names_stocks']
        matched_names_etfs = results['matched_names_etfs']
        matched_names_stocks_tag = results['matched_names_stocks_tag']
        matched_names_etfs_tag = results['matched_names_etfs_tag']
        matched_names_stocks_name = results['matched_names_stocks_name']
        matched_names_etfs_name = results['matched_names_etfs_name']
        matched_names_stocks_symbol = results['matched_names_stocks_symbol']
        matched_names_etfs_symbol = results['matched_names_etfs_symbol']

        search_term = self.input_field.text().strip().upper()

        def sort_by_exact_match(items, search_term):
            exact_matches = []
            partial_matches = []
            for item in items:
                symbol = item[0]
                if symbol == search_term:
                    exact_matches.append(item)
                else:
                    partial_matches.append(item)
            return exact_matches + partial_matches

        # 对 symbol 结果排序
        matched_names_stocks_symbol = sort_by_exact_match(matched_names_stocks_symbol, search_term)
        matched_names_etfs_symbol = sort_by_exact_match(matched_names_etfs_symbol, search_term)

        # 定义各结果组的显示顺序、名称及颜色
        display_order = [
            ("Stock_symbol", matched_names_stocks_symbol, 'cyan'),
            ("ETF_symbol", matched_names_etfs_symbol, 'cyan'),
            ("Stock_name", matched_names_stocks_name, 'white'),
            ("ETF_name", matched_names_etfs_name, 'white'),
            ("Stock_tag", matched_names_stocks_tag, 'white'),
            ("ETF_tag", matched_names_etfs_tag, 'white')
        ]

        # 添加每个分组到结果区域
        for category, result_list, color in display_order:
            if result_list:
                group = CollapsibleWidget(title=category)
                for result in result_list:
                    if len(result) == 3:  # 股票结果： (symbol, name, tags)
                        symbol, name, tags = result
                        compare_info = self.compare_data.get(symbol, "")
                        if compare_info:
                            display_text = f"{symbol}  {compare_info}  {name}  {tags}"
                        else:
                            display_text = f"{symbol}  {name}  {tags}"
                    else:  # ETF 结果： (symbol, tags)
                        symbol, tags = result
                        latest_volume = get_latest_etf_volume(symbol)
                        compare_info = self.compare_data.get(symbol, "")
                        display_parts = [symbol]
                        if compare_info:
                            display_parts.append(compare_info)
                        display_parts.append(tags)
                        if latest_volume and latest_volume != "N/A":
                            display_parts.append(latest_volume)
                        display_text = " ".join(display_parts)
                    lbl = self.create_result_label(display_text, symbol, color, 20)
                    group.addContentWidget(lbl)
                self.results_layout.addWidget(group)

        # 固定分组： Stock_Description 与 ETFs_Description
        if matched_names_stocks:
            group = CollapsibleWidget(title="Stock_Description")
            for result in matched_names_stocks:
                if len(result) == 3:
                    symbol, name, tags = result
                    compare_info = self.compare_data.get(symbol, "")
                    if compare_info:
                        display_text = f"{symbol}  {compare_info}  {name}  {tags}"
                    else:
                        display_text = f"{symbol}  {name}  {tags}"
                    lbl = self.create_result_label(display_text, symbol, 'gray', 20)
                    group.addContentWidget(lbl)
            self.results_layout.addWidget(group)

        if matched_names_etfs:
            group = CollapsibleWidget(title="ETFs_Description")
            for result in matched_names_etfs:
                if len(result) == 2:
                    symbol, tags = result
                    latest_volume = get_latest_etf_volume(symbol)
                    compare_info = self.compare_data.get(symbol, "")
                    display_parts = [symbol]
                    if compare_info:
                        display_parts.append(compare_info)
                    display_parts.append(tags)
                    if latest_volume and latest_volume != "N/A":
                        display_parts.append(latest_volume)
                    display_text = " ".join(display_parts)
                    lbl = self.create_result_label(display_text, symbol, 'gray', 20)
                    group.addContentWidget(lbl)
            self.results_layout.addWidget(group)

    def create_result_label(self, display_text, symbol, color, font_size):
        """
        创建一个结果项标签，设置左对齐、允许文本选择，并通过富文本格式将 symbol 部分设为蓝色，
        其余部分则保持原来的颜色（通过参数 color 传入）
        - 同时设置行间距和字间距加大
        """
        lbl = ClickableLabel()
        lbl.setTextFormat(Qt.RichText)
        # 如果 display_text 以 symbol 开头，则分割 symbol 和剩余文本
        if display_text.startswith(symbol):
            remainder = display_text[len(symbol):]
        else:
            remainder = display_text
        # 使用富文本 HTML 设定 symbol 为蓝色，其余部分使用传入的 color
        # 在外层添加统一的样式：增大行间距(line-height)和字间距(letter-spacing)
        label_html = (
            f"<span style='line-height: 1.8; letter-spacing: 1px;'>"
            f"<span style='color: cyan; text-decoration: underline; font-size: {font_size}px;'>{symbol}</span>"
            f"<span style='color: {color}; text-decoration: underline; font-size: {font_size}px;'>{remainder}</span>"
            f"</span>"
        )
        lbl.setText(label_html)
        lbl.clicked.connect(lambda: self.open_symbol(symbol))
        lbl.setToolTip("点击以复制 symbol 并打开图表")
        return lbl

    def open_symbol(self, symbol):
        """
        当用户点击结果项时，将 symbol 复制到剪贴板，
        并调用 Stock_Chart.py 传入 'paste' 参数
        """
        if symbol:
            pyperclip.copy(symbol)
            stock_chart_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                '/Users/yanzhang/Documents/Financial_System/Query/Stock_Chart.py'
            )
            try:
                subprocess.Popen([sys.executable, stock_chart_path, 'paste'])
            except Exception as e:
                print(f"无法打开图表脚本 {stock_chart_path}: {e}")


if __name__ == "__main__":
    # 开启高 DPI 支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "input":
            # 显示窗口供用户输入
            pass
        elif arg == "paste":
            # 从剪贴板中复制文本进行搜索
            clipboard_content = pyperclip.paste()
            if clipboard_content:
                window.input_field.setText(clipboard_content)
                window.start_search()
            else:
                print("剪贴板为空，请复制一些文本后再试。")
    else:
        # 没有传入参数时由用户手动输入
        pass

    sys.exit(app.exec_())