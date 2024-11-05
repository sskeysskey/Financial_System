import os
import json
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
import pyperclip

def copy2clipboard():
    script = '''
    tell application "System Events"
        keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

class TagEditor:
    def __init__(self, init_symbol=None):
        self.json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"
        self.load_json_data()
        
        self.root = tk.Tk()
        self.root.title("Tag Editor")
        self.root.geometry("500x600")
        
        # 初始化UI
        self.init_ui()
        
        # 将窗口置顶
        self.root.lift()
        self.root.focus_force()
        
        # 绑定ESC键到退出函数
        self.root.bind('<Escape>', lambda e: self.close_application())
        
        # 处理初始化数据
        if init_symbol:
            self.process_symbol(init_symbol)
        else:
            self.process_clipboard()
    
    def close_application(self):
        """关闭应用程序"""
        self.root.quit()
        
    def process_symbol(self, symbol):
        """处理指定的symbol"""
        if symbol:
            category, item = self.find_symbol(symbol)
            if item:
                self.current_category = category
                self.current_item = item
                self.update_ui(item)
            else:
                messagebox.showinfo("提示", f"未找到Symbol: {symbol}")

    def load_json_data(self):
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as file:
                self.data = json.load(file)
        except Exception as e:
            messagebox.showerror("Error", f"加载JSON文件失败: {str(e)}")
            self.data = {"stocks": [], "etfs": []}

    def save_json_data(self):
        try:
            with open(self.json_file_path, 'w', encoding='utf-8') as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
            # 显示成功消息框，并在关闭后重新聚焦到主窗口
            self.root.after(100, lambda: messagebox.showinfo("成功", "保存成功！"))
            self.root.after(200, lambda: self.restore_focus())
        except Exception as e:
            messagebox.showerror("Error", f"保存失败: {str(e)}")
            self.root.after(200, lambda: self.restore_focus())

    def restore_focus(self):
        """恢复主窗口焦点"""
        self.root.lift()
        self.root.focus_force()

    def init_ui(self):
        # Symbol显示
        self.symbol_label = ttk.Label(self.root, text="Symbol: ")
        self.symbol_label.pack(pady=10)
        
        # Tags列表框
        self.tags_frame = ttk.LabelFrame(self.root, text="Tags")
        self.tags_frame.pack(padx=10, pady=5, fill="both", expand=True)
        
        # 创建一个框架来容纳列表框和移动按钮
        list_buttons_frame = ttk.Frame(self.tags_frame)
        list_buttons_frame.pack(fill="both", expand=True)
        
        # 添加上下移动按钮
        move_buttons_frame = ttk.Frame(list_buttons_frame)
        move_buttons_frame.pack(side="left", padx=5, fill="y")
        
        ttk.Button(move_buttons_frame, text="↑", width=3,
                  command=self.move_tag_up).pack(pady=2)
        ttk.Button(move_buttons_frame, text="↓", width=3,
                  command=self.move_tag_down).pack(pady=2)
        
        # Tags列表框
        self.tags_listbox = tk.Listbox(list_buttons_frame)
        self.tags_listbox.pack(side="left", padx=5, pady=5, fill="both", expand=True)
        
        # 绑定双击事件用于编辑
        self.tags_listbox.bind('<Double-Button-1>', self.on_double_click)
        
        # 添加新tag输入框和按钮的框架
        input_frame = ttk.Frame(self.root)
        input_frame.pack(pady=5, fill="x", padx=10)
        
        self.new_tag_var = tk.StringVar()
        self.new_tag_entry = ttk.Entry(input_frame, textvariable=self.new_tag_var)
        self.new_tag_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # 按钮框架
        buttons_frame = ttk.Frame(self.root)
        buttons_frame.pack(pady=5, padx=10, fill="x")
        
        # 按钮
        ttk.Button(buttons_frame, text="添加新标签", 
                  command=self.add_tag).pack(side="left", padx=2)
        ttk.Button(buttons_frame, text="删除标签", 
                  command=self.delete_tag).pack(side="left", padx=2)
        ttk.Button(buttons_frame, text="保存更改", 
                  command=self.save_changes).pack(side="left", padx=2)

        # 绑定回车键到保存功能
        self.root.bind('<Return>', lambda e: self.save_changes())

    def on_double_click(self, event):
        """处理双击编辑事件"""
        selection = self.tags_listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        old_tag = self.tags_listbox.get(index)
        
        # 创建编辑对话框
        edit_window = tk.Toplevel(self.root)
        edit_window.title("编辑标签")
        edit_window.geometry("300x100")
        
        # 使对话框成为模态窗口
        edit_window.transient(self.root)
        edit_window.grab_set()
        
        # 创建编辑框
        edit_var = tk.StringVar(value=old_tag)
        edit_entry = ttk.Entry(edit_window, textvariable=edit_var)
        edit_entry.pack(padx=10, pady=10, fill="x")
        
        def save_edit():
            new_tag = edit_var.get().strip()
            if new_tag and new_tag != old_tag:
                self.current_item['tag'][index] = new_tag
                self.tags_listbox.delete(index)
                self.tags_listbox.insert(index, new_tag)
            edit_window.destroy()
        
        def close_edit_window(event=None):
            """关闭编辑窗口"""
            edit_window.destroy()
            
        # 添加确认按钮
        ttk.Button(edit_window, text="确认", command=save_edit).pack(pady=5)
        
        # 绑定ESC键到关闭编辑窗口函数
        edit_window.bind('<Escape>', close_edit_window)
        
        # 绑定回车键到保存功能
        edit_entry.bind('<Return>', lambda e: save_edit())
        
        # 聚焦到编辑框并选中全部文本
        edit_entry.focus_set()
        edit_entry.select_range(0, tk.END)
        
        # 绑定回车键
        edit_entry.bind('<Return>', lambda e: save_edit())

    def move_tag_up(self):
        """将选中的tag向上移动"""
        selection = self.tags_listbox.curselection()
        if not selection or selection[0] == 0:
            return
            
        index = selection[0]
        tag = self.current_item['tag'].pop(index)
        self.current_item['tag'].insert(index-1, tag)
        
        # 更新列表显示
        self.tags_listbox.delete(0, tk.END)
        for tag in self.current_item['tag']:
            self.tags_listbox.insert(tk.END, tag)
        self.tags_listbox.selection_set(index-1)

    def move_tag_down(self):
        """将选中的tag向下移动"""
        selection = self.tags_listbox.curselection()
        if not selection or selection[0] == self.tags_listbox.size()-1:
            return
            
        index = selection[0]
        tag = self.current_item['tag'].pop(index)
        self.current_item['tag'].insert(index+1, tag)
        
        # 更新列表显示
        self.tags_listbox.delete(0, tk.END)
        for tag in self.current_item['tag']:
            self.tags_listbox.insert(tk.END, tag)
        self.tags_listbox.selection_set(index+1)

    # [之前的其他方法保持不变...]
    def find_symbol(self, symbol):
        """查找symbol对应的数据"""
        for category in ['stocks', 'etfs']:
            for item in self.data[category]:
                if item['symbol'] == symbol:
                    return category, item
        return None, None

    def process_clipboard(self):
        """处理剪贴板内容"""
        try:
            clipboard_text = pyperclip.paste().strip()
            if clipboard_text:
                category, item = self.find_symbol(clipboard_text)
                if item:
                    self.current_category = category
                    self.current_item = item
                    self.update_ui(item)
                else:
                    messagebox.showinfo("提示", f"未找到Symbol: {clipboard_text}")
            else:
                messagebox.showinfo("提示", "剪贴板为空")
        except Exception as e:
            messagebox.showerror("Error", f"剪贴板读取失败: {str(e)}")

    def update_ui(self, item):
        """更新UI显示"""
        self.symbol_label.config(text=f"Symbol: {item['symbol']}")
        self.tags_listbox.delete(0, tk.END)
        for tag in item['tag']:
            self.tags_listbox.insert(tk.END, tag)

    def add_tag(self):
        """添加新tag"""
        new_tag = self.new_tag_var.get().strip()
        if new_tag and hasattr(self, 'current_item'):
            if new_tag not in self.current_item['tag']:
                self.current_item['tag'].append(new_tag)
                self.tags_listbox.insert(tk.END, new_tag)
                self.new_tag_var.set("")
            else:
                messagebox.showinfo("提示", "该标签已存在")

    def delete_tag(self):
        """删除选中的tag"""
        selection = self.tags_listbox.curselection()
        if selection and hasattr(self, 'current_item'):
            index = selection[0]
            tag = self.tags_listbox.get(index)
            self.current_item['tag'].remove(tag)
            self.tags_listbox.delete(index)

    def save_changes(self):
        """保存更改到JSON文件"""
        if hasattr(self, 'current_item'):
            self.save_json_data()
        else:
            messagebox.showinfo("提示", "没有可保存的更改")

    def run(self):
        """运行程序"""
        self.root.mainloop()

def main():
    # 检查是否有命令行参数
    init_symbol = None
    if len(sys.argv) > 1:
        init_symbol = sys.argv[1].upper()  # 转换为大写以确保匹配
    
    # 如果没有命令行参数，执行复制操作
    if not init_symbol:
        copy2clipboard()
    
    # 创建并运行应用
    app = TagEditor(init_symbol)
    app.run()

if __name__ == "__main__":
    main()