import os
import sys
import json
import pyperclip
import subprocess
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QTextBrowser, QScrollArea, QMainWindow, QSizePolicy, QAction
from PyQt5.QtGui import QFont, QColor, QKeySequence, QTextDocument
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QByteArray

# 保持原有的搜索目录列表
searchFolders = [
    "/Users/yanzhang/Documents/ScriptEditor/",
    "/Users/yanzhang/Library/Services/",
    "/Users/yanzhang/Documents/Financial_System",
    "/Users/yanzhang/Documents/python_code",
    "/Users/yanzhang/Documents/News/backup",
    # "/Users/yanzhang/Documents/LuxuryBox",
    # "/Users/yanzhang/Documents/sskeysskey.github.io",
    # "/Users/yanzhang/Downloads/backup/TXT",
    # "/Users/yanzhang/Documents/Books"
]

json_path = "/Users/yanzhang/Documents/Financial_System/Modules/Description.json"

class CustomTextBrowser(QTextBrowser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setOpenLinks(False)  # 禁止自动打开链接

    def setHtml(self, html):
        # 重写setHtml方法，确保初始内容能够正确加载
        super().setHtml(html)

class SearchWorker(QThread):
    finished = pyqtSignal(dict, str, str)

    def __init__(self, directories, keywords, json_path):
        super().__init__()
        self.directories = directories
        self.keywords = keywords
        self.json_path = json_path

    def run(self):
        results = search_files(self.directories, self.keywords)
        self.finished.emit(results, self.json_path, self.keywords)

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
        self.result_area.anchorClicked.connect(self.open_file)

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
        self.worker = SearchWorker(searchFolders, keywords, json_path)
        self.worker.finished.connect(self.show_results)
        self.worker.start()

    def show_results(self, results, json_path, keywords):
        self.loading_label.hide()
        self.result_area.setEnabled(True)
        self.search_button.setEnabled(True)
        self.input_field.setEnabled(True)
        
        matched_names_stocks, matched_names_etfs = search_json_for_keywords(json_path, keywords)
        (matched_names_stocks_tag, matched_names_etfs_tag, 
        matched_names_stocks_name, matched_names_etfs_name,
        matched_names_stocks_symbol, matched_names_etfs_symbol) = search_tag_for_keywords(json_path, keywords)

        html_content = ""

        for directory, files in results.items():
            if files:
                html_content += f"<h2 style='color: yellow; font-size: 18px;'>{directory}</h2>"
                for file in files:
                    file_path = os.path.join(directory, file)
                    html_content += f"<p><a href='{file_path}' style='color: orange; text-decoration: underline; font-size: 18px;'>{file}</a></p>"
                # html_content += "<br>"

        html_content += self.insert_results_html("ETF_tag", matched_names_etfs_tag, 'white', 16)
        html_content += self.insert_results_html("Stock_tag", matched_names_stocks_tag, 'white', 16)
        html_content += self.insert_results_html("Stock_name", matched_names_stocks_name, 'white', 16)
        html_content += self.insert_results_html("ETF_name", matched_names_etfs_name, 'white', 16)
        html_content += self.insert_results_html("Stock_symbol", matched_names_stocks_symbol, 'cyan', 16)
        html_content += self.insert_results_html("ETF_symbol", matched_names_etfs_symbol, 'cyan', 16)
        html_content += self.insert_results_html("Description_Stock", matched_names_stocks, 'gray', 16)
        html_content += self.insert_results_html("Description_ETFs", matched_names_etfs, 'gray', 16)

        self.result_area.setHtml(html_content)

        # 滚动到顶部
        self.result_area.verticalScrollBar().setValue(0)

    def insert_results_html(self, category, results, color, font_size):
        html = ""
        if results:
            html += f"<h2 style='color: yellow; font-size: 16px;'>{category}:</h2>"
            for name, extra in results:
                html += f"<p style='color: {color}; text-decoration: underline; font-size: {font_size}px;'>{name} - {extra}</p>"
        return html

    def open_file(self, url):
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

# 保持原有的搜索相关函数不变
def search_files(directories, keywords):
    matched_files = {}
    keywords_lower = [keyword.strip().lower() for keyword in keywords.split()]

    for directory in directories:
        matched_files[directory] = []
        for root, dirs, files in os.walk(directory):
            for dir_name in dirs:
                if dir_name.endswith('.workflow'):
                    handle_workflow_dir(root, dir_name, directory, keywords_lower, matched_files)
            for name in files:
                handle_file(root, name, directory, keywords_lower, matched_files)

    return matched_files

def handle_workflow_dir(root, dir_name, directory, keywords_lower, matched_files):
    workflow_path = os.path.join(root, dir_name)
    if all(keyword_lower in dir_name.lower() for keyword_lower in keywords_lower):
        matched_files[directory].append(os.path.relpath(workflow_path, directory))
        return
    try:
        wflow_path = os.path.join(workflow_path, 'contents/document.wflow')
        with open(wflow_path, 'r') as file:
            content = file.read().lower()
        if all(keyword_lower in content for keyword_lower in keywords_lower):
            matched_files[directory].append(os.path.relpath(workflow_path, directory))
    except Exception as e:
        print(f"Error reading {wflow_path}: {e}")

def handle_file(root, name, directory, keywords_lower, matched_files):
    item_path = os.path.join(root, name)
    if all(keyword_lower in name.lower() for keyword_lower in keywords_lower):
        matched_files[directory].append(os.path.relpath(item_path, directory))
        return
    if item_path.endswith('.scpt'):
        try:
            content = subprocess.check_output(['osadecompile', item_path], text=True).lower()
            if all(keyword_lower in content for keyword_lower in keywords_lower):
                matched_files[directory].append(os.path.relpath(item_path, directory))
        except Exception as e:
            print(f"Error decompiling {item_path}: {e}")
    elif item_path.endswith(('.txt', '.py', '.json', '.js', '.css', '.html', '.csv', '.md')):
        try:
            with open(item_path, 'r') as file:
                content = file.read().lower()
            if all(keyword_lower in content for keyword_lower in keywords_lower):
                matched_files[directory].append(os.path.relpath(item_path, directory))
        except Exception as e:
            print(f"Error reading {item_path}: {e}")

def read_file_content(path):
    if path.endswith('.scpt'):
        return subprocess.check_output(['osadecompile', path], text=True).lower()
    with open(path, 'r') as file:
        return file.read().lower()

def search_json_for_keywords(json_path, keywords):
    with open(json_path, 'r') as file:
        data = json.load(file)
    keywords_lower = [keyword.strip().lower() for keyword in keywords.split()]

    def search_category(category):
        return [
            (item['symbol'], ' '.join(item.get('tag', []))) for item in data.get(category, [])
            if all(keyword in ' '.join([item['description1'], item['description2']]).lower() for keyword in keywords_lower)
        ]

    return search_category('stocks'), search_category('etfs')

def search_tag_for_keywords(json_path, keywords, max_distance=1):
    with open(json_path, 'r') as file:
        data = json.load(file)
    keywords_lower = [keyword.strip().lower() for keyword in keywords.split()]

    def fuzzy_match(text, keyword):
        words = text.lower().split()
        return any(levenshtein_distance(word, keyword) <= max_distance for word in words)

    def search_category(category):
        tag_matches = []
        name_matches = []
        symbol_matches = []
        for item in data.get(category, []):
            if all(any(fuzzy_match(tag, keyword) for tag in item.get('tag', [])) for keyword in keywords_lower):
                tag_matches.append((item['symbol'], ' '.join(item.get('tag', []))))
            if all(fuzzy_match(item['name'], keyword) for keyword in keywords_lower):
                name_matches.append((item['symbol'], ' '.join(item.get('tag', []))))
            if all(fuzzy_match(item['symbol'], keyword) for keyword in keywords_lower):
                symbol_matches.append((item['symbol'], ' '.join(item.get('tag', []))))
        return tag_matches, name_matches, symbol_matches

    stocks_tag, stocks_name, stocks_symbol = search_category('stocks')
    etfs_tag, etfs_name, etfs_symbol = search_category('etfs')

    return (
        stocks_tag, etfs_tag,
        stocks_name, etfs_name,
        stocks_symbol, etfs_symbol
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
    # 处理剪贴板警告
    try:
        from PyQt5.QtWidgets import QApplication
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass  # 较旧的 PyQt 版本可能没有这些属性

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