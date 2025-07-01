import json
import argparse
import sys
import os
from tkinter import Tk, Frame, Label, Entry, Text, Button, Scrollbar, Canvas, Toplevel
try:
    import pyperclip
except ImportError:
    pyperclip = None

# 您的JSON文件路径
# 请确保这个路径是正确的，或者根据您的实际情况修改
JSON_FILE_PATH = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"

class DescriptionEditor:
    """
    一个用于编辑 description3 字段的 Tkinter GUI 窗口。
    """
    def __init__(self, master, item_data, save_callback):
        """
        初始化编辑器窗口。

        :param master: Tkinter 的主窗口或 Toplevel 窗口。
        :param item_data: 要编辑的股票或ETF项目字典。
        :param save_callback: 保存数据时要调用的函数。
        """
        self.master = master
        self.item_data = item_data
        self.save_callback = save_callback
        
        # 从 description3 字段提取数据。
        # 它的结构是 [{ "date": "text", ... }]，我们只处理第一个字典。
        if self.item_data.get('description3') and isinstance(self.item_data['description3'], list) and len(self.item_data['description3']) > 0:
            self.descriptions = self.item_data['description3'][0]
        else:
            self.descriptions = {}

        self.master.title(f"编辑 {self.item_data.get('symbol', 'N/A')} 的 Description3")
        # 设置窗口关闭事件
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # --- 创建可滚动的区域 ---
        main_frame = Frame(self.master)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        canvas = Canvas(main_frame)
        scrollbar = Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 存放每一行输入控件的列表
        self.entry_widgets = []
        self._populate_entries()

        # --- 底部控制按钮 ---
        button_frame = Frame(self.master)
        button_frame.pack(fill='x', padx=10, pady=(0, 10))

        add_button = Button(button_frame, text="添加新记录", command=self._add_new_entry)
        add_button.pack(side='left', padx=5)

        save_button = Button(button_frame, text="保存并关闭", command=self._on_save, bg="#4CAF50", fg="white")
        save_button.pack(side='right', padx=5)

    def _populate_entries(self):
        """用当前的 description 数据填充滚动区域内的控件。"""
        # 清空旧的控件
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.entry_widgets.clear()

        # 为每条记录创建控件
        sorted_dates = sorted(self.descriptions.keys(), reverse=True)
        for date_str in sorted_dates:
            text_str = self.descriptions[date_str]
            self._create_entry_row(date_str, text_str)

    def _create_entry_row(self, date_str, text_str):
        """为单条记录创建一行编辑控件。"""
        row_frame = Frame(self.scrollable_frame, bd=2, relief="groove", padx=5, pady=5)
        row_frame.pack(fill='x', expand=True, pady=5)

        # 日期部分
        date_label = Label(row_frame, text="日期 (YYYY-MM-DD):")
        date_label.pack(anchor='w')
        date_entry = Entry(row_frame, width=50)
        date_entry.insert(0, date_str)
        date_entry.pack(fill='x', expand=True, pady=(0, 5))

        # 内容部分
        desc_label = Label(row_frame, text="内容:")
        desc_label.pack(anchor='w')
        # 使用 Text 控件以支持多行文本编辑
        text_widget = Text(row_frame, height=4, wrap='word')
        text_widget.insert('1.0', text_str)
        text_widget.pack(fill='x', expand=True)

        # 删除按钮
        delete_button = Button(row_frame, text="删除此条记录", command=lambda f=row_frame: self._delete_entry(f), bg="#f44336", fg="white")
        delete_button.pack(anchor='e', pady=5)
        
        # 将控件和框架保存起来，以便后续读取或删除
        self.entry_widgets.append({
            'frame': row_frame,
            'date': date_entry,
            'text': text_widget
        })

    def _add_new_entry(self):
        """在界面上添加一组新的、空白的输入框。"""
        self._create_entry_row("YYYY-MM-DD", "请在此处输入新内容...")

    def _delete_entry(self, frame_to_delete):
        """删除指定框架对应的记录。"""
        # 找到要删除的控件组
        widget_to_remove = None
        for widgets in self.entry_widgets:
            if widgets['frame'] == frame_to_delete:
                widget_to_remove = widgets
                break
        
        if widget_to_remove:
            self.entry_widgets.remove(widget_to_remove)
            frame_to_delete.destroy()

    def _on_save(self):
        """收集所有输入框的数据，并调用回调函数进行保存。"""
        new_descriptions = {}
        for widgets in self.entry_widgets:
            date_str = widgets['date'].get().strip()
            # Text控件获取内容的方式是 .get('1.0', 'end-1c')
            # '1.0' 表示第一行第0个字符，'end-1c' 表示结尾再减去一个字符（Tkinter会自动加一个换行符）
            text_str = widgets['text'].get('1.0', 'end-1c').strip()

            if date_str and text_str: # 确保日期和内容都不为空
                new_descriptions[date_str] = text_str
        
        # 更新原始数据结构
        self.item_data['description3'] = [new_descriptions]
        
        # 调用主程序中的保存函数
        self.save_callback()
        
        # 关闭窗口
        self.master.destroy()

    def _on_closing(self):
        """处理直接点击关闭按钮的事件，避免未保存的更改丢失。"""
        # 在这里可以添加一个确认对话框，为了简化，我们直接关闭
        print("窗口已关闭，未保存任何更改。")
        self.master.destroy()


