import json
import sys
import os
import pyperclip
import tkinter as tk
from tkinter import messagebox, Text, Entry, Checkbutton, Button, Frame, Scrollbar, Canvas, BooleanVar

# --- 核心功能函数 ---

# JSON文件的固定路径
# 请确保此路径是正确的，如果脚本和json文件不在同一目录，建议使用绝对路径。
JSON_FILE_PATH = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'

def load_data():
    """从JSON文件加载数据，如果文件不存在或为空则返回一个空模板。"""
    if not os.path.exists(JSON_FILE_PATH):
        messagebox.showerror("错误", f"JSON文件未找到: {JSON_FILE_PATH}")
        return None
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        messagebox.showerror("加载错误", f"无法加载或解析JSON文件: {e}")
        return None

def save_data(data):
    """将数据保存回JSON文件。"""
    try:
        with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
            # indent=2 和 ensure_ascii=False 让JSON文件格式更美观且支持中文
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        messagebox.showerror("保存错误", f"无法保存文件: {e}")
        return False

def get_symbol_from_input():
    """
    获取symbol，优先从命令行参数获取，其次从剪贴板获取。
    """
    # 途径2：从命令行参数获取
    if len(sys.argv) > 1:
        print(f"从命令行参数获取 Symbol: {sys.argv[1]}")
        return sys.argv[1].strip()
    
    # 途径1：从剪贴板获取
    try:
        symbol = pyperclip.paste().strip()
        if symbol:
            print(f"从剪贴板获取 Symbol: {symbol}")
            return symbol
    except pyperclip.PyperclipException:
        messagebox.showwarning("警告", "无法访问剪贴板。请手动输入或使用命令行参数。")
    
    return None

def find_item_by_symbol(data, symbol):
    """在stocks和etfs中根据symbol查找对应的项目。"""
    if not data or not symbol:
        return None
        
    for group_key in ['stocks', 'etfs']:
        if group_key in data:
            for item in data[group_key]:
                if item.get('symbol') == symbol:
                    # 确保description3字段存在且是特定格式
                    if 'description3' not in item:
                        item['description3'] = [{}]
                    elif not item['description3']: # 如果是空列表
                        item['description3'].append({})
                    return item
    return None

# --- 图形用户界面 (GUI) ---

