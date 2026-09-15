import os
import glob
import subprocess
import sys
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QFrame, QSizePolicy, QTextEdit, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import send2trash

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 调用 AppleScript 自动在富途搜索 ---
def search_in_futu(symbol: str):
    """
    异步执行 AppleScript，将 symbol 复制到剪贴板并拉起富途牛牛进行搜索。
    使用 Popen 避免阻塞 PyQt5 主线程。
    """
    print(f"正在拉起富途牛牛搜索: {symbol}")
    
    applescript_code = f'''
    set input_text to "{symbol}"
    set the clipboard to input_text
    
    tell application "/Applications/FutuNiuniu.app"
        activate
    end tell
    delay 0.5
    
    tell application "System Events"
        tell process "FutuNiuniu"
            set frontmost to true
        end tell
    end tell
    
    set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
    set imageName to "futu_launch.png"
    set clickValue to "false"
    set Opposite to "false"
    
    set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite
    
    do shell script commandString
    
    set x_coord to "1295"
    set y_coord to "56"
    
    set command to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 /Users/yanzhang/Coding/python_code/Click.py " & x_coord & " " & y_coord
    
    do shell script command
    delay 0.5
    
    tell application "System Events"
        key code 0 using command down
        delay 0.5
        keystroke "v" using command down
        delay 0.5
        key code 36
    end tell
    '''
    
    try:
        subprocess.Popen(['osascript', '-e', applescript_code])
    except Exception as e:
        print(f"执行 AppleScript 失败: {e}")

# --- 确认记录相关函数 ---

def load_confirmed_symbols(directory: str) -> dict:
    """
    加载已确认的 symbol 记录
    返回格式: {symbol: (选中的完整行内容, 来源文件名)}
    """
    confirm_file = os.path.join(directory, "Earning_Confirm.txt")
    confirmed = {}
    
    if not os.path.exists(confirm_file):
        return confirmed
    
    try:
        with open(confirm_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                if len(parts) >= 3:
                    symbol = parts[0].strip()
                    line_content = parts[1].strip()
                    source_filename = parts[2].strip()
                    confirmed[symbol] = (line_content, source_filename)
    except Exception as e:
        print(f"读取确认文件时出错: {e}")
    
    return confirmed


def save_confirmed_symbol(directory: str, symbol: str, line_content: str, source_filename: str):
    """
    保存或更新一个已确认的 symbol 记录
    """
    confirm_file = os.path.join(directory, "Earning_Confirm.txt")
    
    try:
        existing_records = []
        symbol_exists = False
        
        if os.path.exists(confirm_file):
            with open(confirm_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip() and not line.startswith('#') and '|' in line:
                        cur_sym = line.split('|')[0].strip()
                        if cur_sym == symbol:
                            existing_records.append(f"{symbol}|{line_content}|{source_filename}\n")
                            symbol_exists = True
                        else:
                            existing_records.append(line)
                    else:
                        existing_records.append(line)
        
        if not symbol_exists:
            if not existing_records:
                existing_records.append("# 已确认的 Symbol 记录\n")
                existing_records.append("# 格式: symbol|line_content|source_filename\n")
            existing_records.append(f"{symbol}|{line_content}|{source_filename}\n")
            
        with open(confirm_file, 'w', encoding='utf-8') as f:
            f.writelines(existing_records)
            
        print(f"  - [已固定记录] '{symbol}' 已成功同步记录到 Earning_Confirm.txt")
    except Exception as e:
        print(f"保存确认记录时出错: {e}")


def auto_resolve_confirmed_symbol(symbol: str, confirmed_line: str, confirmed_filename: str, 
                                   all_occurrences: list, directory: str, main_files: list):
    """
    自动解决已确认的 symbol 冲突
    """
    print(f"  - Symbol '{symbol}' 已有确认记录，自动处理中...")
    
    lines_to_delete_by_file = defaultdict(list)
    for occurrence in all_occurrences:
        occ_filename, _, occ_line_content = occurrence
        if occ_line_content.strip() != confirmed_line.strip():
            lines_to_delete_by_file[occ_filename].append(occ_line_content)
    
    if not is_main_file(confirmed_filename):
        lines_to_delete_by_file[confirmed_filename].append(confirmed_line)
    
    for filename, contents in lines_to_delete_by_file.items():
        full_path = os.path.join(directory, filename)
        remove_specific_lines_from_file(full_path, contents)
        print(f"    - 已从 {filename} 清理 {len(contents)} 个条目。")
    
    if not is_main_file(confirmed_filename):
        print(f"    - 将确认的行插入到匹配日期的主文件中。")
        insert_line_into_main_file(confirmed_line, main_files)


def show_alert(message):
    """使用 AppleScript 显示一个系统对话框"""
    try:
        applescript_code = f'display dialog "{message}" with title "处理结果" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"无法显示AppleScript弹窗: {e}")
        print(f"提示信息: {message}")


def parse_symbol(line: str) -> str | None:
    """从一行中解析出 symbol"""
    if ":" not in line:
        return None
    head = line.split(":", 1)[0].strip()
    return head if head else None


def is_main_file(filename: str) -> bool:
    """判断一个文件是否是主文件 (不含 '_diff_')"""
    return '_diff_' not in filename


def get_file_paths(directory: str):
    """获取所有主文件和辅助文件的路径"""
    pattern = os.path.join(directory, "Earnings_Release_*.txt")
    all_files = glob.glob(pattern)
    main_files = [f for f in all_files if is_main_file(os.path.basename(f))]
    aux_files = [f for f in all_files if not is_main_file(os.path.basename(f))]
    return main_files, aux_files

# --- 文件修改核心逻辑 ---

def remove_specific_lines_from_file(filepath: str, lines_content_to_remove: list[str]):
    """从一个文件中精确删除指定的行"""
    if not lines_content_to_remove:
        return

    try:
        content_set_to_remove = {line.strip() for line in lines_content_to_remove}
        lines_to_keep = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='latin-1') as f:
                lines = f.readlines()

        for line in lines:
            if line.strip() not in content_set_to_remove:
                lines_to_keep.append(line)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines_to_keep)
    except Exception as e:
        print(f"从文件 {os.path.basename(filepath)} 中删除特定行时出错: {e}")


