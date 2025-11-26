import os
import glob
import subprocess
import sys
from collections import defaultdict, Counter
# 新增导入：用于处理日期和时间
from datetime import datetime, timedelta
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame, QSizePolicy, QTextEdit, QCheckBox
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import send2trash  # 新增导入：用于安全删除到回收站

# 在文件开头添加新的函数来处理确认记录

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
                
                # 解析格式: symbol|line_content|source_filename
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
    保存一个已确认的 symbol 记录
    """
    confirm_file = os.path.join(directory, "Earning_Confirm.txt")
    
    try:
        # 读取现有记录
        existing_symbols = set()
        if os.path.exists(confirm_file):
            with open(confirm_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if '|' in line:
                        existing_symbols.add(line.split('|')[0].strip())
        
        # 如果该 symbol 不存在，则追加
        if symbol not in existing_symbols:
            with open(confirm_file, 'a', encoding='utf-8') as f:
                if os.path.getsize(confirm_file) == 0:
                    f.write("# 已确认的 Symbol 记录\n")
                    f.write("# 格式: symbol|line_content|source_filename\n")
                f.write(f"{symbol}|{line_content}|{source_filename}\n")
            print(f"  - 已将 '{symbol}' 的确认记录保存到 Earning_Confirm.txt")
        else:
            # 更新现有记录
            lines = []
            with open(confirm_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            with open(confirm_file, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.strip() and '|' in line:
                        if line.split('|')[0].strip() == symbol:
                            f.write(f"{symbol}|{line_content}|{source_filename}\n")
                        else:
                            f.write(line)
                    else:
                        f.write(line)
            print(f"  - 已更新 '{symbol}' 的确认记录")
            
    except Exception as e:
        print(f"保存确认记录时出错: {e}")


def auto_resolve_confirmed_symbol(symbol: str, confirmed_line: str, confirmed_filename: str, 
                                   all_occurrences: list, directory: str, main_files: list):
    """
    自动解决已确认的 symbol 冲突
    """
    print(f"  - Symbol '{symbol}' 已有确认记录，自动处理中...")
    
    # 构造选中项 (filename, lineno, line_content)
    # 由于我们只有文件名和行内容，lineno 设为 0（不重要）
    selected_item = (confirmed_filename, 0, confirmed_line)
    
    # 1. 确定要删除的行
    lines_to_delete_by_file = defaultdict(list)
    for occurrence in all_occurrences:
        occ_filename, _, occ_line_content = occurrence
        # 删除所有不是选中项的行
        if occ_line_content.strip() != confirmed_line.strip():
            lines_to_delete_by_file[occ_filename].append(occ_line_content)
    
    # 2. 如果选择的是辅助文件项，原始项也需要被删除
    if not is_main_file(confirmed_filename):
        lines_to_delete_by_file[confirmed_filename].append(confirmed_line)
    
    # 3. 执行删除操作
    for filename, contents in lines_to_delete_by_file.items():
        full_path = os.path.join(directory, filename)
        remove_specific_lines_from_file(full_path, contents)
        print(f"    - 已从 {filename} 清理 {len(contents)} 个条目。")
    
    # 4. 如果是辅助文件项，执行插入操作
    if not is_main_file(confirmed_filename):
        print(f"    - 将确认的行插入到匹配日期的主文件中。")
        insert_line_into_main_file(confirmed_line, main_files)

def show_alert(message):
    """使用AppleScript显示一个系统对话框"""
    try:
        # AppleScript代码模板
        applescript_code = f'display dialog "{message}" with title "处理结果" buttons {{"OK"}} default button "OK"'
        # 使用subprocess调用osascript
        subprocess.run(['osascript', '-e', applescript_code], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"无法显示AppleScript弹窗: {e}")
        print(f"提示信息: {message}")

def parse_symbol(line: str) -> str | None:
    """从一行中解析出symbol"""
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
    """
    从一个文件中精确删除一个或多个指定的行（通过内容匹配）。
    """
    if not lines_content_to_remove:
        return

    try:
        # 使用strip()来匹配，以忽略行尾的空白符差异
        content_set_to_remove = {line.strip() for line in lines_content_to_remove}
        
        lines_to_keep = []
        # 尝试用utf-8解码，失败则用latin-1
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='latin-1') as f:
                lines = f.readlines()

        for line in lines:
            if line.strip() not in content_set_to_remove:
                lines_to_keep.append(line)

        # 写回文件，确保行与行之间只有一个换行符
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines_to_keep)
    except Exception as e:
        print(f"从文件 {os.path.basename(filepath)} 中删除特定行时出错: {e}")


def insert_line_into_main_file(line_to_insert: str, all_main_files: list[str]):
    """将指定行插入到日期匹配的第一个主文件中"""
    try:
        # 从待插入行中提取日期
        # 即使行中包含 #BACKUP_DUP，此逻辑也能正常工作，因为它会取第三部分并分割
        parts = line_to_insert.split(':')
        if len(parts) < 3:
            print(f"警告: 无法从 '{line_to_insert}' 中解析日期，跳过插入操作。")
            return
        # 确保我们正确提取日期，即使有其他信息
        date_to_match = parts[2].strip().split(' ')[0]

        found_insertion_spot = False
        for main_file_path in all_main_files:
            # 尝试用utf-8解码，失败则用latin-1
            try:
                with open(main_file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(main_file_path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()
            
            new_lines = []
            inserted = False
            for i, line in enumerate(lines):
                if not inserted and date_to_match in line:
                    new_lines.append(line_to_insert + '\n')
                    new_lines.append(line)
                    inserted = True
                    found_insertion_spot = True
                else:
                    new_lines.append(line)
            
            if inserted:
                with open(main_file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                print(f"已将 '{line_to_insert.strip()}' 插入到文件 '{os.path.basename(main_file_path)}' 中。")
                break # 插入一次后即停止

        if not found_insertion_spot:
            print(f"警告: 在所有主文件中均未找到日期为 '{date_to_match}' 的行，无法插入 '{line_to_insert.strip()}'。")

    except Exception as e:
        print(f"插入行时出错: {e}")


# --- PyQt5 GUI部分 (常规重复项) ---

# 修改 DuplicateResolverApp 类

class DuplicateResolverApp(QWidget):
    def __init__(self, duplicates, symbol_sources, directory):
        super().__init__()
        self.all_duplicates = sorted(duplicates, key=lambda x: (-x[1], x[0]))
        self.symbol_sources = symbol_sources
        self.directory = directory
        self.current_duplicate_index = 0
        
        self.main_files, self.aux_files = get_file_paths(self.directory)
        
        # 加载已确认的 symbol 记录
        self.confirmed_symbols = load_confirmed_symbols(self.directory)
        
        # 预处理
        self.manual_duplicates = self._preprocess_and_auto_resolve()

        if not self.manual_duplicates:
            print("\n所有常规重复项均已自动处理或无需处理。")
            QTimer.singleShot(100, self.close)
            return

        self.init_ui()
        self.display_current_duplicate()

    def _preprocess_and_auto_resolve(self):
        """预处理所有重复项"""
        manual_tasks = []
        auto_resolved_log = []

        for symbol, count in self.all_duplicates:
            occurrences = self.symbol_sources[symbol]
            
            # --- 新增逻辑：检查内容是否完全一致 ---
            # 提取所有出现的行内容
            all_contents = [item[2] for item in occurrences]
            
            # 定义一个标准化函数，用于忽略空格差异进行比较
            # 例如: "ACN : BMO : 2025-12-18" 和 "ACN: BMO: 2025-12-18" 应该被视为相同
            def normalize_line(line):
                # 按冒号分割，去除每部分的空格，重新组合
                return "|".join([part.strip() for part in line.split(':')])
            
            # 获取第一个标准化后的内容
            if all_contents:
                first_normalized = normalize_line(all_contents[0])
                
                # 检查是否所有行都相同
                if all(normalize_line(c) == first_normalized for c in all_contents):
                    # print(f"  - Symbol '{symbol}' 在所有来源中内容实质一致，跳过处理（保持原状）。") <--- 原来的代码，导致diff文件删不掉
                    
                    # --- 新逻辑：虽然内容一致，但必须清理掉 diff 文件里的冗余副本 ---
                    print(f"  - Symbol '{symbol}' 内容实质一致，正在自动保留主副本并清理冗余项...")
                    
                    target_item = None
                    
                    # 策略：选择一个“最佳”保留项
                    # 优先级 1: Earnings_Release_new.txt (通常是最新的)
                    for item in occurrences:
                        if item[0] == "Earnings_Release_new.txt":
                            target_item = item
                            break
                    
                    # 优先级 2: 任何主文件 (非 _diff_ 文件)
                    if target_item is None:
                        for item in occurrences:
                            if is_main_file(item[0]):
                                target_item = item
                                break
                    
                    # 优先级 3: 如果都没有(都在diff文件里)，就选第一个
                    if target_item is None:
                        target_item = occurrences[0]
                    
                    # 调用核心处理函数：这会保留 target_item，删除其他所有 occurrences
                    # 如果 target_item 在 diff 文件里，它还会自动把它移动到主文件
                    self._perform_resolution(target_item, save_confirm=False)
                    
                    auto_resolved_log.append(f"  - Symbol '{symbol}' 内容一致，已保留 '{target_item[0]}' 版本并清理其他副本。")
                    continue

            # 优先检查是否已有确认记录
            if symbol in self.confirmed_symbols:
                confirmed_line, confirmed_filename = self.confirmed_symbols[symbol]
                auto_resolve_confirmed_symbol(symbol, confirmed_line, confirmed_filename, 
                                             occurrences, self.directory, self.main_files)
                auto_resolved_log.append(f"  - Symbol '{symbol}' 已根据确认记录自动处理。")
                continue
            
            # 检查是否包含 new.txt
            new_txt_item = None
            for item in occurrences:
                if item[0] == "Earnings_Release_new.txt":
                    new_txt_item = item
                    break
            
            if new_txt_item:
                self._perform_resolution(new_txt_item, save_confirm=False)
                auto_resolved_log.append(f"  - Symbol '{symbol}' 已根据 'Earnings_Release_new.txt' 的条目自动处理。")
            else:
                manual_tasks.append((symbol, count))

        if auto_resolved_log:
            print("\n--- 自动处理日志 ---")
            for log_entry in auto_resolved_log:
                print(log_entry)
            print("----------------------\n")
            
        return manual_tasks

    def _perform_resolution(self, selected_item, save_confirm=False):
        """执行解决冲突的核心文件操作"""
        selected_filename, _, selected_line_content = selected_item
        symbol = parse_symbol(selected_line_content)
        
        print(f"\n处理 Symbol '{symbol}'，选择的条目: '{selected_line_content.strip()}' (来自: {selected_filename})")

        # 如果需要保存确认记录
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

        print(f"  操作: 清理 '{symbol}' 的其他重复项。")
        for filename, contents in lines_to_delete_by_file.items():
            full_path = os.path.join(self.directory, filename)
            remove_specific_lines_from_file(full_path, contents)
            print(f"    - 已从 {filename} 清理 {len(contents)} 个条目。")

        if not is_main_file(selected_filename):
            print(f"  操作: 将所选行插入到匹配日期的一个主文件中。")
            insert_line_into_main_file(selected_line_content, self.main_files)

    def init_ui(self):
        self.setWindowTitle('常规重复Symbol处理器')
        self.setGeometry(300, 300, 800, 450)  # 增加高度以容纳确认选项

        self.main_layout = QVBoxLayout(self)

        self.title_label = QLabel()
        self.title_label.setFont(QFont('Arial', 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

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

        occurrences = self.symbol_sources[symbol]
        
        # 用于存储每个条目的确认复选框
        self.confirm_checkboxes = {}
        
        for item in occurrences:
            filename, lineno, line_content = item

            line_frame = QFrame()
            line_layout = QHBoxLayout(line_frame)

            item_display = QTextEdit()
            item_display.setReadOnly(True)
            item_display.setText(f"{line_content}\n(来源: {filename}, 第 {lineno} 行)")
            item_display.setStyleSheet("""
                QTextEdit {
                    border: none;
                    background-color: transparent;
                    font-size: 13px;
                }
            """)
            item_display.setFixedHeight(50)
            item_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            # 添加确认复选框
            from PyQt5.QtWidgets import QCheckBox
            confirm_checkbox = QCheckBox('确认')
            confirm_checkbox.setToolTip('勾选后，下次遇到相同 symbol 冲突时将自动使用此选择')
            
            select_button = QPushButton('选择')
            select_button.setFixedWidth(100)
            select_button.clicked.connect(
                lambda checked, item_to_process=item, checkbox=confirm_checkbox: 
                self.resolve_selection(item_to_process, checkbox.isChecked())
            )

            line_layout.addWidget(item_display)
            line_layout.addWidget(confirm_checkbox)
            line_layout.addWidget(select_button)
            
            self.scroll_layout.addWidget(line_frame)

    def resolve_selection(self, selected_item, save_confirm):
        """GUI事件：当用户点击'选择'按钮时调用"""
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

# 同样需要在 BackupDupResolverApp 中添加确认功能

class BackupDupResolverApp(QWidget):
    def __init__(self, tasks, directory):
        super().__init__()
        self.tasks = tasks
        self.directory = directory
        self.current_task_index = 0
        
        self.main_files, self.aux_files = get_file_paths(self.directory)
        self.all_files = self.main_files + self.aux_files
        
        # 加载已确认的 symbol 记录
        self.confirmed_symbols = load_confirmed_symbols(self.directory)

        # 预处理：自动解决已确认的 symbols
        self.manual_tasks = self._preprocess_confirmed_tasks()

        if not self.manual_tasks:
            print("\n所有 #BACKUP_DUP 任务均已自动处理。")
            QTimer.singleShot(100, self.close)
            return

        self.init_ui()
        self.display_current_task()

    def _preprocess_confirmed_tasks(self):
        """预处理任务，自动解决已确认的 symbols"""
        manual_tasks = []
        
        for symbol, line_content, filename, lineno in self.tasks:
            if symbol in self.confirmed_symbols:
                # 自动处理
                print(f"\n自动处理 #BACKUP_DUP Symbol '{symbol}' (已有确认记录)...")
                
                # 重新扫描该 symbol 的所有出现
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
        self.setGeometry(300, 300, 800, 450)

        self.main_layout = QVBoxLayout(self)
        self.title_label = QLabel()
        self.title_label.setFont(QFont('Arial', 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

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
            
            from PyQt5.QtWidgets import QCheckBox
            confirm_checkbox = QCheckBox('确认')
            confirm_checkbox.setToolTip('勾选后，下次遇到相同 symbol 冲突时将自动使用此选择')
            
            select_button = QPushButton('选择并迁移')
            select_button.setFixedWidth(120)
            
            if '#BACKUP_DUP' in line_content:
                select_button.clicked.connect(
                    lambda checked, item_to_process=item, all_occs=occurrences, checkbox=confirm_checkbox: 
                    self.resolve_selection(item_to_process, all_occs, checkbox.isChecked())
                )
            else:
                select_button.setEnabled(False)
                confirm_checkbox.setEnabled(False)
                select_button.setToolTip("只有带 #BACKUP_DUP 标记的行才能被选择用于迁移。")

            line_layout.addWidget(item_display)
            line_layout.addWidget(confirm_checkbox)
            line_layout.addWidget(select_button)
            self.scroll_layout.addWidget(line_frame)

    def resolve_selection(self, selected_item, all_occurrences, save_confirm):
        """当用户点击'选择并迁移'按钮时调用"""
        _, _, selected_line_content = selected_item
        symbol = parse_symbol(selected_line_content)
        
        print(f"\n处理 #BACKUP_DUP Symbol '{symbol}'...")

        line_to_insert = selected_line_content.split('#')[0].strip()
        print(f"  - 准备插入的行: '{line_to_insert}'")
        
        # 如果需要保存确认记录（使用清理后的行）
        if save_confirm:
            # 从 line_to_insert 中提取文件名信息（如果可能）
            # 因为我们清理了 #BACKUP_DUP，所以使用原始 selected_item 的文件名
            selected_filename = selected_item[0]
            save_confirmed_symbol(self.directory, symbol, line_to_insert, selected_filename)

        lines_to_delete_by_file = defaultdict(list)
        for occ_filename, _, occ_line_content in all_occurrences:
            lines_to_delete_by_file[occ_filename].append(occ_line_content)
        
        print(f"  - 清理 '{symbol}' 的所有相关条目...")
        for filename, contents in lines_to_delete_by_file.items():
            full_path = os.path.join(self.directory, filename)
            remove_specific_lines_from_file(full_path, contents)
            print(f"    - 已从 {filename} 清理 {len(contents)} 个条目。")

        print(f"  - 将清理后的行插入主文件...")
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

# --- 处理 #BACKUP_DUP 的主函数 ---

def handle_backup_duplicates(directory: str):
    """扫描并处理所有文件中带有 #BACKUP_DUP 标记的行"""
    print("\n--- 阶段 3: 检查 #BACKUP_DUP 标记 ---")
    
    _, aux_files = get_file_paths(directory)
    backup_dup_tasks = []

    for path in aux_files:
        try:
            # 尝试用utf-8解码，失败则用latin-1
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
                        # 存储任务信息: (symbol, 行内容, 文件名, 行号)
                        backup_dup_tasks.append((sym, line, os.path.basename(path), lineno))

        except Exception as e:
            print(f"扫描 #BACKUP_DUP 时无法读取文件 {path}: {e}")

    if backup_dup_tasks:
        print(f"发现 {len(backup_dup_tasks)} 个带有 #BACKUP_DUP 标记的条目，正在启动专用处理器...")
        
        # 确保QApplication实例存在
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
            
        resolver = BackupDupResolverApp(backup_dup_tasks, directory)
        resolver.show()
        app.exec_()
        print("专用处理器已关闭。")
    else:
        print("未在辅助文件中发现 #BACKUP_DUP 标记的条目。")


