import tkinter as tk
import sqlite3
from datetime import datetime
import sys  # 添加导入

class App:
    def __init__(self, init_symbol=None):  # 修改初始化函数接受参数
        self.root = tk.Tk()
        self.root.title("添加财报信息")
        
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 设置窗口大小和位置
        window_width = 400
        window_height = 200
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 绑定ESC键到所有窗口
        self.root.bind('<Escape>', self.close_app)
        
        # 如果提供了初始symbol，直接进入第二步
        if init_symbol:
            self.stock_name = init_symbol.upper()
            self.create_second_screen()
        else:
            self.create_first_screen()
        
        # 将窗口置于最前
        self.root.lift()
        self.root.focus_force()
        
    def create_first_screen(self):
        self.clear_window()
        
        label = tk.Label(self.root, text="请输入要添加财报信息的股票代码：")
        label.pack(pady=20)
        
        self.entry = tk.Entry(self.root)
        self.entry.pack(pady=10)
        
        # 确保输入框获得焦点
        self.root.after(100, lambda: self.entry.focus_set())
        
        # 绑定回车键
        self.entry.bind('<Return>', self.handle_first_screen)
        
        # 绑定输入转换为大写
        self.entry.bind('<KeyRelease>', self.to_upper)
        
    def to_upper(self, event):
        # 获取当前输入内容并转换为大写
        content = self.entry.get().upper()
        self.entry.delete(0, tk.END)
        self.entry.insert(0, content)
        
    def handle_first_screen(self, event):
        self.stock_name = self.entry.get().upper()
        self.create_second_screen()
        
    def create_second_screen(self):
        self.clear_window()
        
        label = tk.Label(self.root, text="请输入日期 (格式: YYYY-MM-DD)：")
        label.pack(pady=20)
        
        self.date_entry = tk.Entry(self.root)
        self.date_entry.pack(pady=10)
        
        # 插入当前日期作为默认值
        current_date = datetime.now().strftime('%Y-%m-%d')
        self.date_entry.insert(0, current_date)
        
        # 确保输入框获得焦点
        self.root.after(100, lambda: self.date_entry.focus_set())
        
        # 绑定回车键
        self.date_entry.bind('<Return>', self.handle_second_screen)
        
    def handle_second_screen(self, event):
        date_str = self.date_entry.get()
        try:
            # 验证日期格式
            datetime.strptime(date_str, '%Y-%m-%d')
            self.selected_date = date_str
            self.create_third_screen()
        except ValueError:
            self.show_error_message("请输入正确的日期格式 (YYYY-MM-DD)")
        
    def create_third_screen(self):
        self.clear_window()
        
        label = tk.Label(self.root, text="请输入价格：")
        label.pack(pady=20)
        
        self.price_entry = tk.Entry(self.root)
        self.price_entry.pack(pady=10)
        
        # 确保输入框获得焦点
        self.root.after(100, lambda: self.price_entry.focus_set())
        
        # 绑定回车键
        self.price_entry.bind('<Return>', self.handle_third_screen)
        
    def handle_third_screen(self, event):
        try:
            self.price = float(self.price_entry.get())  # 保存价格为类属性
            self.save_to_database(self.stock_name, self.selected_date, self.price)
            self.show_success_screen()
        except ValueError:
            self.show_error_message("请输入有效的价格数字")
            
    def show_success_screen(self):
        self.clear_window()
        
        # 成功消息
        success_label = tk.Label(
            self.root, 
            text=f"保存成功！\n\n股票代码: {self.stock_name}\n日期: {self.selected_date}\n价格: {self.price}",
            justify=tk.LEFT
        )
        success_label.pack(pady=20)
        
        # 添加提示信息
        hint_label = tk.Label(self.root, text="按ESC键关闭窗口")
        hint_label.pack(pady=10)
            
    def save_to_database(self, name, date, price):
        conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
        cursor = conn.cursor()
        
        # 插入数据
        cursor.execute('''
            INSERT INTO Earning (date, name, price)
            VALUES (?, ?, ?)
        ''', (date, name, price))
        
        conn.commit()
        conn.close()
        
    def clear_window(self):
        # 清除窗口中的所有部件
        for widget in self.root.winfo_children():
            widget.destroy()
            
    def close_app(self, event=None):
        self.root.quit()
            
    def run(self):
        self.root.mainloop()

def init_database():
    conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Earning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_database()
    
    # 检查是否提供了命令行参数
    init_symbol = None
    if len(sys.argv) > 1:
        init_symbol = sys.argv[1]
        
    app = App(init_symbol)
    app.run()