def insert_line_into_main_file(line_to_insert: str, all_main_files: list[str], fallback_file: str = None):
    """
    将指定行插入到日期匹配的第一个主文件中。
    若找不到日期匹配项，且指定了 fallback_file，则安全追加到 fallback_file，防止数据遗失。
    """
    try:
        parts = line_to_insert.split(':')
        if len(parts) < 3:
            print(f"警告: 无法从 '{line_to_insert}' 中解析日期，跳过插入操作。")
            return
        
        date_to_match = parts[2].strip().split(' ')[0]

        def normalize(s):
            return "".join(s.split())
        
        target_normalized = normalize(line_to_insert)

        for main_file_path in all_main_files:
            try:
                with open(main_file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(main_file_path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()
            
            # 防重复检查
            if any(normalize(line) == target_normalized for line in lines):
                print(f"  - 提示: 文件 '{os.path.basename(main_file_path)}' 中已存在该行，跳过插入。")
                return

            new_lines = []
            inserted = False
            for line in lines:
                if not inserted and date_to_match in line:
                    new_lines.append(line_to_insert + '\n')
                    new_lines.append(line)
                    inserted = True
                else:
                    new_lines.append(line)
            
            if inserted:
                with open(main_file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                print(f"已将 '{line_to_insert.strip()}' 插入到文件 '{os.path.basename(main_file_path)}' 中。")
                return

        # 日期在所有主文件中均未找到对应同日条目的防丢机制
        target_fallback = fallback_file if fallback_file and os.path.exists(fallback_file) else (all_main_files[0] if all_main_files else None)
        if target_fallback:
            with open(target_fallback, 'a', encoding='utf-8') as f:
                f.write(line_to_insert.strip() + '\n')
            print(f"提示: 未找到日期为 '{date_to_match}' 的锚点行，已安全追加至 '{os.path.basename(target_fallback)}'。后续排序阶段将自动排列。")
        else:
            print(f"警告: 无法找到任何可供写入的主文件！")

    except Exception as e:
        print(f"插入行时出错: {e}")

# --- PyQt5 GUI部分 (常规重复项) ---

class DuplicateResolverApp(QWidget):
    def __init__(self, duplicates, symbol_sources, directory):
        super().__init__()
        self.all_duplicates = sorted(duplicates, key=lambda x: (-x[1], x[0]))
        self.symbol_sources = symbol_sources
        self.directory = directory
        self.current_duplicate_index = 0
        
        self.main_files, self.aux_files = get_file_paths(self.directory)
        self.confirmed_symbols = load_confirmed_symbols(self.directory)
        self.manual_duplicates = self._preprocess_and_auto_resolve()

        if not self.manual_duplicates:
            print("\n所有常规重复项均已自动处理或无需处理。")
            QTimer.singleShot(100, self.close)
            return

        self.init_ui()
        self.display_current_duplicate()

    def _preprocess_and_auto_resolve(self):
        manual_tasks = []
        auto_resolved_log = []

        for symbol, count in self.all_duplicates:
            occurrences = self.symbol_sources[symbol]
            all_contents = [item[2] for item in occurrences]
            
            def normalize_line(line):
                return "|".join([part.strip() for part in line.split(':')])
            
            if all_contents:
                first_normalized = normalize_line(all_contents[0])
                if all(normalize_line(c) == first_normalized for c in all_contents):
                    main_file_occurrences = [item for item in occurrences if is_main_file(item[0])]
                    if len(main_file_occurrences) > 1:
                        print(f"  - Symbol '{symbol}' 内容一致，但存在于多个主文件中，需手动选择。")
                        manual_tasks.append((symbol, count))
                        continue
                    
                    target_item = None
                    for item in occurrences:
                        if item[0] == "Earnings_Release_new.txt":
                            target_item = item
                            break
                    if target_item is None:
                        for item in occurrences:
                            if is_main_file(item[0]):
                                target_item = item
                                break
                    if target_item is None:
                        target_item = occurrences[0]
                    
                    self._perform_resolution(target_item, save_confirm=False)
                    auto_resolved_log.append(f"  - Symbol '{symbol}' 内容一致，已保留 '{target_item[0]}' 版本。")
                    continue

            if symbol in self.confirmed_symbols:
                confirmed_line, confirmed_filename = self.confirmed_symbols[symbol]
                auto_resolve_confirmed_symbol(symbol, confirmed_line, confirmed_filename, 
                                             occurrences, self.directory, self.main_files)
                auto_resolved_log.append(f"  - Symbol '{symbol}' 已根据确认记录自动处理。")
                continue
            
            new_txt_item = None
            for item in occurrences:
                if item[0] == "Earnings_Release_new.txt":
                    new_txt_item = item
                    break
            
            if new_txt_item:
                self._perform_resolution(new_txt_item, save_confirm=False)
                auto_resolved_log.append(f"  - Symbol '{symbol}' 已根据 'Earnings_Release_new.txt' 自动处理。")
            else:
                manual_tasks.append((symbol, count))

        if auto_resolved_log:
            print("\n--- 自动处理日志 ---")
            for log_entry in auto_resolved_log:
                print(log_entry)
            print("----------------------\n")
            
        return manual_tasks

    def _perform_resolution(self, selected_item, save_confirm=False):
        selected_filename, _, selected_line_content = selected_item
        symbol = parse_symbol(selected_line_content)
        
        print(f"\n处理 Symbol '{symbol}'，选择: '{selected_line_content.strip()}' (来自: {selected_filename})")

        if save_confirm:
            save_confirmed_symbol(self.directory, symbol, selected_line_content, selected_filename)

        all_occurrences = self.symbol_sources.get(symbol, [])
        lines_to_delete_by_file = defaultdict(list)
        for occurrence in all_occurrences:
            if occurrence != selected_item:
                occ_filename, _, occ_line_content = occurrence
                lines_to_delete_by_file[occ_filename].append(occ_line_content)

        if not is_main_file(selected_filename):
            lines_to_delete_by_file[selected_filename].append(selected_line_content)

        for filename, contents in lines_to_delete_by_file.items():
            full_path = os.path.join(self.directory, filename)
            remove_specific_lines_from_file(full_path, contents)

        if not is_main_file(selected_filename):
            insert_line_into_main_file(selected_line_content, self.main_files)

    def init_ui(self):
        self.setWindowTitle('常规重复Symbol处理器')
        self.setGeometry(300, 300, 800, 500)

        self.main_layout = QVBoxLayout(self)
        self.title_label = QLabel()
        self.title_label.setFont(QFont('Arial', 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.futu_button = QPushButton()
        self.futu_button.setStyleSheet("background-color: #ff9900; color: white; font-weight: bold; padding: 8px; font-size: 14px; border-radius: 4px;")
        self.futu_button.setCursor(Qt.PointingHandCursor)
        self.main_layout.addWidget(self.futu_button, alignment=Qt.AlignCenter)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content_widget)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content_widget)
        self.main_layout.addWidget(self.scroll_area)

        button_layout = QHBoxLayout()
        self.skip_button = QPushButton('跳过 (Skip)')
        self.cancel_button = QPushButton('取消 (Cancel)')
        
        self.skip_button.clicked.connect(self.skip_duplicate)
        self.cancel_button.clicked.connect(self.close)

        button_layout.addStretch(1)
        button_layout.addWidget(self.skip_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch(1)

        self.main_layout.addLayout(button_layout)

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def display_current_duplicate(self):
        if self.current_duplicate_index >= len(self.manual_duplicates):
            self.close()
            return

        self.clear_layout(self.scroll_layout)
        symbol, count = self.manual_duplicates[self.current_duplicate_index]
        self.title_label.setText(f"手动处理 ({self.current_duplicate_index + 1}/{len(self.manual_duplicates)}): {symbol} ({count} 次)")

        self.futu_button.setText(f"🔍 在富途牛牛中查看 {symbol}")
        try: self.futu_button.clicked.disconnect()
        except TypeError: pass
        self.futu_button.clicked.connect(lambda checked, s=symbol: search_in_futu(s))

        occurrences = self.symbol_sources[symbol]
        for item in occurrences:
            filename, lineno, line_content = item

            line_frame = QFrame()
            line_layout = QHBoxLayout(line_frame)

            item_display = QTextEdit()
            item_display.setReadOnly(True)
            item_display.setText(f"{line_content}\n(来源: {filename}, 第 {lineno} 行)")
            item_display.setStyleSheet("QTextEdit { border: none; background-color: transparent; font-size: 13px; }")
            item_display.setFixedHeight(50)
            item_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            select_button = QPushButton('选择')
            select_button.setFixedWidth(80)
            select_button.clicked.connect(lambda checked, item_to_proc=item: self.resolve_selection(item_to_proc, False))

            confirm_select_button = QPushButton('确定选择')
            confirm_select_button.setFixedWidth(100)
            confirm_select_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; border-radius: 4px; padding: 5px;")
            confirm_select_button.setToolTip('选择并记住此操作，下次自动处理')
            confirm_select_button.clicked.connect(lambda checked, item_to_proc=item: self.resolve_selection(item_to_proc, True))

            line_layout.addWidget(item_display)
            line_layout.addWidget(select_button)
            line_layout.addWidget(confirm_select_button)
            self.scroll_layout.addWidget(line_frame)

    def resolve_selection(self, selected_item, save_confirm):
        self._perform_resolution(selected_item, save_confirm=save_confirm)
        self.next_duplicate()

    def skip_duplicate(self):
        symbol, _ = self.manual_duplicates[self.current_duplicate_index]
        print(f"\n用户跳过了对 symbol '{symbol}' 的处理。")
        self.next_duplicate()

    def next_duplicate(self):
        self.current_duplicate_index += 1
        if self.current_duplicate_index < len(self.manual_duplicates):
            self.display_current_duplicate()
        else:
            print("\n所有手动常规重复项已处理完毕。")
            self.close()

# --- PyQt5 GUI部分 (#BACKUP_DUP) ---

class BackupDupResolverApp(QWidget):
    def __init__(self, tasks, directory):
        super().__init__()
        self.tasks = tasks
        self.directory = directory
        self.current_task_index = 0
        
        self.main_files, self.aux_files = get_file_paths(self.directory)
        self.all_files = self.main_files + self.aux_files
        self.confirmed_symbols = load_confirmed_symbols(self.directory)
        self.manual_tasks = self._preprocess_confirmed_tasks()

        if not self.manual_tasks:
            print("\n所有 #BACKUP_DUP 任务均已自动处理。")
            QTimer.singleShot(100, self.close)
            return

        self.init_ui()
        self.display_current_task()

    def _preprocess_confirmed_tasks(self):
        manual_tasks = []
        for symbol, line_content, filename, lineno in self.tasks:
            if symbol in self.confirmed_symbols:
                print(f"\n自动处理 #BACKUP_DUP Symbol '{symbol}' (已有确认记录)...")
                occurrences = []
                for path in self.all_files:
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                    except UnicodeDecodeError:
                        with open(path, 'r', encoding='latin-1') as f:
                            lines = f.readlines()
                    
                    for i, line in enumerate(lines):
                        line_stripped = line.strip()
                        if parse_symbol(line_stripped) == symbol:
                            occurrences.append((os.path.basename(path), i + 1, line_stripped))
                
                confirmed_line, confirmed_filename = self.confirmed_symbols[symbol]
                auto_resolve_confirmed_symbol(symbol, confirmed_line, confirmed_filename,
                                             occurrences, self.directory, self.main_files)
            else:
                manual_tasks.append((symbol, line_content, filename, lineno))
        return manual_tasks

    def init_ui(self):
        self.setWindowTitle('#BACKUP_DUP 处理器')
        self.setGeometry(300, 300, 800, 500)

        self.main_layout = QVBoxLayout(self)
        self.title_label = QLabel()
        self.title_label.setFont(QFont('Arial', 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.futu_button = QPushButton()
        self.futu_button.setStyleSheet("background-color: #ff9900; color: white; font-weight: bold; padding: 8px; font-size: 14px; border-radius: 4px;")
        self.futu_button.setCursor(Qt.PointingHandCursor)
        self.main_layout.addWidget(self.futu_button, alignment=Qt.AlignCenter)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content_widget)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content_widget)
        self.main_layout.addWidget(self.scroll_area)

        button_layout = QHBoxLayout()
        self.skip_button = QPushButton('跳过 (Skip)')
        self.cancel_button = QPushButton('取消 (Cancel All)')
        
        self.skip_button.clicked.connect(self.skip_task)
        self.cancel_button.clicked.connect(self.close)

        button_layout.addStretch(1)
        button_layout.addWidget(self.skip_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch(1)

        self.main_layout.addLayout(button_layout)

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def display_current_task(self):
        if self.current_task_index >= len(self.manual_tasks):
            self.close()
            return

        self.clear_layout(self.scroll_layout)
        symbol, _, _, _ = self.manual_tasks[self.current_task_index]
        
        self.futu_button.setText(f"🔍 在富途牛牛中查看 {symbol}")
        try: self.futu_button.clicked.disconnect()
        except TypeError: pass
        self.futu_button.clicked.connect(lambda checked, s=symbol: search_in_futu(s))

        occurrences = []
        for path in self.all_files:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()
            
            for i, line in enumerate(lines):
                line_content = line.strip()
                if parse_symbol(line_content) == symbol:
                    occurrences.append((os.path.basename(path), i + 1, line_content))

        self.title_label.setText(f"处理 #BACKUP_DUP ({self.current_task_index + 1}/{len(self.manual_tasks)}): {symbol} ({len(occurrences)} 次)")

        for item in occurrences:
            filename, lineno, line_content = item
            line_frame = QFrame()
            line_layout = QHBoxLayout(line_frame)
            
            item_display = QTextEdit()
            item_display.setReadOnly(True)
            item_display.setText(f"{line_content}\n(来源: {filename}, 第 {lineno} 行)")
            item_display.setStyleSheet("QTextEdit { border: none; background-color: transparent; font-size: 13px; }")
            item_display.setFixedHeight(50)
            item_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            select_button = QPushButton('选择并迁移')
            select_button.setFixedWidth(100)
            
            confirm_select_button = QPushButton('确定选择并迁移')
            confirm_select_button.setFixedWidth(130)
            confirm_select_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; border-radius: 4px; padding: 5px;")
            confirm_select_button.setToolTip('选择并记住此操作，下次自动处理')
            
            if '#BACKUP_DUP' in line_content:
                select_button.clicked.connect(lambda checked, item_to_proc=item, all_occs=occurrences: self.resolve_selection(item_to_proc, all_occs, False))
                confirm_select_button.clicked.connect(lambda checked, item_to_proc=item, all_occs=occurrences: self.resolve_selection(item_to_proc, all_occs, True))
            else:
                select_button.setEnabled(False)
                confirm_select_button.setEnabled(False)

            line_layout.addWidget(item_display)
            line_layout.addWidget(select_button)
            line_layout.addWidget(confirm_select_button)
            self.scroll_layout.addWidget(line_frame)

    def resolve_selection(self, selected_item, all_occurrences, save_confirm):
        _, _, selected_line_content = selected_item
        symbol = parse_symbol(selected_line_content)
        
        line_to_insert = selected_line_content.split('#')[0].strip()
        if save_confirm:
            save_confirmed_symbol(self.directory, symbol, line_to_insert, selected_item[0])

        lines_to_delete_by_file = defaultdict(list)
        for occ_filename, _, occ_line_content in all_occurrences:
            lines_to_delete_by_file[occ_filename].append(occ_line_content)
        
        for filename, contents in lines_to_delete_by_file.items():
            full_path = os.path.join(self.directory, filename)
            remove_specific_lines_from_file(full_path, contents)

        insert_line_into_main_file(line_to_insert, self.main_files)
        self.next_task()

    def skip_task(self):
        symbol, _, _, _ = self.manual_tasks[self.current_task_index]
        print(f"\n用户跳过了对 #BACKUP_DUP symbol '{symbol}' 的处理。")
        self.next_task()

    def next_task(self):
        self.current_task_index += 1
        if self.current_task_index < len(self.manual_tasks):
            self.display_current_task()
        else:
            print("\n所有 #BACKUP_DUP 任务已处理完毕。")
            self.close()

# --- 清理辅助文件 ---

def cleanup_empty_or_backup_only_diff_files(directory: str):
    print("\n--- 阶段 4: 清理空的或仅含 #BACKUP_DUP 的辅助文件 ---")
    _, aux_files = get_file_paths(directory)
    if not aux_files:
        print("未找到带 '_diff_' 的辅助文件，跳过清理。")
        return

    deleted_files_count = 0
    for file_path in aux_files:
        try:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()

            content_lines = [line.strip() for line in lines if line.strip()]
            should_delete = False
            if not content_lines or all('#BACKUP_DUP' in line for line in content_lines):
                should_delete = True

            if should_delete:
                try:
                    send2trash.send2trash(file_path)
                    print(f"  - 已将文件 '{os.path.basename(file_path)}' 移动到回收站。")
                    deleted_files_count += 1
                except Exception as e:
                    print(f"  - 移动文件 '{os.path.basename(file_path)}' 到回收站时出错: {e}")
        except Exception as e:
            print(f"  - 检查文件 '{os.path.basename(file_path)}' 时出错: {e}")

    if deleted_files_count > 0:
        print(f"清理完成，共移动 {deleted_files_count} 个文件到回收站。")
    else:
        print("没有需要清理的辅助文件。")

# --- 周末日期修正逻辑 (包含固定记录到 Earning_Confirm.txt) ---

class WeekendDatePickerApp(QWidget):
    def __init__(self, tasks, directory):
        super().__init__()
        self.tasks = tasks  # list of (line_content, filename, lineno)
        self.directory = directory
        self.current_task_index = 0
        self.main_files, _ = get_file_paths(self.directory)

        self.init_ui()
        self.display_current_task()

    def init_ui(self):
        self.setWindowTitle('周末日期修正器')
        self.setGeometry(300, 300, 800, 420)

        self.main_layout = QVBoxLayout(self)
        self.title_label = QLabel()
        self.title_label.setFont(QFont('Arial', 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.futu_button = QPushButton()
        self.futu_button.setStyleSheet("background-color: #ff9900; color: white; font-weight: bold; padding: 8px; font-size: 14px; border-radius: 4px;")
        self.futu_button.setCursor(Qt.PointingHandCursor)
        self.main_layout.addWidget(self.futu_button, alignment=Qt.AlignCenter)

        self.task_frame = QFrame()
        self.task_layout = QVBoxLayout(self.task_frame)
        self.main_layout.addWidget(self.task_frame)

        # 增加"记住此操作，后续自动确认"的复选框
        self.confirm_checkbox = QCheckBox("记住此修正结果并加入固定配置 (Earning_Confirm.txt)")
        self.confirm_checkbox.setChecked(True)  # 默认勾选，符合你的核心需求
        self.confirm_checkbox.setStyleSheet("font-weight: bold; color: #2E7D32; font-size: 13px;")
        self.main_layout.addWidget(self.confirm_checkbox, alignment=Qt.AlignCenter)

        button_layout = QHBoxLayout()
        self.modify_button = QPushButton('修改日期 (Modify Date)')
        self.modify_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        self.skip_button = QPushButton('跳过 (Skip)')
        self.cancel_button = QPushButton('取消 (Cancel All)')
        
        self.modify_button.clicked.connect(self.resolve_selection)
        self.skip_button.clicked.connect(self.skip_task)
        self.cancel_button.clicked.connect(self.close)

        button_layout.addStretch(1)
        button_layout.addWidget(self.modify_button)
        button_layout.addWidget(self.skip_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch(1)

        self.main_layout.addLayout(button_layout)
        self.main_layout.addStretch(1)

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def display_current_task(self):
        if self.current_task_index >= len(self.tasks):
            self.close()
            return

        self.clear_layout(self.task_layout)
        line_content, filename, lineno = self.tasks[self.current_task_index]
        symbol = parse_symbol(line_content)

        if symbol:
            self.futu_button.setText(f"🔍 在富途牛牛中查看 {symbol}")
            self.futu_button.show()
            try: self.futu_button.clicked.disconnect()
            except TypeError: pass
            self.futu_button.clicked.connect(lambda checked, s=symbol: search_in_futu(s))
        else:
            self.futu_button.hide()
        
        self.title_label.setText(f"修正周末日期 ({self.current_task_index + 1}/{len(self.tasks)}): {symbol}")

        item_display = QTextEdit()
        item_display.setReadOnly(True)
        item_display.setText(f"{line_content}\n(来源: {filename}, 第 {lineno} 行)")
        item_display.setStyleSheet("QTextEdit { border: none; background-color: transparent; font-size: 14px; }")
        item_display.setFixedHeight(60)
        item_display.setAlignment(Qt.AlignCenter)
        
        self.task_layout.addWidget(item_display)

    def resolve_selection(self):
        """当用户点击'修改日期'按钮时调用"""
        original_line, original_filename, _ = self.tasks[self.current_task_index]
        original_filepath = os.path.join(self.directory, original_filename)
        
        print(f"\n修正周末日期: '{original_line}' 来自 {original_filename}")

        try:
            parts = original_line.split(':')
            symbol_part = parts[0]
            symbol = symbol_part.strip()
            date_part_full = parts[2]
            
            original_date_str = date_part_full.strip().split(' ')[0]
            original_dt = datetime.strptime(original_date_str, '%Y-%m-%d')
            
            weekday = original_dt.weekday()
            if weekday == 5:    # 周六 -> 顺延2天到下周一
                new_dt = original_dt + timedelta(days=2)
            elif weekday == 6:  # 周日 -> 顺延1天到下周一
                new_dt = original_dt + timedelta(days=1)
            else:
                print(f"警告: '{original_line}' 的日期不是周末，跳过修改。")
                self.next_task()
                return
            
            new_date_str = new_dt.strftime('%Y-%m-%d')
            new_date_part = date_part_full.replace(original_date_str, new_date_str)
            
            # 标准化格式并将 BMO/TNS 改为 AMC
            new_line = f"{symbol_part}: AMC :{new_date_part}"
            
            print(f"  - 原行: {original_line}")
            print(f"  - 新行: {new_line.strip()}")

            # 1. 如果勾选了保存确认，固定写入 Earning_Confirm.txt
            if self.confirm_checkbox.isChecked():
                save_confirmed_symbol(self.directory, symbol, new_line.strip(), original_filename)

            # 2. 从原文件删除旧行
            remove_specific_lines_from_file(original_filepath, [original_line])

            # 3. 将新行插入主文件（带回退兜底，绝不丢数据）
            insert_line_into_main_file(new_line.strip(), self.main_files, fallback_file=original_filepath)

        except Exception as e:
            print(f"处理周末日期时发生错误: {e}")

        self.next_task()

    def skip_task(self):
        line_content, _, _ = self.tasks[self.current_task_index]
        print(f"\n用户跳过了对周末日期条目 '{line_content}' 的处理。")
        self.next_task()

    def next_task(self):
        self.current_task_index += 1
        if self.current_task_index < len(self.tasks):
            self.display_current_task()
        else:
            print("\n所有周末日期任务已处理完毕。")
            self.close()


def handle_weekend_dates(directory: str):
    """扫描主文件并处理日期为周末的行（已固定的条目会自动生效并跳过弹窗）"""
    print("\n--- 阶段 5: 检查主文件中的周末日期 ---")
    
    main_files, _ = get_file_paths(directory)
    confirmed_symbols = load_confirmed_symbols(directory)
    weekend_tasks = []

    for path in main_files:
        try:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()

            for lineno, line in enumerate(lines, start=1):
                line_content = line.strip()
                if not line_content or ':' not in line_content:
                    continue

                try:
                    parts = line_content.split(':')
                    if len(parts) < 3:
                        continue
                    
                    sym = parts[0].strip()
                    date_str = parts[2].strip().split(' ')[0]
                    dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    
                    # 发现是周末 (周六 5, 周日 6)
                    if dt_obj.weekday() >= 5:
                        # 检查是否已在确认记录中存在固定的处理规则
                        if sym in confirmed_symbols:
                            conf_line, conf_fn = confirmed_symbols[sym]
                            print(f"  - Symbol '{sym}' 周末日期条目已在 Earning_Confirm.txt 登记，自动替换...")
                            remove_specific_lines_from_file(path, [line_content])
                            insert_line_into_main_file(conf_line, main_files, fallback_file=path)
                        else:
                            weekend_tasks.append((line_content, os.path.basename(path), lineno))

                except (ValueError, IndexError):
                    continue
        except Exception as e:
            print(f"扫描周末日期时无法读取文件 {path}: {e}")

    if weekend_tasks:
        print(f"发现 {len(weekend_tasks)} 个未记录的周末日期条目，正在启动专用处理器...")
        app = QApplication.instance() or QApplication(sys.argv)
        resolver = WeekendDatePickerApp(weekend_tasks, directory)
        resolver.show()
        app.exec_()
        print("周末日期处理器已关闭。")
    else:
        print("主文件中无须手动处理的周末日期条目。")

# --- 阶段 6: 整理主文件按日期排序 ---

def sort_file_by_date(filepath: str):
    """读取文件内容，按日期排序后重新写入"""
    try:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='latin-1') as f:
                lines = f.readlines()
        
        parsed_lines = []
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or ':' not in line_stripped:
                continue
            
            try:
                parts = line_stripped.split(':')
                if len(parts) >= 3:
                    date_str = parts[2].strip().split(' ')[0]
                    dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    parsed_lines.append((dt_obj, line_stripped))
                else:
                    parsed_lines.append((datetime.max, line_stripped))
            except (ValueError, IndexError):
                parsed_lines.append((datetime.max, line_stripped))
        
        parsed_lines.sort(key=lambda x: x[0])
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for _, line_content in parsed_lines:
                f.write(line_content + '\n')
        print(f"  - 已整理 {os.path.basename(filepath)}")
    except Exception as e:
        print(f"整理文件 {os.path.basename(filepath)} 时出错: {e}")


def sort_all_main_files(directory: str):
    print("\n--- 阶段 6: 整理主文件按日期排序 ---")
    main_files, _ = get_file_paths(directory)
    if not main_files:
        print("未找到主文件，跳过整理。")
        return
    for filepath in main_files:
        sort_file_by_date(filepath)
    print(f"已完成 {len(main_files)} 个主文件的整理。")


def remove_intra_file_duplicates(filepath: str):
    """预处理：去除单个文件内的实质重复项"""
    try:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='latin-1') as f:
                lines = f.readlines()
        
        seen_normalized = set()
        new_lines = []
        modified = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                new_lines.append(line)
                continue

            sym = parse_symbol(stripped)
            if sym:
                if ':' in stripped:
                    normalized_key = "|".join([part.strip() for part in stripped.split(':')])
                else:
                    normalized_key = stripped
                
                if normalized_key in seen_normalized:
                    modified = True
                    print(f"    - [自动清理] 发现文件内重复并删除: {stripped} (文件: {os.path.basename(filepath)})")
                    continue 
                seen_normalized.add(normalized_key)
            new_lines.append(line)
        
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"  - [预处理] 已更新文件 '{os.path.basename(filepath)}'。")
    except Exception as e:
        print(f"预处理文件 {os.path.basename(filepath)} 时出错: {e}")


def handle_backup_duplicates(directory: str):
    print("\n--- 阶段 3: 检查 #BACKUP_DUP 标记 ---")
    _, aux_files = get_file_paths(directory)
    backup_dup_tasks = []

    for path in aux_files:
        try:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()

            for lineno, line in enumerate(lines, start=1):
                if '#BACKUP_DUP' in line:
                    line = line.strip()
                    sym = parse_symbol(line)
                    if sym:
                        backup_dup_tasks.append((sym, line, os.path.basename(path), lineno))
        except Exception as e:
            print(f"扫描 #BACKUP_DUP 时无法读取文件 {path}: {e}")

    if backup_dup_tasks:
        print(f"发现 {len(backup_dup_tasks)} 个带有 #BACKUP_DUP 标记的条目，正在启动专用处理器...")
        app = QApplication.instance() or QApplication(sys.argv)
        resolver = BackupDupResolverApp(backup_dup_tasks, directory)
        resolver.show()
        app.exec_()
        print("专用处理器已关闭。")
    else:
        print("未在辅助文件中发现 #BACKUP_DUP 标记的条目。")

# --- 主入口 ---

def main():
    directory = os.path.join(BASE_CODING_DIR, "News")
    pattern = os.path.join(directory, "Earnings_Release_*.txt")
    output_path = os.path.join(directory, "duplication.txt")

    print("--- 阶段 0: 预处理文件内重复项 ---")
    files_to_preprocess = glob.glob(pattern)
    if not files_to_preprocess:
        show_alert("在指定目录中未找到 Earnings_Release_*.txt 文件。")
        return
        
    for path in files_to_preprocess:
        remove_intra_file_duplicates(path)

    print("\n--- 阶段 1: 扫描并处理常规重复项 ---")
    files = glob.glob(pattern)
    symbol_counts = Counter()
    symbol_sources = defaultdict(list)

    def process_file(path, encoding):
        with open(path, "r", encoding=encoding) as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line or '#BACKUP_DUP' in line:
                    continue
                sym = parse_symbol(line)
                if not sym:
                    continue
                symbol_counts[sym] += 1
                symbol_sources[sym].append((os.path.basename(path), lineno, line))

    for path in files:
        try:
            process_file(path, "utf-8")
        except UnicodeDecodeError:
            try:
                process_file(path, "latin-1")
            except Exception as e:
                print(f"读取文件 {path} 时出错: {e}")

    duplicates_dict = {s: c for s, c in symbol_counts.items() if c > 1}

    if duplicates_dict:
        print("发现常规重复 symbols，正在启动交互式处理器...")
        app = QApplication.instance() or QApplication(sys.argv)
        duplicates_list = list(duplicates_dict.items())
        resolver_app = DuplicateResolverApp(duplicates_list, symbol_sources, directory)
        
        if resolver_app.manual_duplicates:
            resolver_app.show()
            app.exec_()
        else:
            app.quit()
        print("常规重复项处理已结束。")
    else:
        print("未发现常规重复项。")

    print("\n--- 阶段 2: 重新分析文件以生成最终报告 ---")
    final_symbol_counts = Counter()
    final_symbol_sources = defaultdict(list)
    
    files_after_edit = glob.glob(pattern)
    for path in files_after_edit:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line or '#BACKUP_DUP' in line: continue
                    sym = parse_symbol(line)
                    if not sym: continue
                    final_symbol_counts[sym] += 1
                    final_symbol_sources[sym].append((os.path.basename(path), lineno))
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line or '#BACKUP_DUP' in line: continue
                    sym = parse_symbol(line)
                    if not sym: continue
                    final_symbol_counts[sym] += 1
                    final_symbol_sources[sym].append((os.path.basename(path), lineno))
        except Exception as e:
            print(f"最终分析时无法读取文件 {path}: {e}")

    final_duplicates = {s: c for s, c in final_symbol_counts.items() if c > 1}
    report_generated = False
    if not final_duplicates:
        if os.path.exists(output_path):
            os.remove(output_path)
    else:
        lines_out = []
        lines_out.append(f"共解析 symbol 数量：{len(final_symbol_counts)}，总出现次数：{sum(final_symbol_counts.values())}")
        lines_out.append("发现的剩余重复 symbol (手动跳过或内容一致项):")
        for sym, count in sorted(final_duplicates.items(), key=lambda x: (-x[1], x[0])):
            lines_out.append(f"- {sym}: {count} 次")
            for src_file, lineno in final_symbol_sources[sym]:
                lines_out.append(f"  · {src_file}: 第 {lineno} 行")
        with open(output_path, "w", encoding="utf-8") as fw:
            fw.write("\n".join(lines_out) + "\n")
        report_generated = True

    # 阶段 3: 处理 #BACKUP_DUP
    handle_backup_duplicates(directory)

    # 阶段 4: 清理空文件或仅含 #BACKUP_DUP 的文件
    cleanup_empty_or_backup_only_diff_files(directory)

    # 阶段 5: 处理周末日期（集成记忆与自动修正）
    handle_weekend_dates(directory)

    # 阶段 6: 整理并按日期排序
    sort_all_main_files(directory)
    
    print("\n所有处理流程已完成。")
    if report_generated:
        show_alert("处理完毕，但仍有手动跳过或内容一致的重复内容，已生成 duplication.txt 报告。")
    else:
        show_alert("所有重复内容已解决，周末日期已修正并固定记录，无需清理的文件也已处理完毕。")


if __name__ == "__main__":
    main()