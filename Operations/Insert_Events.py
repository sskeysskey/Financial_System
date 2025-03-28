import tkinter as tk
from tkinter import ttk
from tkinter import messagebox  # 添加这一行导入messagebox
import json
from datetime import datetime, timedelta
import calendar
import platform
import os

class App:
    def __init__(self):
        self.data = self.load_json()
        self.selected_type = None
        self.selected_date = None
        self.selected_symbol = None
        self.selected_symbols = []  # 新增：用于保存多个符合标签的symbols
        self.event_text = None
        
        self.main_window()

    def load_json(self):
        with open('/Users/yanzhang/Documents/Financial_System/Modules/description.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_json(self):
        with open('/Users/yanzhang/Documents/Financial_System/Modules/description.json', 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def set_window_to_front(self, window):
        # Mac系统特定的窗口置顶方法
        if platform.system() == 'Darwin':  # macOS
            os.system('''/usr/bin/osascript -e 'tell app "Finder" to set frontmost of process "Python" to true' ''')
        
        window.lift()  # 将窗口提升到最前
        window.focus_force()  # 强制获取焦点

    def main_window(self):
        self.root = tk.Tk()
        self.root.title("选择类型")
        
        # 设置窗口位置在屏幕中央
        window_width = 200
        window_height = 100
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(self.root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 将默认值改为"特定"
        self.type_var = tk.StringVar(value="特定")
        
        global_radio = ttk.Radiobutton(frame, text="全局", variable=self.type_var, value="全局")
        specific_radio = ttk.Radiobutton(frame, text="特定", variable=self.type_var, value="特定")
        
        global_radio.grid(row=0, column=0, pady=5)
        specific_radio.grid(row=1, column=0, pady=5)
        
        self.root.bind('<Return>', self.handle_type_selection)
        self.root.bind('<Escape>', lambda e: self.root.destroy())
        
        # 添加上下键切换
        def handle_up_down(event):
            current = self.type_var.get()
            self.type_var.set("特定" if current == "全局" else "全局")
        
        self.root.bind('<Up>', handle_up_down)
        self.root.bind('<Down>', handle_up_down)

        # 将窗口置于最前台并激活
        self.root.after(100, lambda: self.set_window_to_front(self.root))
        
        self.root.mainloop()

    def handle_type_selection(self, event):
        self.selected_type = self.type_var.get()
        self.root.destroy()
        
        if self.selected_type == "特定":
            self.selection_method_window()  # 修改为先选择查找方式
        else:
            self.date_window()

    def selection_method_window(self):
        """新增窗口，用于选择通过Symbol还是通过标签来查找"""
        method_root = tk.Tk()
        method_root.title("选择查找方式")
        
        # 设置窗口位置在屏幕中央
        window_width = 250
        window_height = 120
        screen_width = method_root.winfo_screenwidth()
        screen_height = method_root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        method_root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(method_root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 默认选择Symbol方式
        self.method_var = tk.StringVar(value="Symbol")
        
        symbol_radio = ttk.Radiobutton(frame, text="通过Symbol查找", variable=self.method_var, value="Symbol")
        tag_radio = ttk.Radiobutton(frame, text="通过标签查找", variable=self.method_var, value="标签")
        
        symbol_radio.grid(row=0, column=0, pady=5, sticky=tk.W)
        tag_radio.grid(row=1, column=0, pady=5, sticky=tk.W)
        
        def handle_method_selection():
            method = self.method_var.get()
            method_root.destroy()
            if method == "Symbol":
                self.symbol_window()
            else:
                self.tag_window()
        
        method_root.bind('<Return>', lambda e: handle_method_selection())
        method_root.bind('<Escape>', lambda e: method_root.destroy())
        
        # 添加上下键切换
        def handle_up_down(event):
            current = self.method_var.get()
            self.method_var.set("标签" if current == "Symbol" else "Symbol")
        
        method_root.bind('<Up>', handle_up_down)
        method_root.bind('<Down>', handle_up_down)
        
        def focus_and_lift():
            self.set_window_to_front(method_root)
            symbol_radio.focus_set()
        
        method_root.after(100, focus_and_lift)
        
        method_root.mainloop()

    def tag_window(self):
        """新增窗口，用于通过标签筛选symbols"""
        tag_root = tk.Tk()
        tag_root.title("输入标签")
        
        # 设置窗口位置在屏幕中央
        window_width = 400
        window_height = 200
        screen_width = tag_root.winfo_screenwidth()
        screen_height = tag_root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        tag_root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(tag_root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(frame, text="请输入标签（用空格分隔多个标签）:").grid(row=0, column=0, pady=5, sticky=tk.W)
        tag_entry = ttk.Entry(frame, width=40)
        tag_entry.grid(row=1, column=0, pady=5, sticky=tk.W)
        
        info_label = ttk.Label(frame, text="符合条件的每个标签将被分别查找。", wraplength=380)
        info_label.grid(row=2, column=0, pady=5, sticky=tk.W)
        
        result_label = ttk.Label(frame, text="", foreground="blue", wraplength=380)
        result_label.grid(row=3, column=0, pady=5, sticky=tk.W)
        
        error_label = ttk.Label(frame, text="", foreground="red", wraplength=380)
        error_label.grid(row=4, column=0, pady=5, sticky=tk.W)
        
        def handle_tag_search():
            tags = tag_entry.get().strip().split()
            if not tags:
                error_label.config(text="请至少输入一个标签！")
                return
            
            # 清空之前的选择
            self.selected_symbols = []
            
            # 查找匹配标签的所有symbol
            found_symbols = set()  # 使用集合避免重复
            
            for section in ['stocks', 'etfs']:
                for item in self.data[section]:
                    # 获取item的tag并处理不同的数据类型情况
                    item_tags = []
                    tag_value = item.get('tag', '')
                    
                    # 处理不同类型的tag字段
                    if isinstance(tag_value, str):
                        item_tags = tag_value.split()
                    elif isinstance(tag_value, list):
                        item_tags = tag_value
                    
                    # 检查是否有任何标签完全匹配
                    if any(tag in item_tags for tag in tags):
                        found_symbols.add(item['symbol'])
            
            # 将结果转换为列表
            self.selected_symbols = list(found_symbols)
            
            if not self.selected_symbols:
                error_label.config(text="没有找到符合条件的symbol！")
                result_label.config(text="")
            else:
                error_label.config(text="")
                result_label.config(text=f"找到 {len(self.selected_symbols)} 个符合条件的symbol: " + 
                                  ", ".join(self.selected_symbols[:5]) + 
                                  (f" 等..." if len(self.selected_symbols) > 5 else ""))
                
                # 确认是否继续
                confirm = messagebox.askyesno("确认", f"找到 {len(self.selected_symbols)} 个符合条件的symbol，是否继续？")
                if confirm:
                    tag_root.destroy()
                    self.date_window()
        
        tag_root.bind('<Return>', lambda e: handle_tag_search())
        tag_root.bind('<Escape>', lambda e: tag_root.destroy())
        
        def focus_and_lift():
            self.set_window_to_front(tag_root)
            tag_entry.focus_set()
        
        tag_root.after(100, focus_and_lift)
        
        tag_root.mainloop()

    def symbol_window(self):
        symbol_root = tk.Tk()
        symbol_root.title("输入Symbol")
        
        # 设置窗口位置在屏幕中央
        window_width = 300
        window_height = 150
        screen_width = symbol_root.winfo_screenwidth()
        screen_height = symbol_root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        symbol_root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(symbol_root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(frame, text="请输入Symbol:").grid(row=0, column=0, pady=5)
        symbol_entry = ttk.Entry(frame)
        symbol_entry.grid(row=1, column=0, pady=5)
        
        # 创建一个验证命令，将输入转换为大写
        def to_uppercase(*args):
            value = symbol_entry.get()
            symbol_entry.delete(0, tk.END)
            symbol_entry.insert(0, value.upper())
        
        # 绑定键盘事件，每次输入都转换为大写
        symbol_entry.bind('<KeyRelease>', to_uppercase)
        
        def handle_symbol():
            symbol = symbol_entry.get().upper()
            # 验证symbol是否存在
            found = False
            for section in ['stocks', 'etfs']:
                for item in self.data[section]:
                    if item['symbol'] == symbol:
                        found = True
                        break
                if found:
                    break
            
            if found:
                self.selected_symbol = symbol
                self.selected_symbols = [symbol]  # 也设置为列表，便于后续处理
                symbol_root.destroy()
                self.date_window()
            else:
                error_label.config(text="Symbol不存在！")
        
        error_label = ttk.Label(frame, text="", foreground="red")
        error_label.grid(row=2, column=0, pady=5)
        
        symbol_root.bind('<Return>', lambda e: handle_symbol())
        symbol_root.bind('<Escape>', lambda e: symbol_root.destroy())
        
        def focus_and_lift():
            self.set_window_to_front(symbol_root)
            symbol_entry.focus_set()  # 确保输入框获得焦点
        
        # 将窗口置于最前台并激活，同时设置输入框焦点
        symbol_root.after(100, focus_and_lift)
        
        symbol_root.mainloop()

    def date_window(self):
        date_root = tk.Tk()
        date_root.title("选择日期")
        
        # 设置窗口位置在屏幕中央
        window_width = 300
        window_height = 200
        screen_width = date_root.winfo_screenwidth()
        screen_height = date_root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        date_root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(date_root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.date_var = tk.StringVar(value="默认")
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        default_radio = ttk.Radiobutton(frame, text=f"默认（{yesterday}）", variable=self.date_var, value="默认")
        custom_radio = ttk.Radiobutton(frame, text="自定义", variable=self.date_var, value="自定义")
        
        default_radio.grid(row=0, column=0, pady=5)
        custom_radio.grid(row=1, column=0, pady=5)
        
        # 自定义日期选择器
        date_frame = ttk.Frame(frame)
        date_frame.grid(row=2, column=0, pady=5)
        
        year_var = tk.StringVar(value=str(datetime.now().year))
        month_var = tk.StringVar(value=str(datetime.now().month))
        day_var = tk.StringVar(value=str(datetime.now().day))
        
        ttk.Label(date_frame, text="年:").grid(row=0, column=0)
        year_entry = ttk.Entry(date_frame, textvariable=year_var, width=6)
        year_entry.grid(row=0, column=1)
        
        ttk.Label(date_frame, text="月:").grid(row=0, column=2)
        month_entry = ttk.Entry(date_frame, textvariable=month_var, width=4)
        month_entry.grid(row=0, column=3)
        
        ttk.Label(date_frame, text="日:").grid(row=0, column=4)
        day_entry = ttk.Entry(date_frame, textvariable=day_var, width=4)
        day_entry.grid(row=0, column=5)
        
        def handle_date():
            if self.date_var.get() == "默认":
                self.selected_date = yesterday
            else:
                try:
                    year = int(year_var.get())
                    month = int(month_var.get())
                    day = int(day_var.get())
                    self.selected_date = f"{year:04d}-{month:02d}-{day:02d}"
                    # 验证日期是否合法
                    datetime.strptime(self.selected_date, '%Y-%m-%d')
                except:
                    error_label.config(text="日期格式不正确！")
                    return
            
            date_root.destroy()
            self.event_window()
        
        error_label = ttk.Label(frame, text="", foreground="red")
        error_label.grid(row=3, column=0, pady=5)
        
        # 添加上下键切换
        def handle_up_down(event):
            current = self.date_var.get()
            self.date_var.set("自定义" if current == "默认" else "默认")
        
        date_root.bind('<Up>', handle_up_down)
        date_root.bind('<Down>', handle_up_down)
        date_root.bind('<Return>', lambda e: handle_date())
        date_root.bind('<Escape>', lambda e: date_root.destroy())
        
        def focus_and_lift():
            self.set_window_to_front(date_root)
            default_radio.focus_set()  # 设置默认选项获得焦点
        
        # 将窗口置于最前台并激活，同时设置焦点
        date_root.after(100, focus_and_lift)
        
        date_root.mainloop()

    def event_window(self):
        event_root = tk.Tk()
        event_root.title("输入事件")
        
        # 设置窗口位置在屏幕中央
        window_width = 400
        window_height = 200
        screen_width = event_root.winfo_screenwidth()
        screen_height = event_root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        event_root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(event_root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(frame, text="请输入事件描述 (Shift+Enter 提交):").grid(row=0, column=0, pady=5)
        
        # 设置文本框字体大小
        text_widget = tk.Text(frame, height=5, width=40, font=('TkDefaultFont', 14))
        text_widget.grid(row=1, column=0, pady=5)
        text_widget.focus()
        
        def handle_event():
            self.event_text = text_widget.get("1.0", "end-1c").strip()
            if self.event_text:
                event_root.destroy()
                self.save_data()
        
        # 使用 Shift+Return 作为提交快捷键
        def on_shift_return(event):
            handle_event()
            return "break"
        
        text_widget.bind("<Shift-Return>", on_shift_return)
        event_root.bind('<Escape>', lambda e: event_root.destroy())
        
        def focus_and_lift():
            self.set_window_to_front(event_root)
            text_widget.focus_set()  # 确保文本框获得焦点
        
        # 将窗口置于最前台并激活，同时设置文本框焦点
        event_root.after(100, focus_and_lift)
        
        event_root.mainloop()

    def save_data(self):
        if self.selected_type == "全局":
            self.data['global'][self.selected_date] = self.event_text
        else:
            # 对于标签模式选择的多个symbol，需要逐个处理
            updated_count = 0
            for symbol in self.selected_symbols:
                # 查找并更新特定symbol的description3
                for section in ['stocks', 'etfs']:
                    found = False
                    for item in self.data[section]:
                        if item['symbol'] == symbol:
                            found = True
                            # 检查是否已存在相同日期的事件
                            if 'description3' in item and isinstance(item['description3'], list) and item['description3'] and isinstance(item['description3'][0], dict):
                                if self.selected_date in item['description3'][0]:
                                    # 已存在相同日期的事件，跳过
                                    continue
                            
                            # 如果没有description3字段，先创建它
                            if 'description3' not in item:
                                # 重新组织字段顺序
                                new_item = {
                                    'symbol': item['symbol'],
                                    'name': item['name'],
                                    'tag': item['tag'],
                                    'description1': item['description1'],
                                    'description2': item['description2'],
                                    'description3': [{}],
                                    'value': item['value']
                                }
                                # 更新新的事件
                                new_item['description3'][0][self.selected_date] = self.event_text
                                # 替换原来的item
                                idx = self.data[section].index(item)
                                self.data[section][idx] = new_item
                            else:
                                if not isinstance(item['description3'], list):
                                    item['description3'] = [{}]
                                elif not item['description3']:
                                    item['description3'] = [{}]
                                elif not isinstance(item['description3'][0], dict):
                                    item['description3'][0] = {}
                                
                                item['description3'][0][self.selected_date] = self.event_text
                            
                            updated_count += 1
                            break
                    if found:
                        break
            
        self.save_json()
        
        # 创建成功提示框
        success_root = tk.Tk()
        if self.selected_type == "特定" and len(self.selected_symbols) > 1:
            success_root.title(f"成功 - 已更新{updated_count}个Symbol")
        else:
            success_root.title("成功")
        
        # 设置窗口位置在屏幕中央
        window_width = 250
        window_height = 150
        screen_width = success_root.winfo_screenwidth()
        screen_height = success_root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        success_root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(success_root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        if self.selected_type == "特定" and len(self.selected_symbols) > 1:
            success_text = f"保存成功！\n共更新了 {updated_count} 个Symbol"
        else:
            success_text = "保存成功！"
            
        success_label = ttk.Label(frame, text=success_text, font=('TkDefaultFont', 14))
        success_label.grid(row=0, column=0, pady=20)
        
        def close_window(event=None):
            success_root.destroy()
        
        # 绑定多个关闭按键
        success_root.bind('<Return>', close_window)
        success_root.bind('<Escape>', close_window)
        
        def focus_and_lift():
            self.set_window_to_front(success_root)
        
        # 将窗口置于最前台并激活
        success_root.after(100, focus_and_lift)
        
        success_root.mainloop()

if __name__ == "__main__":
    App()