class DescriptionEditorApp:
    def __init__(self, master, full_data, item_data):
        self.master = master
        self.full_data = full_data
        self.item_data = item_data
        
        # 从item_data中获取事件字典。
        # JSON结构是 [{"date": "desc"}]，所以我们取第一个元素。
        self.events_dict = self.item_data.get('description3', [{}])[0]

        self.master.title(f"编辑 {self.item_data.get('symbol', '')} 的 Description3")
        self.master.geometry("800x600")

        # --- 创建主框架和滚动条 ---
        main_frame = Frame(master)
        main_frame.pack(fill=tk.BOTH, expand=1)

        canvas = Canvas(main_frame)
        scrollbar = Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # --- 创建控件 ---
        self.rows = []
        self._create_widgets()

        # --- 底部按钮 ---
        button_frame = Frame(master)
        button_frame.pack(fill=tk.X, pady=10)

        self.save_button = Button(button_frame, text="保存所有更改", command=self._save_changes)
        self.save_button.pack(side=tk.RIGHT, padx=10)

        self.delete_button = Button(button_frame, text="删除选中项", command=self._delete_selected)
        self.delete_button.pack(side=tk.RIGHT, padx=10)
        
        self.add_button = Button(button_frame, text="添加新条目", command=self._add_new_row)
        self.add_button.pack(side=tk.LEFT, padx=10)


    def _create_widgets(self):
        """根据events_dict动态创建界面元素。"""
        # 清理旧的控件
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.rows = []

        # 按日期降序排序
        sorted_events = sorted(self.events_dict.items(), key=lambda item: item[0], reverse=True)

        # 创建表头
        header_frame = Frame(self.scrollable_frame)
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        Checkbutton(header_frame).grid(row=0, column=0, padx=5)
        tk.Label(header_frame, text="日期 (YYYY-MM-DD)", font=('Helvetica', 10, 'bold')).grid(row=0, column=1, padx=5)
        tk.Label(header_frame, text="内容描述", font=('Helvetica', 10, 'bold')).grid(row=0, column=2, padx=5)
        self.scrollable_frame.grid_columnconfigure(2, weight=1) # 让内容列自适应宽度

        # 为每个事件创建一行
        for i, (date_key, description) in enumerate(sorted_events, start=1):
            row_frame = Frame(self.scrollable_frame)
            row_frame.grid(row=i, column=0, sticky="ew", padx=5, pady=2)
            row_frame.grid_columnconfigure(2, weight=1)

            # 1. 复选框
            check_var = BooleanVar()
            checkbutton = Checkbutton(row_frame, variable=check_var)
            checkbutton.grid(row=0, column=0, padx=5)

            # 2. 日期输入框
            date_entry = Entry(row_frame, width=15)
            date_entry.insert(0, date_key)
            date_entry.grid(row=0, column=1, padx=5)

            # 3. 内容文本框
            desc_text = Text(row_frame, height=4, width=60, wrap=tk.WORD)
            desc_text.insert("1.0", description)
            desc_text.grid(row=0, column=2, sticky="ew", padx=5)

            # 保存对所有控件的引用
            self.rows.append({
                'check_var': check_var,
                'date_entry': date_entry,
                'desc_text': desc_text,
                'original_date': date_key # 记录原始日期，以便在日期被修改时也能找到原条目
            })

    def _add_new_row(self):
        """在界面上添加一个空的新行，用于创建新条目。"""
        i = len(self.rows) + 1 # 新行号
        row_frame = Frame(self.scrollable_frame)
        row_frame.grid(row=i, column=0, sticky="ew", padx=5, pady=2)
        row_frame.grid_columnconfigure(2, weight=1)

        check_var = BooleanVar()
        checkbutton = Checkbutton(row_frame, variable=check_var)
        checkbutton.grid(row=0, column=0, padx=5)

        date_entry = Entry(row_frame, width=15)
        date_entry.insert(0, "YYYY-MM-DD")
        date_entry.grid(row=0, column=1, padx=5)

        desc_text = Text(row_frame, height=4, width=60, wrap=tk.WORD)
        desc_text.insert("1.0", "请在此输入内容...")
        desc_text.grid(row=0, column=2, sticky="ew", padx=5)

        self.rows.append({
            'check_var': check_var,
            'date_entry': date_entry,
            'desc_text': desc_text,
            'original_date': None # 这是一个新条目
        })


    def _delete_selected(self):
        """删除所有选中的条目。"""
        # 找出需要删除的原始日期
        keys_to_delete = [
            row['original_date'] 
            for row in self.rows 
            if row['check_var'].get() and row['original_date'] is not None
        ]

        if not keys_to_delete:
            messagebox.showinfo("提示", "没有选中任何要删除的条目。")
            return

        if messagebox.askyesno("确认删除", f"确定要删除选中的 {len(keys_to_delete)} 个条目吗？此操作将直接修改内存中的数据。"):
            # 从 self.events_dict 中删除
            for key in keys_to_delete:
                if key in self.events_dict:
                    del self.events_dict[key]
            
            # 重建UI
            self._create_widgets()
            messagebox.showinfo("成功", "选中的条目已从界面移除。\n请点击'保存所有更改'以更新JSON文件。")


    def _save_changes(self):
        """将界面上的所有更改同步到数据结构并保存到文件。"""
        new_events_dict = {}
        for row in self.rows:
            date_key = row['date_entry'].get().strip()
            # The get method for Text widgets needs two arguments: start and end index.
            # "1.0" means line 1, character 0. "end-1c" means the end minus one character (the trailing newline).
            description = row['desc_text'].get("1.0", "end-1c").strip()
            
            if not date_key or date_key == "YYYY-MM-DD":
                continue # 跳过无效或未填写的条目

            if date_key in new_events_dict:
                messagebox.showwarning("警告", f"日期 '{date_key}' 重复，只有最后一个会被保存。")

            new_events_dict[date_key] = description
        
        # 更新 self.item_data 中的 description3 字段
        self.item_data['description3'] = [new_events_dict]
        
        # 调用主函数中的保存方法来保存整个文件
        if save_data(self.full_data):
            # 更新 self.events_dict 和 original_date 以便后续操作
            self.events_dict = new_events_dict
            for row in self.rows:
                row['original_date'] = row['date_entry'].get().strip()

            messagebox.showinfo("成功", "所有更改已成功保存到JSON文件！")
            # 保存成功后刷新界面，以确保排序和状态正确
            self._create_widgets()
        else:
            messagebox.showerror("失败", "保存文件时发生错误，请检查控制台输出。")

# --- 主程序入口 ---

def main():
    """程序主逻辑。"""
    # 1. 获取Symbol
    symbol = get_symbol_from_input()
    if not symbol:
        messagebox.showerror("错误", "未能获取到有效的Symbol。\n请确保剪贴板内容正确，或通过命令行参数提供。")
        return

    # 2. 加载JSON数据
    full_data = load_data()
    if full_data is None:
        return

    # 3. 查找对应的项目
    item_data = find_item_by_symbol(full_data, symbol)
    if item_data is None:
        messagebox.showerror("未找到", f"在JSON文件中未找到Symbol为 '{symbol}' 的项目。")
        return

    # 4. 启动GUI应用
    root = tk.Tk()
    root.lift()
    root.attributes('-topmost', True)
    root.focus_force()
    app = DescriptionEditorApp(root, full_data, item_data)
    root.mainloop()


if __name__ == "__main__":
    main()