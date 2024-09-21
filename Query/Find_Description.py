import os
import sys
import json
import pyperclip
import subprocess
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QTextBrowser, QMainWindow, QAction
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl

json_path = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"

class CustomTextBrowser(QTextBrowser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class SearchWorker(QThread):
    finished = pyqtSignal(str, str)

    def __init__(self, keywords, json_path):
        super().__init__()
        self.keywords = keywords
        self.json_path = json_path

    def run(self):
        self.finished.emit(self.json_path, self.keywords)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文件搜索")
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
        self.loading_label.show()
        self.result_area.clear()
        self.result_area.setEnabled(False)
        self.search_button.setEnabled(False)
        self.input_field.setEnabled(False)
        self.worker = SearchWorker(keywords, json_path)
        self.worker.finished.connect(self.show_results)
        self.worker.start()

    def show_results(self, json_path, keywords):
        self.loading_label.hide()
        self.result_area.setEnabled(True)
        self.search_button.setEnabled(True)
        self.input_field.setEnabled(True)
        
        matched_names_stocks, matched_names_etfs = search_json_for_keywords(json_path, keywords)
        (matched_names_stocks_tag, matched_names_etfs_tag, 
        matched_names_stocks_name, matched_names_etfs_name,
        matched_names_stocks_symbol, matched_names_etfs_symbol) = search_tag_for_keywords(json_path, keywords)

        html_content = ""

        html_content += self.insert_results_html("Stock_tag", matched_names_stocks_tag, 'white', 16)
        html_content += self.insert_results_html("ETF_tag", matched_names_etfs_tag, 'white', 16)
        html_content += self.insert_results_html("Stock_symbol", matched_names_stocks_symbol, 'cyan', 16)
        html_content += self.insert_results_html("ETF_symbol", matched_names_etfs_symbol, 'cyan', 16)
        html_content += self.insert_results_html("Stock_name", matched_names_stocks_name, 'white', 16)
        html_content += self.insert_results_html("ETF_name", matched_names_etfs_name, 'white', 16)
        html_content += self.insert_results_html("Stock_Description", matched_names_stocks, 'gray', 16)
        html_content += self.insert_results_html("ETFs_Description", matched_names_etfs, 'gray', 16)

        self.result_area.setHtml(html_content)

        # 滚动到顶部
        self.result_area.verticalScrollBar().setValue(0)

    def insert_results_html(self, category, results, color, font_size):
        html = ""
        if results:
            html += f"<h2 style='color: yellow; font-size: 16px;'>{category}:</h2>"
            for result in results:
                if len(result) == 3:  # 股票结果
                    symbol, name, tags = result
                    # 创建 symbol 链接
                    html += f"<p><a href='symbol://{symbol}' style='color: {color}; text-decoration: underline; font-size: {font_size}px;'>{symbol} - {name} - {tags}</a></p>"
                else:  # ETF结果
                    symbol, tags = result
                    # 创建 symbol 链接
                    html += f"<p><a href='symbol://{symbol}' style='color: {color}; text-decoration: underline; font-size: {font_size}px;'>{symbol} - {tags}</a></p>"
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
        exact_results = [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', []))) if category == 'stocks' else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if all(keyword in item[search_field].lower() for keyword in keywords_lower)
        ]
        if exact_results:
            return exact_results
        
        return [
            (item['symbol'], item.get('name', ''), ' '.join(item.get('tag', []))) if category == 'stocks' else (item['symbol'], ' '.join(item.get('tag', [])))
            for item in data.get(category, [])
            if all(fuzzy_match(item[search_field], keyword) for keyword in keywords_lower)
        ]

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
        print("请提供参数 input 或 paste")

    sys.exit(app.exec_())