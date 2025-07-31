import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import json
import platform
import os

class TagAdder:
    def __init__(self):
        self.data = self.load_json()
        self.selected_symbols = []  # 用于保存符合标签的symbols
        self.new_tags = None  # 用于保存新添加的标签
        
        self.main_window()

    def load_json(self):
        with open('/Users/yanzhang/Coding/Financial_System/Modules/description.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_json(self):
        with open('/Users/yanzhang/Coding/Financial_System/Modules/description.json', 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def set_window_to_front(self, window):
        # Mac系统特定的窗口置顶方法
        if platform.system() == 'Darwin':  # macOS
            os.system('''/usr/bin/osascript -e 'tell app "Finder" to set frontmost of process "Python" to true' ''')
        
        window.lift()  # 将窗口提升到最前
        window.focus_force()  # 强制获取焦点

    def main_window(self):
        """输入标签查找窗口"""
        self.root = tk.Tk()
        self.root.title("输入查找标签")
        
        # 设置窗口位置在屏幕中央
        window_width = 400
        window_height = 200
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(self.root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(frame, text="请输入要查找的标签（用空格分隔多个标签）:").grid(row=0, column=0, pady=5, sticky=tk.W)
        self.tag_entry = ttk.Entry(frame, width=40)
        self.tag_entry.grid(row=1, column=0, pady=5, sticky=tk.W)
        
        info_label = ttk.Label(frame, text="符合条件的每个标签将被分别查找。", wraplength=380)
        info_label.grid(row=2, column=0, pady=5, sticky=tk.W)
        
        self.result_label = ttk.Label(frame, text="", foreground="blue", wraplength=380)
        self.result_label.grid(row=3, column=0, pady=5, sticky=tk.W)
        
        self.error_label = ttk.Label(frame, text="", foreground="red", wraplength=380)
        self.error_label.grid(row=4, column=0, pady=5, sticky=tk.W)
        
        self.root.bind('<Return>', lambda e: self.handle_tag_search())
        self.root.bind('<Escape>', lambda e: self.root.destroy())
        
        def focus_and_lift():
            self.set_window_to_front(self.root)
            self.tag_entry.focus_set()  # 设置输入框焦点
    
        # 使用更短的延迟时间，并确保在窗口显示后立即设置焦点
        self.root.after(1, focus_and_lift)
        
        self.root.mainloop()

    def handle_tag_search(self):
        """处理标签搜索"""
        tags = self.tag_entry.get().strip().split()
        if not tags:
            self.error_label.config(text="请至少输入一个标签！")
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
            self.error_label.config(text="没有找到符合条件的symbol！")
            self.result_label.config(text="")
        else:
            self.error_label.config(text="")
            self.result_label.config(text=f"找到 {len(self.selected_symbols)} 个符合条件的symbol: " + 
                              ", ".join(self.selected_symbols[:5]) + 
                              (f" 等..." if len(self.selected_symbols) > 5 else ""))
            
            # 确认是否继续
            confirm = messagebox.askyesno("确认", f"找到 {len(self.selected_symbols)} 个符合条件的symbol，是否继续添加新标签？")
            if confirm:
                self.root.destroy()
                self.add_tag_window()

    def add_tag_window(self):
        """输入新标签窗口"""
        tag_root = tk.Tk()
        tag_root.title("输入新标签")
        
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
        
        ttk.Label(frame, text="请输入要添加的新标签 (用空格分隔多个标签):").grid(row=0, column=0, pady=5)
        
        # 设置文本框字体大小
        text_widget = tk.Text(frame, height=5, width=40, font=('TkDefaultFont', 14))
        text_widget.grid(row=1, column=0, pady=5)
        text_widget.focus()
        
        def handle_new_tags():
            self.new_tags = text_widget.get("1.0", "end-1c").strip()
            if self.new_tags:
                tag_root.destroy()
                self.save_tags()
        
        # 使用 Shift+Return 作为提交快捷键
        def on_shift_return(event):
            handle_new_tags()
            return "break"
        
        text_widget.bind("<Shift-Return>", on_shift_return)
        tag_root.bind('<Escape>', lambda e: tag_root.destroy())
        
        def focus_and_lift():
            self.set_window_to_front(tag_root)
            text_widget.focus_set()  # 确保文本框获得焦点
        
        # 将窗口置于最前台并激活，同时设置文本框焦点
        tag_root.after(100, focus_and_lift)
        
        tag_root.mainloop()

    def save_tags(self):
        """保存新标签到符合条件的所有symbol"""
        if not self.new_tags:
            return
            
        # 将新标签拆分成列表
        new_tag_list = self.new_tags.split()
        
        updated_count = 0
        for symbol in self.selected_symbols:
            # 查找并更新特定symbol的tag
            for section in ['stocks', 'etfs']:
                found = False
                for item in self.data[section]:
                    if item['symbol'] == symbol:
                        found = True
                        
                        # 获取当前tag及其类型
                        tag_value = item.get('tag', '')
                        
                        # 根据原始tag的类型来添加新标签
                        if isinstance(tag_value, str):
                            # 如果原始标签是字符串，需要检查其是否为空
                            if not tag_value:
                                # 如果是空字符串，将新标签作为空格分隔的字符串
                                item['tag'] = ' '.join(new_tag_list)
                            else:
                                # 如果原始标签不为空，添加空格和新标签
                                current_tags = tag_value.split()
                                # 只添加不存在的标签
                                for new_tag in new_tag_list:
                                    if new_tag not in current_tags:
                                        tag_value += f' {new_tag}'
                                item['tag'] = tag_value
                        elif isinstance(tag_value, list):
                            # 如果原始标签是列表，将不存在的新标签添加到列表
                            for new_tag in new_tag_list:
                                if new_tag not in tag_value:
                                    tag_value.append(new_tag)
                            item['tag'] = tag_value
                        else:
                            # 如果tag字段不存在或为其他类型，创建为字符串
                            item['tag'] = ' '.join(new_tag_list)
                        
                        updated_count += 1
                        break
                if found:
                    break
        
        self.save_json()
        
        # 创建成功提示框
        success_root = tk.Tk()
        success_root.title(f"成功 - 已更新{updated_count}个Symbol")
        
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
        
        success_text = f"保存成功！\n已为 {updated_count} 个Symbol添加新标签"
            
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
    TagAdder()