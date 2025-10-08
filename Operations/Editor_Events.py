import json
import sys
import os
import pyperclip
import tkinter as tk
from tkinter import messagebox, Text, Entry, Checkbutton, Button, Frame, Scrollbar, Canvas, BooleanVar, simpledialog

# 请确保此路径是正确的，如果脚本和json文件不在同一目录，建议使用绝对路径。
JSON_FILE_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'

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
    # --- 新增: 移植b.py的Nord风格颜色主题 ---
    COLORS = {
        'bg_dark': '#2E3440',
        'bg_medium': '#3B4252',
        'fg_light': '#ECEFF4',
        'border': '#4C566A',
        'select_bg': '#5E81AC',
        'save_bg': '#A3BE8C',
        'delete_bg': '#BF616A',
        'text_main': '#D8DEE9',
    }

    def __init__(self, master, full_data, item_data):
        self.master = master
        self.full_data = full_data
        self.item_data = item_data
        
        self.events_dict = self.item_data.get('description3', [{}])[0]

        # --- 修改: 调整窗口标题、尺寸和位置 ---
        self.master.title(f"事件编辑器 - {self.item_data.get('symbol', '')}")
        # 格式: "宽x高+X坐标+Y坐标"
        self.master.geometry("700x750+800+0") 
        self.master.configure(bg=self.COLORS['bg_dark'])
        # 防止窗口大小被内部组件撑开
        self.master.pack_propagate(False)

        self.select_all_var = BooleanVar()

        # --- 创建主框架和滚动条 ---
        main_frame = Frame(master, bg=self.COLORS['bg_dark'])
        main_frame.pack(fill=tk.BOTH, expand=1, padx=10, pady=10)

        self.canvas = Canvas(main_frame, bg=self.COLORS['bg_dark'], highlightthickness=0)
        
        # --- 修改: 为滚动条应用样式 ---
        scrollbar = Scrollbar(main_frame, orient="vertical", command=self.canvas.yview,
                              bg=self.COLORS['bg_dark'], 
                              troughcolor=self.COLORS['bg_medium'],
                              activebackground=self.COLORS['select_bg'],
                              borderwidth=0,
                              highlightthickness=0)
                              
        self.scrollable_frame = Frame(self.canvas, bg=self.COLORS['bg_dark'])

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # --- 新增: 绑定触摸板滚动事件 ---
        self.master.bind_all("<MouseWheel>", self._on_mousewheel)

        # --- 新增: 绑定快捷键 C/c 触发“复制到...” ---
        self.master.bind_all("<Key>", self._on_keypress)

        self.rows = []
        self._create_widgets()

        # --- 底部按钮 ---
        button_frame = Frame(master, bg=self.COLORS['bg_dark'])
        button_frame.pack(fill=tk.X, pady=(0, 10), padx=10)

        # --- 修改: 为所有按钮应用新样式 ---
        btn_style = {
            'fg': self.COLORS['bg_dark'],
            'activeforeground': self.COLORS['fg_light'],
            'font': ('Helvetica', 18),
            'borderwidth': 0,
            'relief': tk.FLAT,
            'pady': 8,
            'padx': 15
        }

        self.copy_button = Button(button_frame, text="复制到...", command=self._copy_to_symbols, 
                                  bg=self.COLORS['border'], activebackground=self.COLORS['select_bg'], **btn_style)
        self.copy_button.pack(side=tk.LEFT, padx=(0, 10))

        self.add_button = Button(button_frame, text="添加新条目", command=self._add_new_row,
                                 bg=self.COLORS['border'], activebackground=self.COLORS['select_bg'], **btn_style)
        self.add_button.pack(side=tk.LEFT)

        self.save_button = Button(button_frame, text="保存所有更改", command=self._save_changes,
                                  bg=self.COLORS['save_bg'], activebackground='#B4D39C', **btn_style)
        self.save_button.pack(side=tk.RIGHT)

        self.delete_button = Button(button_frame, text="删除选中项", command=self._delete_selected,
                                    bg=self.COLORS['delete_bg'], activebackground='#D08770', **btn_style)
        self.delete_button.pack(side=tk.RIGHT, padx=(0, 10))

    # --- 新增: 判断是否为文本输入类控件 ---
    def _is_text_input_widget(self, widget):
        # 在 Entry 或 Text 聚焦时，认为处于输入状态
        import tkinter as tk
        return isinstance(widget, (tk.Entry, tk.Text))

    # --- 新增: 处理全局按键，按 C/c 触发复制 ---
    def _on_keypress(self, event):
        # 仅当不在输入状态时生效
        focused = self.master.focus_get()
        if self._is_text_input_widget(focused):
            return
        # 过滤组合键，确保是单独的字母键
        if event.state & (0x0004 | 0x0001 | 0x0008 | 0x0002):
            # 有 Ctrl/Shift/Alt/Meta 修饰则忽略（按需调整）
            return
        if event.char in ('c', 'C'):
            # 执行与点击“复制到...”按钮相同的逻辑
            self._copy_to_symbols()
    # --- 新增: 触摸板滚动处理函数 ---
    def _on_mousewheel(self, event):
        """处理鼠标滚轮和触摸板滚动事件。"""
        # event.delta 在 macOS 上通常是 1 或 -1，在 Windows 上是 120 的倍数
        # Tkinter 的 yview_scroll 单位是 "units" (行) 或 "pages"
        # 负号用于反转滚动方向以符合自然滚动
        self.canvas.yview_scroll(int(-1 * (event.delta)), "units")

    def _toggle_select_all(self):
        is_checked = self.select_all_var.get()
        for row in self.rows:
            row['check_var'].set(is_checked)

    def _update_select_all_state(self):
        if not self.rows:
            self.select_all_var.set(False)
            return
        all_checked = all(row['check_var'].get() for row in self.rows)
        self.select_all_var.set(all_checked)

    def _create_widgets(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.rows = []

        sorted_events = sorted(self.events_dict.items(), key=lambda item: item[0], reverse=True)

        header_frame = Frame(self.scrollable_frame, bg=self.COLORS['bg_dark'])
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 10))
        
        # --- 修改: 为表头控件应用样式 ---
        header_checkbutton = Checkbutton(header_frame, variable=self.select_all_var, command=self._toggle_select_all,
                                         bg=self.COLORS['bg_dark'], activebackground=self.COLORS['bg_dark'],
                                         highlightthickness=0, selectcolor=self.COLORS['bg_medium'])
        header_checkbutton.grid(row=0, column=0, padx=5)
        
        tk.Label(header_frame, text="日期 (YYYY-MM-DD)", font=('Helvetica', 12, 'bold'), 
                 bg=self.COLORS['bg_dark'], fg=self.COLORS['text_main']).grid(row=0, column=1, padx=5)
        tk.Label(header_frame, text="内容描述", font=('Helvetica', 12, 'bold'),
                 bg=self.COLORS['bg_dark'], fg=self.COLORS['text_main']).grid(row=0, column=2, padx=5)
        self.scrollable_frame.grid_columnconfigure(2, weight=1)

        for i, (date_key, description) in enumerate(sorted_events, start=1):
            # is_latest=True 仅用于第一条（最新一条）
            self._create_row_widgets(i, date_key, description, is_new=False, is_latest=(i == 1))
        
        self._update_select_all_state()

    def _create_row_widgets(self, row_index, date_key, description, is_new=False, is_latest=False):
        """辅助函数，用于创建一行控件并应用样式"""
        row_frame = Frame(self.scrollable_frame, bg=self.COLORS['bg_dark'])
        row_frame.grid(row=row_index, column=0, sticky="ew", padx=5, pady=4)
        row_frame.grid_columnconfigure(2, weight=1)

        # 1. 复选框
        check_var = BooleanVar()
        checkbutton = Checkbutton(row_frame, variable=check_var, command=self._update_select_all_state,
                                  bg=self.COLORS['bg_dark'], activebackground=self.COLORS['bg_dark'],
                                  highlightthickness=0, selectcolor=self.COLORS['bg_medium'])
        checkbutton.grid(row=0, column=0, padx=5, sticky='ns')

        # 若为最新一条，默认勾选
        if is_latest:
            check_var.set(True)

        # 样式定义
        entry_style = {
            'bg': self.COLORS['bg_medium'],
            'fg': self.COLORS['fg_light'],
            'font': ('Helvetica', 22),
            'insertbackground': self.COLORS['fg_light'], # 光标颜色
            'relief': tk.SOLID,
            'borderwidth': 1,
            'highlightthickness': 2,
            'highlightbackground': self.COLORS['border'],
            'highlightcolor': self.COLORS['select_bg']
        }

        # 2. 日期输入框
        date_entry = Entry(row_frame, width=15, **entry_style)
        date_entry.insert(0, date_key)
        date_entry.grid(row=0, column=1, padx=5, ipady=5)

        # 3. 内容文本框
        desc_text = Text(row_frame, height=4, wrap=tk.WORD, **entry_style)
        desc_text.insert("1.0", description)
        desc_text.grid(row=0, column=2, sticky="ew", padx=5)

        self.rows.append({
            'check_var': check_var,
            'date_entry': date_entry,
            'desc_text': desc_text,
            'original_date': None if is_new else date_key
        })

        # 设置完当前行后更新一次全选状态（避免仅有一条时全选框不一致）
        self._update_select_all_state()

    def _add_new_row(self):
        i = len(self.rows) + 1
        # 使用辅助函数创建新行
        self._create_row_widgets(i, "YYYY-MM-DD", "请在此输入内容...", is_new=True, is_latest=False)
        self._update_select_all_state()

    def _delete_selected(self):
        keys_to_delete = [
            row['original_date'] 
            for row in self.rows 
            if row['check_var'].get() and row['original_date'] is not None
        ]

        if not keys_to_delete:
            messagebox.showinfo("提示", "没有选中任何要删除的条目。")
            self.master.lift()
            self.master.focus_force()
            return

        if messagebox.askyesno("确认删除", f"确定要删除选中的 {len(keys_to_delete)} 个条目吗？\n此操作将立即保存到文件。"):
            for key in keys_to_delete:
                if key in self.events_dict:
                    del self.events_dict[key]
            
            if not self.events_dict:
                self.item_data['description3'] = [{}]

            if save_data(self.full_data):
                messagebox.showinfo("成功", "已删除选中条目并保存成功。")
                self._create_widgets() # 成功后刷新UI
            else:
                messagebox.showerror("错误", "删除时在内存中成功，但保存到文件时失败。请重新加载数据。")

            self.master.lift()
            self.master.focus_force()

    def _copy_to_symbols(self):
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

        target_symbols_str = simpledialog.askstring(
            "复制到...",
            "请输入目标Symbol (多个Symbol请用空格分隔):",
            parent=self.master
        )

        if not target_symbols_str:
            return

        target_symbols = target_symbols_str.strip().split()
        if not target_symbols:
            return

        successful_copies = []
        failed_symbols = []
        
        for symbol in target_symbols:
            target_item = find_item_by_symbol(self.full_data, symbol)
            
            if target_item:
                target_events_dict = target_item['description3'][0]
                for item in items_to_copy:
                    target_events_dict[item['date']] = item['desc']
                successful_copies.append(target_item['symbol'])
            else:
                failed_symbols.append(symbol)

        if successful_copies:
            if not save_data(self.full_data):
                messagebox.showerror("复制失败", "数据已在内存中修改，但保存到文件时失败。")
                return
        
        report_message = ""
        if successful_copies:
            report_message += f"成功将 {len(items_to_copy)} 个条目复制到: \n" + ", ".join(successful_copies)
        
        if failed_symbols:
            if report_message:
                report_message += "\n\n"
            report_message += "未在JSON文件中找到以下Symbol: \n" + ", ".join(failed_symbols)

        messagebox.showinfo("复制操作完成", report_message)
        self.master.lift()
        self.master.focus_force()

    def _save_changes(self):
        new_events_dict = {}
        has_duplicates = False
        for row in self.rows:
            date_key = row['date_entry'].get().strip()
            description = row['desc_text'].get("1.0", "end-1c").strip()
            
            if not date_key or date_key == "YYYY-MM-DD" or not description:
                continue

            if date_key in new_events_dict and not has_duplicates:
                messagebox.showwarning("警告", f"日期 '{date_key}' 重复，只有此日期下的最后一个条目会被保存。")
                has_duplicates = True

            new_events_dict[date_key] = description
        
        self.item_data['description3'] = [new_events_dict]
        
        if save_data(self.full_data):
            self.events_dict = new_events_dict
            # messagebox.showinfo("成功", "所有更改已成功保存！")
            self._create_widgets()
        else:
            messagebox.showerror("失败", "保存文件时发生错误，请检查控制台输出。")

# --- 主程序入口 ---
def main():
    symbol = get_symbol_from_input()
    if not symbol:
        return # 如果初始获取 symbol 失败或用户取消，则直接退出

    full_data = load_data()
    if full_data is None:
        return

    hidden_root = tk.Tk()
    hidden_root.withdraw()

    item_data = find_item_by_symbol(full_data, symbol)

    while item_data is None:
        prompt = f"未在 JSON 中找到 Symbol：'{symbol}'。\n请重新输入要编辑的 Symbol：\n（取消则退出）"
        symbol = simpledialog.askstring("输入 Symbol", prompt, parent=hidden_root)
        if not symbol:
            hidden_root.destroy()
            return
        item_data = find_item_by_symbol(full_data, symbol)

    hidden_root.destroy()

    root = tk.Tk()
    root.bind('<Escape>', lambda e: root.destroy())
    
    app = DescriptionEditorApp(root, full_data, item_data)
    
    # 确保窗口在最前
    root.lift()
    root.focus_force()
    
    root.mainloop()

if __name__ == "__main__":
    main()