# --- 新增：清理辅助文件的函数 ---
def cleanup_empty_or_backup_only_diff_files(directory: str):
    """
    清理所有空的或仅包含 #BACKUP_DUP 行的 _diff_ 辅助文件。
    文件将被移动到回收站，而不是永久删除。
    """
    print("\n--- 阶段 4: 清理空的或仅含 #BACKUP_DUP 的辅助文件 ---")
    
    _, aux_files = get_file_paths(directory)
    
    if not aux_files:
        print("未找到带 '_diff_' 的辅助文件，跳过清理。")
        return

    deleted_files_count = 0
    for file_path in aux_files:
        try:
            # 使用正确的编码读取文件内容
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()

            # 过滤掉空行或只包含空白的行
            content_lines = [line.strip() for line in lines if line.strip()]

            # 检查是否满足删除条件：
            # 1. 文件中没有任何有内容的行（即文件为空或只含空行）。
            # 2. 或者，所有有内容的行都包含 '#BACKUP_DUP'。
            should_delete = False
            if not content_lines:
                should_delete = True
            elif all('#BACKUP_DUP' in line for line in content_lines):
                should_delete = True

            if should_delete:
                try:
                    send2trash.send2trash(file_path)
                    print(f"  - 已将文件 '{os.path.basename(file_path)}' 移动到回收站。")
                    deleted_files_count += 1
                except Exception as e:
                    print(f"  - 移动文件 '{os.path.basename(file_path)}' 到回收站时出错: {e}")
        
        except FileNotFoundError:
            # 文件可能在之前的步骤中被重命名或删除，这很正常
            print(f"  - 检查文件 '{os.path.basename(file_path)}' 时未找到，可能已被处理。")
        except Exception as e:
            print(f"  - 检查文件 '{os.path.basename(file_path)}' 时出错: {e}")

    if deleted_files_count > 0:
        print(f"清理完成，共移动 {deleted_files_count} 个文件到回收站。")
    else:
        print("没有需要清理的辅助文件。")

