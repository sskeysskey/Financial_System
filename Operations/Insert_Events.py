import tkinter as tk
from tkinter import ttk
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
            self.symbol_window()
        else:
            self.date_window()

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
        
        ttk.Label(frame, text="请输入事件描述:").grid(row=0, column=0, pady=5)
        
        # 设置文本框字体大小
        text_widget = tk.Text(frame, height=5, width=40, font=('TkDefaultFont', 14))
        text_widget.grid(row=1, column=0, pady=5)
        text_widget.focus()
        
        def handle_event():
            self.event_text = text_widget.get("1.0", "end-1c").strip()
            if self.event_text:
                event_root.destroy()
                self.save_data()
        
        event_root.bind('<Return>', lambda e: handle_event())
        # 在 Text 组件上直接绑定 <Return>，并通过返回 "break" 阻止默认插入换行符
        def on_return(event):
            handle_event()
            return "break"  # 阻止默认行为
        
        text_widget.bind("<Return>", on_return)
        
        # 你可以继续绑定 Escape 键来关闭窗口
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
            # 查找并更新特定symbol的description3
            for section in ['stocks', 'etfs']:
                for item in self.data[section]:
                    if item['symbol'] == self.selected_symbol:
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
                            item['description3'][0][self.selected_date] = self.event_text
                        break
            
        self.save_json()
        
        # 创建成功提示框
        success_root = tk.Tk()
        success_root.title("成功")
        
        # 设置窗口位置在屏幕中央
        window_width = 200
        window_height = 100
        screen_width = success_root.winfo_screenwidth()
        screen_height = success_root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        success_root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(success_root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        success_label = ttk.Label(frame, text="保存成功！", font=('TkDefaultFont', 14))
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