def load_data(file_path):
    """从JSON文件加载数据。"""
    if not os.path.exists(file_path):
        print(f"错误: JSON文件未找到于路径 '{file_path}'")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"错误: JSON文件 '{file_path}' 格式无效。")
        return None
    except Exception as e:
        print(f"读取文件时发生未知错误: {e}")
        return None

def save_data(file_path, data):
    """将数据保存到JSON文件。"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            # ensure_ascii=False 保证中文字符正确写入
            # indent=2 使JSON文件格式化，易于阅读
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"数据已成功保存到 '{file_path}'")
    except Exception as e:
        print(f"保存文件时发生错误: {e}")

def find_item(symbol, data):
    """在stocks和etfs列表中查找指定的symbol。"""
    for group_key in ['stocks', 'etfs']:
        if group_key in data:
            for item in data[group_key]:
                if item.get('symbol') == symbol:
                    return item
    return None

def main():
    """主执行函数。"""
    parser = argparse.ArgumentParser(description="编辑金融JSON文件中指定symbol的description3字段。")
    parser.add_argument("-s", "--symbol", type=str, help="要编辑的股票或ETF的symbol。")
    args = parser.parse_args()

    symbol = args.symbol

    # 如果未通过参数提供symbol，则尝试从剪贴板获取
    if not symbol:
        if pyperclip:
            try:
                clipboard_content = pyperclip.paste().strip()
                if clipboard_content:
                    print(f"从剪贴板获取到 Symbol: '{clipboard_content}'")
                    symbol = clipboard_content
                else:
                    print("剪贴板为空。")
            except pyperclip.PyperclipException as e:
                print(f"无法访问剪贴板: {e}. 请使用 -s 参数提供 symbol。")
        else:
            print("Pyperclip 库未安装，无法从剪贴板获取。请使用 -s 参数提供 symbol。")

    if not symbol:
        parser.print_help()
        sys.exit(1)

    # 加载数据
    all_data = load_data(JSON_FILE_PATH)
    if all_data is None:
        sys.exit(1)

    # 查找项目
    item_to_edit = find_item(symbol, all_data)

    if item_to_edit:
        # 创建 Tkinter 主窗口并启动编辑器
        root = Tk()
        # 将主窗口隐藏，只显示我们的编辑器对话框
        root.withdraw() 
        
        # 创建一个 Toplevel 窗口作为我们的编辑器
        editor_window = Toplevel(root)

        # 定义保存操作
        def on_save_action():
            save_data(JSON_FILE_PATH, all_data)

        app = DescriptionEditor(editor_window, item_to_edit, on_save_action)
        
        # 运行 Tkinter 事件循环
        root.mainloop()
    else:
        print(f"错误: 在 'stocks' 或 'etfs' 组中未找到 Symbol '{symbol}'。")
        sys.exit(1)

if __name__ == "__main__":
    main()