import json
import sys
import os
import pyperclip
import tkinter as tk
from tkinter import messagebox, Text, Entry, Checkbutton, Button, Frame, Scrollbar, Canvas, BooleanVar, simpledialog

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
    获取 symbol，优先从命令行参数获取，其次从剪贴板获取，如果都没有，则弹框手动输入。
    """
    # 途径1：命令行参数
    if len(sys.argv) > 1:
        sym = sys.argv[1].strip()
        if sym:
            print(f"从命令行参数获取 Symbol: {sym}")
            return sym

    # 途径2：剪贴板
    try:
        raw = pyperclip.paste()
    except pyperclip.PyperclipException:
        raw = None

    if raw:
        sym = raw.strip()
        if sym:
            print(f"从剪贴板获取 Symbol: {sym}")
            return sym

    # 途径3：弹框手动输入
    # 这里需要先创建一个临时的 Tk 窗口来承载对话框
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    sym = simpledialog.askstring(
        "输入 Symbol",
        "未检测到命令行参数或剪贴板内容。\n请输入股票/ETF 的 Symbol：",
        parent=root
    )
    root.destroy()

    if sym:
        return sym.strip()
    else:
        return None

def find_item_by_symbol(data, symbol):
    """在stocks和etfs中根据symbol（不区分大小写）查找对应的项目。"""
    if not data or not symbol:
        return None
    target = symbol.lower()
    for group_key in ['stocks', 'etfs']:
        for item in data.get(group_key, []):
            if item.get('symbol', '').lower() == target:
                # 确保 description3 存在且是一列表内 dict
                if 'description3' not in item or not item['description3']:
                    item['description3'] = [{}]
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

        # --- 新增: 为“全选”复选框创建变量 ---
        self.select_all_var = BooleanVar()

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

        # --- 新增: "复制到..." 按钮 ---
        self.copy_button = Button(button_frame, text="复制到...", command=self._copy_to_symbols)
        self.copy_button.pack(side=tk.RIGHT, padx=10)

        self.delete_button = Button(button_frame, text="删除选中项", command=self._delete_selected)
        self.delete_button.pack(side=tk.RIGHT, padx=10)
        
        self.add_button = Button(button_frame, text="添加新条目", command=self._add_new_row)
        self.add_button.pack(side=tk.LEFT, padx=10)

    # --- 新增: 全选/全不选 功能函数 ---
    def _toggle_select_all(self):
        """
        根据“全选”复选框的状态，设置所有条目的复选框状态。
        """
        is_checked = self.select_all_var.get()
        for row in self.rows:
            row['check_var'].set(is_checked)

    # --- 新增: 更新“全选”复选框状态的函数 ---
    def _update_select_all_state(self):
        """
        检查是否所有条目都被选中，并相应地更新“全选”复选框。
        """
        if not self.rows: # 如果没有条目，则全选框不勾选
            self.select_all_var.set(False)
            return
            
        all_checked = all(row['check_var'].get() for row in self.rows)
        self.select_all_var.set(all_checked)

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
        
        # --- 修改: 将表头复选框与变量和命令关联 ---
        header_checkbutton = Checkbutton(header_frame, variable=self.select_all_var, command=self._toggle_select_all)
        header_checkbutton.grid(row=0, column=0, padx=5)
        
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
            # --- 修改: 为每个复选框添加命令，以便在点击时更新“全选”框的状态 ---
            checkbutton = Checkbutton(row_frame, variable=check_var, command=self._update_select_all_state)
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
        
        # --- 新增: 创建完所有控件后，更新一次“全选”框的初始状态 ---
        self._update_select_all_state()

    def _add_new_row(self):
        """在界面上添加一个空的新行，用于创建新条目。"""
        i = len(self.rows) + 1 # 新行号
        row_frame = Frame(self.scrollable_frame)
        row_frame.grid(row=i, column=0, sticky="ew", padx=5, pady=2)
        row_frame.grid_columnconfigure(2, weight=1)

        check_var = BooleanVar()
        # --- 修改: 新增的复选框也需要关联更新函数 ---
        checkbutton = Checkbutton(row_frame, variable=check_var, command=self._update_select_all_state)
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
        
        # --- 新增: 添加新行后，由于新行默认未选中，需要更新“全选”框的状态 ---
        self._update_select_all_state()


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

    # --- 新增: "复制到..." 功能的实现 ---
    def _copy_to_symbols(self):
        """将选中的条目复制到其他一个或多个symbol中。"""
        # 1. 收集所有选中的条目
        items_to_copy = []
        for row in self.rows:
            if row['check_var'].get():
                date = row['date_entry'].get().strip()
                desc = row['desc_text'].get("1.0", "end-1c").strip()
                if date and date != "YYYY-MM-DD" and desc:
                    items_to_copy.append({'date': date, 'desc': desc})
        
        if not items_to_copy:
            messagebox.showinfo("提示", "没有选中任何有效的条目进行复制。")
            return

        # 2. 弹出对话框让用户输入目标symbols
        # 使用 simpledialog 获取用户输入
        target_symbols_str = simpledialog.askstring(
            "复制到...",
            "请输入目标Symbol (多个Symbol请用空格分隔):",
            parent=self.master
        )

        if not target_symbols_str:
            return # 用户取消或未输入

        target_symbols = target_symbols_str.strip().split()
        if not target_symbols:
            return

        # 3. 执行复制操作
        successful_copies = []
        failed_symbols = []
        
        for symbol in target_symbols:
            # 查找目标item
            target_item = find_item_by_symbol(self.full_data, symbol)
            
            if target_item:
                # 获取目标item的description3字典
                # find_item_by_symbol确保了description3的基本结构
                target_events_dict = target_item['description3'][0]
                
                # 将选中的条目逐一添加到目标字典中（如果已存在则覆盖）
                for item in items_to_copy:
                    target_events_dict[item['date']] = item['desc']
                
                successful_copies.append(target_item['symbol'])
            else:
                failed_symbols.append(symbol)

        # 4. 保存所有更改到JSON文件
        if successful_copies:
            if not save_data(self.full_data):
                # 如果保存失败，save_data内部会显示错误，这里可以提前返回
                messagebox.showerror("复制失败", "数据已在内存中修改，但保存到文件时失败。")
                return
        
        # 5. 构建并显示最终结果报告
        report_message = ""
        if successful_copies:
            report_message += f"成功将 {len(items_to_copy)} 个条目复制到: \n" + ", ".join(successful_copies)
        
        if failed_symbols:
            if report_message:
                report_message += "\n\n"
            report_message += "未在JSON文件中找到以下Symbol: \n" + ", ".join(failed_symbols)

        messagebox.showinfo("复制操作完成", report_message)


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

            # messagebox.showinfo("成功", "所有更改已成功保存到JSON文件！")
            # 保存成功后刷新界面，以确保排序和状态正确
            self._create_widgets()
        else:
            messagebox.showerror("失败", "保存文件时发生错误，请检查控制台输出。")

# --- 主程序入口 ---

def main():
    # 1. 尝试拿命令行/剪贴板初始 symbol
    symbol = get_symbol_from_input()

    # 2. 加载JSON数据
    full_data = load_data()
    if full_data is None:
        return

    # 3. 创一个隐藏的 Tk，用来弹出输入对话框
    hidden_root = tk.Tk()
    hidden_root.withdraw()

    # 4. 先试第一次查找
    item_data = find_item_by_symbol(full_data, symbol) if symbol else None

    # 5. 如果没找到，就循环让用户输入
    while item_data is None:
        prompt = "未在 JSON 中找到 Symbol：" \
                 f"'{symbol}'。\n请重新输入要编辑的 Symbol：" \
                 "\n（取消则退出）"
        symbol = simpledialog.askstring("输入 Symbol", prompt, parent=hidden_root)
        if not symbol:
            # 用户按了 取消 或者输入空
            messagebox.showinfo("已取消", "未指定合法的 Symbol，程序退出。", parent=hidden_root)
            hidden_root.destroy()
            return
        # 再次查找
        item_data = find_item_by_symbol(full_data, symbol)

    # 6. 找到后，把 JSON 里原始的大小写 symbol 也读出来
    symbol = item_data['symbol']

    # 7. 销毁隐藏窗口，启动真正的主窗口
    hidden_root.destroy()

    root = tk.Tk()
    # ESC 关闭快捷键
    root.bind('<Escape>', lambda e: root.destroy())

    root.lift()
    root.focus_force()
    DescriptionEditorApp(root, full_data, item_data)
    root.mainloop()


if __name__ == "__main__":
    main()