# --- 新增：PyQt5 GUI部分 (周末日期修正) ---

class WeekendDatePickerApp(QWidget):
    def __init__(self, tasks, directory):
        super().__init__()
        self.tasks = tasks  # list of (line_content, filename, lineno)
        self.directory = directory
        self.current_task_index = 0
        
        # 只需要主文件列表用于插入操作
        self.main_files, _ = get_file_paths(self.directory)

        self.init_ui()
        self.display_current_task()

    def init_ui(self):
        self.setWindowTitle('周末日期修正器')
        self.setGeometry(300, 300, 800, 300)

        self.main_layout = QVBoxLayout(self)
        self.title_label = QLabel()
        self.title_label.setFont(QFont('Arial', 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        # 这个界面一次只显示一个任务，不需要滚动区域
        self.task_frame = QFrame()
        self.task_layout = QVBoxLayout(self.task_frame)
        self.main_layout.addWidget(self.task_frame)

        button_layout = QHBoxLayout()
        self.modify_button = QPushButton('修改日期 (Modify Date)')
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
        self.main_layout.addStretch(1) # 增加弹性空间

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
        
        self.title_label.setText(f"修正周末日期 ({self.current_task_index + 1}/{len(self.tasks)})")

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
        
        print(f"\n修正周末日期: '{original_line}' from {original_filename}")

        try:
            # 1. 解析原始行，计算新日期和新行内容
            parts = original_line.split(':')
            symbol_part = parts[0]
            date_part_full = parts[2]
            
            original_date_str = date_part_full.strip().split(' ')[0]
            original_dt = datetime.strptime(original_date_str, '%Y-%m-%d')
            
            # 计算到下一个周一的日期
            weekday = original_dt.weekday() # Monday is 0 and Sunday is 6
            if weekday == 5: # Saturday
                new_dt = original_dt + timedelta(days=2)
            elif weekday == 6: # Sunday
                new_dt = original_dt + timedelta(days=1)
            else:
                # 理论上不会进入这里，因为我们只处理周末
                print(f"警告: '{original_line}' 的日期不是周末，跳过修改。")
                self.next_task()
                return
            
            new_date_str = new_dt.strftime('%Y-%m-%d')
            
            # 2. 构建新行，保持原有格式，将 BMO/TNS 替换为 AMC
            # 这种方法可以保留 symbol 部分的尾部空格和 date 部分的头部空格
            new_date_part = date_part_full.replace(original_date_str, new_date_str)
            new_line = f"{symbol_part}: AMC :{new_date_part}"
            
            print(f"  - 原行: {original_line}")
            print(f"  - 新行: {new_line.strip()}")

            # 3. 从原文件删除旧行
            print(f"  - 从 {original_filename} 删除旧行...")
            remove_specific_lines_from_file(original_filepath, [original_line])

            # 4. 将新行插入到对应日期的主文件中
            print(f"  - 将新行插入到主文件...")
            insert_line_into_main_file(new_line, self.main_files)

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

# --- 新增：处理周末日期的主函数 ---

def handle_weekend_dates(directory: str):
    """扫描主文件并处理日期为周末的行"""
    print("\n--- 阶段 5: 检查主文件中的周末日期 ---")
    
    main_files, _ = get_file_paths(directory)
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
                    
                    date_str = parts[2].strip().split(' ')[0]
                    dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    
                    # Monday is 0 and Sunday is 6. Saturday is 5.
                    if dt_obj.weekday() >= 5:
                        weekend_tasks.append((line_content, os.path.basename(path), lineno))

                except (ValueError, IndexError):
                    # 忽略无法解析日期或格式不正确的行
                    continue
        
        except Exception as e:
            print(f"扫描周末日期时无法读取文件 {path}: {e}")

    if weekend_tasks:
        print(f"发现 {len(weekend_tasks)} 个日期为周末的条目，正在启动专用处理器...")
        
        app = QApplication.instance() or QApplication(sys.argv)
        resolver = WeekendDatePickerApp(weekend_tasks, directory)
        resolver.show()
        app.exec_()
        print("周末日期处理器已关闭。")
    else:
        print("在主文件中未发现日期为周末的条目。")

# --- 新增：阶段 6: 整理主文件按日期排序 ---

def sort_file_by_date(filepath: str):
    """
    读取文件内容，按日期排序后重新写入
    """
    try:
        # 读取文件
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='latin-1') as f:
                lines = f.readlines()
        
        # 解析每一行，提取日期用于排序
        parsed_lines = []
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or ':' not in line_stripped:
                # 跳过空行或格式不正确的行
                continue
            
            try:
                parts = line_stripped.split(':')
                if len(parts) >= 3:
                    date_str = parts[2].strip().split(' ')[0]
                    # 尝试解析日期
                    dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    parsed_lines.append((dt_obj, line_stripped))
                else:
                    # 格式不正确，保留原行但不参与排序（放到最后）
                    parsed_lines.append((datetime.max, line_stripped))
            except (ValueError, IndexError):
                # 无法解析日期，保留原行但不参与排序（放到最后）
                parsed_lines.append((datetime.max, line_stripped))
        
        # 按日期排序
        parsed_lines.sort(key=lambda x: x[0])
        
        # 写回文件
        with open(filepath, 'w', encoding='utf-8') as f:
            for _, line_content in parsed_lines:
                f.write(line_content + '\n')
        
        print(f"  - 已整理 {os.path.basename(filepath)}")
        
    except Exception as e:
        print(f"整理文件 {os.path.basename(filepath)} 时出错: {e}")


def sort_all_main_files(directory: str):
    """
    整理所有主文件，按日期排序
    """
    print("\n--- 阶段 6: 整理主文件按日期排序 ---")
    
    main_files, _ = get_file_paths(directory)
    
    if not main_files:
        print("未找到主文件，跳过整理。")
        return
    
    for filepath in main_files:
        sort_file_by_date(filepath)
    
    print(f"已完成 {len(main_files)} 个主文件的整理。")

# --- 主程序入口 ---

def main():
    directory = "/Users/yanzhang/Coding/News"
    pattern = os.path.join(directory, "Earnings_Release_*.txt")
    output_path = os.path.join(directory, "duplication.txt")

    # --- 阶段 1: 初始扫描和处理常规重复项 ---
    print("--- 阶段 1: 扫描并处理常规重复项 ---")
    files = glob.glob(pattern)

    if not files:
        show_alert("在指定目录中未找到 Earnings_Release_*.txt 文件。")
        return

    symbol_counts = Counter()
    symbol_sources = defaultdict(list)

    def process_file(path, encoding):
        with open(path, "r", encoding=encoding) as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                # 忽略带 #BACKUP_DUP 的行，它们将在后续步骤中专门处理
                if '#BACKUP_DUP' in line:
                    continue
                sym = parse_symbol(line)
                if not sym:
                    continue
                symbol_counts[sym] += 1
                # 存储完整信息：文件名，行号，行内容
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

    # 如果有重复项，启动GUI进行交互式处理
    if duplicates_dict:
        print("发现常规重复 symbols，正在启动交互式处理器...")
        app = QApplication(sys.argv)
        # 将字典转换为元组列表
        duplicates_list = list(duplicates_dict.items())
        resolver_app = DuplicateResolverApp(duplicates_list, symbol_sources, directory)
        
        # 只有当有手动任务时才显示窗口
        if resolver_app.manual_duplicates:
            resolver_app.show()
            app.exec_()
        else:
            # 如果没有手动任务，直接退出app循环
            app.quit()
        
        print("常规重复项处理已结束。")
    else:
        print("未发现常规重复项。")
    
    # --- 阶段 2: GUI结束后，重新分析文件并生成最终报告 ---
    print("\n--- 阶段 2: 重新分析文件以生成最终报告 ---")
    final_symbol_counts = Counter()
    final_symbol_sources = defaultdict(list)

    # 重新扫描所有文件
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

    # --- 阶段 3: 处理 #BACKUP_DUP ---
    handle_backup_duplicates(directory)

    # --- 阶段 4: 清理空的或仅含 #BACKUP_DUP 的辅助文件 ---
    cleanup_empty_or_backup_only_diff_files(directory)

    # --- 新增：阶段 5: 检查并修正周末日期 ---
    handle_weekend_dates(directory)

    # --- 新增：阶段 6: 整理主文件按日期排序 ---
    sort_all_main_files(directory)
    
    # --- 最终总结 ---
    print("\n所有处理流程已完成。")
    if report_generated:
        show_alert("处理完毕，但仍有手动跳过或内容一致的重复内容，已生成 duplication.txt 报告。")
    else:
        # 修改最终提示信息
        show_alert("所有重复内容已解决，周末日期已修正，且无需清理的文件也已处理完毕。")


if __name__ == "__main__":
    main()