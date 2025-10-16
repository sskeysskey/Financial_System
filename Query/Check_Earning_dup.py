import os
import glob
import subprocess
import sys
from collections import defaultdict, Counter
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame, QSizePolicy
from PyQt5.QtCore import Qt
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

def modify_file_content(filepath: str, symbol_to_remove: str):
    """读取文件，删除包含指定symbol的行，然后写回"""
    try:
        lines_to_keep = []
        # 尝试用utf-8解码，失败则用latin-1
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='latin-1') as f:
                lines = f.readlines()

        for line in lines:
            line_symbol = parse_symbol(line)
            if line_symbol != symbol_to_remove:
                lines_to_keep.append(line)

        # 写回文件，确保行与行之间只有一个换行符
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines_to_keep)
            
    except Exception as e:
        print(f"修改文件 {filepath} 时出错: {e}")

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
        self.duplicates = sorted(duplicates, key=lambda x: (-x[1], x[0])) # (symbol, count)
        self.symbol_sources = symbol_sources
        self.directory = directory
        self.current_duplicate_index = 0
        
        self.main_files, self.aux_files = get_file_paths(self.directory)

        self.init_ui()
        self.display_current_duplicate()

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
        """显示当前索引指向的重复Symbol信息"""
        if self.current_duplicate_index >= len(self.duplicates):
            self.close()
            return

        # 清空旧内容
        self.clear_layout(self.scroll_layout)

        symbol, count = self.duplicates[self.current_duplicate_index]
        self.title_label.setText(f"处理中 ({self.current_duplicate_index + 1}/{len(self.duplicates)}): {symbol} ({count} 次)")

        occurrences = self.symbol_sources[symbol]
        
        for item in occurrences:
            filename, lineno, line_content = item

            # 容器行
            line_frame = QFrame()
            line_layout = QHBoxLayout(line_frame)

            # 标签显示内容
            item_label = QLabel(f"{line_content}\n(来源: {filename}, 第 {lineno} 行)")
            item_label.setWordWrap(True)
            item_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            
            # 选择按钮
            select_button = QPushButton('选择')
            select_button.setFixedWidth(100)
            # 使用lambda捕获当前循环的item变量
            select_button.clicked.connect(lambda checked, item_to_process=item: self.resolve_selection(item_to_process))

            line_layout.addWidget(item_label)
            line_layout.addWidget(select_button)
            
            self.scroll_layout.addWidget(line_frame)

    def resolve_selection(self, selected_item):
        """核心处理逻辑，当用户点击'选择'按钮时调用"""
        selected_filename, _, selected_line_content = selected_item
        symbol = parse_symbol(selected_line_content)
        
        print(f"\n用户选择了: '{selected_line_content.strip()}' 来自文件 '{selected_filename}'")

        if is_main_file(selected_filename):
            # 情况1: 选择的是主文件中的行
            # -> 删除所有辅助文件中的该symbol
            print(f"检测到选择的是主文件。将在所有辅助文件中删除 symbol '{symbol}'...")
            for aux_file_path in self.aux_files:
                modify_file_content(aux_file_path, symbol)
                print(f"  - 已检查并处理文件: {os.path.basename(aux_file_path)}")

        else:
            # 情况2: 选择的是辅助文件中的行
            # -> 删除所有主文件中的该symbol
            print(f"检测到选择的是辅助文件。将在所有主文件中删除 symbol '{symbol}'...")
            for main_file_path in self.main_files:
                modify_file_content(main_file_path, symbol)
                print(f"  - 已检查并处理文件: {os.path.basename(main_file_path)}")
            
            # -> 将选择的行插入到日期匹配的主文件中
            print(f"准备将行 '{selected_line_content.strip()}' 插入到对应的主文件中...")
            insert_line_into_main_file(selected_line_content, self.main_files)

        # 移动到下一个重复项
        self.next_duplicate()

    def skip_duplicate(self):
        """跳过当前symbol，处理下一个"""
        symbol, _ = self.duplicates[self.current_duplicate_index]
        print(f"\n用户跳过了对 symbol '{symbol}' 的处理。")
        self.next_duplicate()

    def next_duplicate(self):
        """递增索引并刷新界面"""
        self.current_duplicate_index += 1
        if self.current_duplicate_index < len(self.duplicates):
            self.display_current_duplicate()
        else:
            print("\n所有重复项已处理完毕。")
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
                print(f"无法读取文件 {path}: {e}")

    duplicates_dict = {s: c for s, c in symbol_counts.items() if c > 1}

    # 如果有重复项，启动GUI进行交互式处理
    if duplicates_dict:
        print("发现重复的 symbols，正在启动交互式处理器...")
        app = QApplication(sys.argv)
        # 将字典转换为元组列表
        duplicates_list = list(duplicates_dict.items())
        resolver_app = DuplicateResolverApp(duplicates_list, symbol_sources, directory)
        resolver_app.show()
        app.exec_()
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
    lines_out.append("发现的剩余重复 symbol：")
    for sym, count in sorted(final_duplicates.items(), key=lambda x: (-x[1], x[0])):
        lines_out.append(f"- {sym}: {count} 次")
        for src_file, lineno in final_symbol_sources[sym]:
            lines_out.append(f"  · {src_file}: 第 {lineno} 行")

    # 将结果写入文件
    with open(output_path, "w", encoding="utf-8") as fw:
        fw.write("\n".join(lines_out) + "\n")

    show_alert("处理完毕，但仍有重复内容，已生成 duplication.txt 报告。")


if __name__ == "__main__":
    main()