import os
import glob
import subprocess
import sys
from collections import defaultdict, Counter
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame, QSizePolicy, QTextEdit
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

# --- 辅助函数 ---

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
        parts = line_to_insert.split(':')
        if len(parts) < 3:
            print(f"警告: 无法从 '{line_to_insert}' 中解析日期，跳过插入操作。")
            return
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


# --- PyQt5 GUI部分 ---

class DuplicateResolverApp(QWidget):
    def __init__(self, duplicates, symbol_sources, directory):
        super().__init__()
        self.all_duplicates = sorted(duplicates, key=lambda x: (-x[1], x[0])) # (symbol, count)
        self.symbol_sources = symbol_sources
        self.directory = directory
        self.current_duplicate_index = 0
        
        self.main_files, self.aux_files = get_file_paths(self.directory)
        
        # 预处理，自动解决new.txt并分离出手动的任务
        self.manual_duplicates = self._preprocess_and_auto_resolve()

        if not self.manual_duplicates:
            print("\n所有重复项均已自动处理或无需处理。")
            # 使用QTimer延迟关闭，确保日志能被看到
            QTimer.singleShot(100, self.close)
            return

        self.init_ui()
        self.display_current_duplicate()

    def _preprocess_and_auto_resolve(self):
        """
        预处理所有重复项。如果包含new.txt，则自动解决。
        返回需要手动处理的列表。
        """
        manual_tasks = []
        auto_resolved_log = []

        for symbol, count in self.all_duplicates:
            occurrences = self.symbol_sources[symbol]
            new_txt_item = None
            for item in occurrences:
                if item[0] == "Earnings_Release_new.txt":
                    new_txt_item = item
                    break
            
            if new_txt_item:
                # 需求3: 自动处理
                self._perform_resolution(new_txt_item)
                auto_resolved_log.append(f"  - Symbol '{symbol}' 已根据 'Earnings_Release_new.txt' 的条目自动处理。")
            else:
                # 需要手动处理
                manual_tasks.append((symbol, count))

        if auto_resolved_log:
            print("\n--- 自动处理日志 ---")
            for log_entry in auto_resolved_log:
                print(log_entry)
            print("----------------------\n")
            
        return manual_tasks

    def _perform_resolution(self, selected_item):
        """
        执行解决冲突的核心文件操作。
        新规则: 无论选择哪一项，所有其他包含该symbol的条目都将被删除。
        特殊规则: 如果选择的是辅助文件项，则执行“剪切-粘贴”操作。
        """
        selected_filename, _, selected_line_content = selected_item
        symbol = parse_symbol(selected_line_content)
        
        print(f"\n处理 Symbol '{symbol}'，选择的条目: '{selected_line_content.strip()}' (来自: {selected_filename})")

        all_occurrences = self.symbol_sources.get(symbol, [])
        
        # 1. 确定要删除的行
        lines_to_delete_by_file = defaultdict(list)
        for occurrence in all_occurrences:
            # 如果当前项不是被选中的项，则标记为删除
            if occurrence != selected_item:
                occ_filename, _, occ_line_content = occurrence
                lines_to_delete_by_file[occ_filename].append(occ_line_content)

        # 2. 如果选择的是辅助文件项（剪切操作），则原始项本身也需要被删除
        if not is_main_file(selected_filename):
            lines_to_delete_by_file[selected_filename].append(selected_line_content)

        # 3. 执行删除操作
        print(f"  操作: 清理 '{symbol}' 的其他重复项。")
        for filename, contents in lines_to_delete_by_file.items():
            full_path = os.path.join(self.directory, filename)
            remove_specific_lines_from_file(full_path, contents)
            print(f"    - 已从 {filename} 清理 {len(contents)} 个条目。")

        # 4. 如果选择的是辅助文件项，执行“粘贴”操作
        if not is_main_file(selected_filename):
            print(f"  操作: 将所选行插入到匹配日期的一个主文件中。")
            insert_line_into_main_file(selected_line_content, self.main_files)

    def init_ui(self):
        self.setWindowTitle('重复Symbol处理器')
        self.setGeometry(300, 300, 800, 400)

        # 主布局
        self.main_layout = QVBoxLayout(self)

        # 标题标签
        self.title_label = QLabel()
        self.title_label.setFont(QFont('Arial', 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        # 用于显示重复项的滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content_widget)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content_widget)
        self.main_layout.addWidget(self.scroll_area)

        # 底部按钮布局
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
        """清空布局中的所有小部件"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def display_current_duplicate(self):
        if self.current_duplicate_index >= len(self.manual_duplicates):
            self.close()
            return

        # 清空旧内容
        self.clear_layout(self.scroll_layout)
        symbol, count = self.manual_duplicates[self.current_duplicate_index]
        self.title_label.setText(f"手动处理 ({self.current_duplicate_index + 1}/{len(self.manual_duplicates)}): {symbol} ({count} 次)")

        occurrences = self.symbol_sources[symbol]
        
        for item in occurrences:
            filename, lineno, line_content = item

            # 容器行
            line_frame = QFrame()
            line_layout = QHBoxLayout(line_frame)

            # 需求2: 使用QTextEdit替换QLabel以支持文本选择和双击
            item_display = QTextEdit()
            item_display.setReadOnly(True)
            item_display.setText(f"{line_content}\n(来源: {filename}, 第 {lineno} 行)")
            # 设置样式使其看起来像标签，并设置固定高度
            item_display.setStyleSheet("""
                QTextEdit {
                    border: none;
                    background-color: transparent;
                    font-size: 13px;
                }
            """)
            item_display.setFixedHeight(50)
            item_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            # 选择按钮
            select_button = QPushButton('选择')
            select_button.setFixedWidth(100)
            # 使用lambda捕获当前循环的item变量
            select_button.clicked.connect(lambda checked, item_to_process=item: self.resolve_selection(item_to_process))

            line_layout.addWidget(item_display)
            line_layout.addWidget(select_button)
            
            self.scroll_layout.addWidget(line_frame)

    def resolve_selection(self, selected_item):
        """GUI事件：当用户点击'选择'按钮时调用"""
        self._perform_resolution(selected_item)
        self.next_duplicate()

    def skip_duplicate(self):
        symbol, _ = self.manual_duplicates[self.current_duplicate_index]
        print(f"\n用户跳过了对 symbol '{symbol}' 的处理。")
        self.next_duplicate()

    def next_duplicate(self):
        """递增索引并刷新界面"""
        self.current_duplicate_index += 1
        if self.current_duplicate_index < len(self.manual_duplicates):
            self.display_current_duplicate()
        else:
            print("\n所有手动重复项已处理完毕。")
            self.close()

# --- 主程序入口 ---

def main():
    directory = "/Users/yanzhang/Coding/News"
    pattern = os.path.join(directory, "Earnings_Release_*.txt")
    output_path = os.path.join(directory, "duplication.txt")

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
        print("发现重复的 symbols，正在启动交互式处理器...")
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
        
        print("交互式处理已结束。")
    
    # --- GUI结束后，重新分析文件并生成最终报告 ---
    print("重新分析文件以生成最终报告...")
    final_symbol_counts = Counter()
    final_symbol_sources = defaultdict(list)

    # 重新扫描所有文件
    files_after_edit = glob.glob(pattern)
    for path in files_after_edit:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line: continue
                    sym = parse_symbol(line)
                    if not sym: continue
                    final_symbol_counts[sym] += 1
                    final_symbol_sources[sym].append((os.path.basename(path), lineno))
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line: continue
                    sym = parse_symbol(line)
                    if not sym: continue
                    final_symbol_sources[sym].append((os.path.basename(path), lineno))
        except Exception as e:
            print(f"最终分析时无法读取文件 {path}: {e}")

    final_duplicates = {s: c for s, c in final_symbol_counts.items() if c > 1}

    if not final_duplicates:
        show_alert("所有重复内容已解决。")
        # 如果旧的duplication.txt存在，可以考虑删除或清空
        if os.path.exists(output_path):
            os.remove(output_path)
        return

    # 如果仍有重复，生成duplication.txt并弹窗
    lines_out = []
    lines_out.append(f"共解析 symbol 数量：{len(final_symbol_counts)}，总出现次数：{sum(final_symbol_counts.values())}")
    lines_out.append("发现的剩余重复 symbol (手动跳过项):")
    for sym, count in sorted(final_duplicates.items(), key=lambda x: (-x[1], x[0])):
        lines_out.append(f"- {sym}: {count} 次")
        for src_file, lineno in final_symbol_sources[sym]:
            lines_out.append(f"  · {src_file}: 第 {lineno} 行")

    # 将结果写入文件
    with open(output_path, "w", encoding="utf-8") as fw:
        fw.write("\n".join(lines_out) + "\n")

    show_alert("处理完毕，但仍有手动跳过的重复内容，已生成 duplication.txt 报告。")


if __name__ == "__main__":
    main()