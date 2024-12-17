import os
import sys
import json
import pyperclip
import subprocess
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QTextBrowser, QMainWindow, QAction
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
import sqlite3

json_path = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"

class CustomTextBrowser(QTextBrowser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class SearchWorker(QThread):
    results_ready = pyqtSignal(object)

    def __init__(self, keywords, json_path):
        super().__init__()
        self.keywords = keywords
        self.json_path = json_path
        self.compare_data = load_compare_data()

    def run(self):
        # 在此方法中执行耗时的搜索操作
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

        # 发射包含结果的信号
        self.results_ready.emit(self.results)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("公司、股票和ETF搜索")
        self.setGeometry(350, 200, 800, 600)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setFixedHeight(30)
        self.input_field.setFont(QFont("Arial", 18))
        self.search_button = QPushButton("搜索")
        self.search_button.setFixedSize(60, 30)
        self.input_layout.addWidget(self.input_field, 7)
        self.input_layout.addWidget(self.search_button, 1)
        self.layout.addLayout(self.input_layout)

        self.loading_label = QLabel("正在搜索...", self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Arial", 14))
        self.loading_label.hide()
        self.layout.addWidget(self.loading_label)

        self.result_area = CustomTextBrowser()
        self.result_area.anchorClicked.connect(self.open_file)
        self.result_area.setFont(QFont("Arial", 12))
        self.layout.addWidget(self.result_area)

        self.search_button.clicked.connect(self.start_search)
        self.input_field.returnPressed.connect(self.start_search)

        # 添加 ESC 键关闭窗口的功能
        self.shortcut_close = QKeySequence("Esc")
        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(self.shortcut_close)
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)

    def start_search(self):
        keywords = self.input_field.text()
        if not keywords.strip():
            return  # 如果用户没有输入关键词，则不进行搜索
        # 更新compare数据
        self.compare_data = load_compare_data()
        self.loading_label.show()
        self.result_area.clear()
        self.result_area.setEnabled(False)
        self.search_button.setEnabled(False)
        self.input_field.setEnabled(False)

        # 传递是否有空格的信息
        self.worker = SearchWorker(keywords, json_path)
        self.worker.results_ready.connect(self.show_results)
        self.worker.start()

    def show_results(self, results):
        self.loading_label.hide()
        self.result_area.setEnabled(True)
        self.search_button.setEnabled(True)
        self.input_field.setEnabled(True)

        # 解包结果
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
                symbol = item[0]  # 获取symbol（第一个元素）
                if symbol == search_term:
                    exact_matches.append(item)
                else:
                    partial_matches.append(item)
            
            return exact_matches + partial_matches

        # 对symbol结果进行排序
        matched_names_stocks_symbol = sort_by_exact_match(matched_names_stocks_symbol, search_term)
        matched_names_etfs_symbol = sort_by_exact_match(matched_names_etfs_symbol, search_term)

        # 创建显示顺序列表
        display_order = [
            ("Stock_symbol", matched_names_stocks_symbol, 'cyan'),
            ("ETF_symbol", matched_names_etfs_symbol, 'cyan'),
            ("Stock_name", matched_names_stocks_name, 'white'),
            ("ETF_name", matched_names_etfs_name, 'white'),
            ("Stock_tag", matched_names_stocks_tag, 'white'),
            ("ETF_tag", matched_names_etfs_tag, 'white')
        ]

        html_content = ""

        # 生成HTML内容
        for category, results, color in display_order:
            if results:  # 只显示有结果的类别
                html_content += self.insert_results_html(category, results, color, 16)

        # 添加固定在末尾的类别
        html_content += self.insert_results_html("Stock_Description", matched_names_stocks, 'gray', 16)
        html_content += self.insert_results_html("ETFs_Description", matched_names_etfs, 'gray', 16)

        self.result_area.setHtml(html_content)
        self.result_area.verticalScrollBar().setValue(0)

    def insert_results_html(self, category, results, color, font_size):
        html = ""
        if results:
            html += f"<h2 style='color: yellow; font-size: 16px;'>{category}:</h2>"
            for result in results:
                if len(result) == 3:  # 股票结果
                    symbol, name, tags = result
                    # 查找compare数据
                    compare_info = self.compare_data.get(symbol, "")
                    if compare_info:
                        display_text = f"{symbol}  {compare_info}  {name} - {tags}"
                    else:
                        display_text = f"{symbol} - {name} - {tags}"
                    html += f"<p><a href='symbol://{symbol}' style='color: {color}; text-decoration: underline; font-size: {font_size}px;'>{display_text}</a></p>"
                else:  # ETF 结果
                    symbol, tags = result
                    # 获取 ETF 的最新成交量
                    latest_volume = get_latest_etf_volume(symbol)
                    # 查找compare数据
                    compare_info = self.compare_data.get(symbol, "")
                    # 构建显示文本
                    display_parts = [symbol]
                    if compare_info:
                        display_parts.append(compare_info)
                    display_parts.append(tags)
                    if latest_volume and latest_volume != "N/A":  # 只在有有效成交量时添加
                        display_parts.append(latest_volume)
                    
                    display_text = " - ".join(display_parts)
                    html += f"<p><a href='symbol://{symbol}' style='color: {color}; text-decoration: underline; font-size: {font_size}px;'>{display_text}</a></p>"
        return html

    def open_file(self, url):
        if url.scheme() == 'symbol':
            # 提取 symbol
            symbol = url.toString().replace('symbol://', '').strip()
            if symbol:
                # 将 symbol 复制到剪贴板
                pyperclip.copy(symbol)
                # 获取 stock_chart.py 的绝对路径
                stock_chart_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '/Users/yanzhang/Documents/Financial_System/Query/Stock_Chart.py')
                # 调用 stock_chart.py，传递 'paste' 参数
                subprocess.Popen([sys.executable, stock_chart_path, 'paste'])
        else:
            file_path = url.toLocalFile()
            if not file_path:
                file_path = url.toString()
            try:
                if sys.platform == "win32":
                    os.startfile(file_path)
                else:
                    subprocess.call(("open", file_path))
            except Exception as e:
                print(f"无法打开文件 {file_path}: {e}")

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
        if len(keyword) <= 1:  # 对于单个字符，只进行精确匹配
            return keyword in text.lower()
        words = text.lower().split()
        return any(levenshtein_distance(word, keyword) <= max_distance for word in words)

    def two_step_search(category, search_field):
        search_term = keywords.strip().upper()
        search_term_lower = keywords.strip().lower()
        
        def exact_match(item):
            if search_field == 'name':
                return item.get('name', '').lower() == search_term_lower
            elif search_field == 'symbol':
                return item.get('symbol', '').upper() == search_term
            return False
        
        def partial_match(item):
            if search_field == 'name':
                return all(keyword in item.get('name', '').lower() for keyword in keywords_lower)
            elif search_field == 'symbol':
                return all(keyword in item.get('symbol', '').upper() for keyword in keywords_lower)
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
        # 定义一个计算匹配分数的函数
        def match_score(item):
            tags = item[2].lower() if category == 'stocks' else item[1].lower()
            exact_matches = sum(keyword in tags for keyword in keywords_lower)
            fuzzy_matches = sum(any(fuzzy_match(tag.lower(), keyword) for tag in tags.split()) for keyword in keywords_lower)
            return (exact_matches, fuzzy_matches)

        exact_results = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', []))) if category == 'stocks' else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if all(keyword in ' '.join(item.get('tag', [])).lower() for keyword in keywords_lower)
        ]
        if exact_results:
            return sorted(exact_results, key=match_score, reverse=True)

        return [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', []))) if category == 'stocks' else (item['symbol'], ' '.join(item.get('tag', [])))
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
        # 将 volume 转换为 K 单位并返回
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

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "input":
            # 显示窗口，让用户输入
            pass
        elif arg == "paste":
            # 使用剪贴板内容进行搜索
            clipboard_content = pyperclip.paste()
            if clipboard_content:
                window.input_field.setText(clipboard_content)
                window.start_search()
            else:
                print("剪贴板为空，请复制一些文本后再试。")
    else:
        # 如果没有提供参数，则仅显示窗口，让用户手动输入
        pass

    sys.exit(app.exec_())