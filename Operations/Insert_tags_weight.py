import json
import tkinter as tk
from tkinter import messagebox

def add_tag():
    # 创建主窗口
    root = tk.Tk()
    root.title("添加标签")
    root.geometry("300x150")

    root.lift()
    root.focus_force()
    
    # 创建输入框和标签
    label = tk.Label(root, text="请输入要添加的标签:")
    label.pack(pady=10)
    
    entry = tk.Entry(root, width=30)
    entry.pack(pady=10)
    entry.focus()  # 让输入框获得焦点
    
    def submit():
        new_tag = entry.get().strip()
        
        if not new_tag:
            messagebox.showwarning("警告", "请输入有效的标签!")
            return
            
        try:
            # 读取JSON文件
            with open('/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查标签是否已存在
            all_tags = []
            for tags in data.values():
                all_tags.extend(tags)
                
            if new_tag in all_tags:
                messagebox.showwarning("警告", "该标签已存在!")
                return
                
            # 添加新标签到2.0分组
            data['2.0'].append(new_tag)
            
            # 写回JSON文件
            with open('/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            messagebox.showinfo("成功", f"标签 '{new_tag}' 已成功添加!")
            root.destroy()
            
        except Exception as e:
            messagebox.showerror("错误", f"发生错误: {str(e)}")
    
    def close_window(event=None):
        root.destroy()
        
    # 创建提交按钮
    submit_button = tk.Button(root, text="提交", command=submit)
    submit_button.pack(pady=10)
    
    # 绑定快捷键
    root.bind('<Return>', lambda event: submit())  # 回车键绑定提交功能
    root.bind('<Escape>', close_window)  # ESC键绑定关闭功能
    
    # 添加提示文本
    hint_label = tk.Label(root, text="快捷键: Enter = 提交, ESC = 关闭", fg="gray")
    hint_label.pack(pady=5)
    
    # 启动主循环
    root.mainloop()

if __name__ == "__main__":
    add_tag()