import json
import tkinter as tk
from tkinter import messagebox, ttk

def add_tag():
    def select_weight():
        # 创建权重选择窗口
        weight_window = tk.Tk()
        weight_window.title("选择权重")
        weight_window.geometry("300x150")
        weight_window.lift()
        weight_window.focus_force()

        # 创建权重选择框
        label = tk.Label(weight_window, text="请选择标签权重:")
        label.pack(pady=10)

        weight_var = tk.StringVar(value="2.0")  # 默认值设为2.0
        weight_combo = ttk.Combobox(
            weight_window, 
            textvariable=weight_var,
            values=["1.3", "2.0"],
            state="readonly",
            width=25
        )
        weight_combo.pack(pady=10)
        
        # 自动激活下拉框
        weight_combo.focus_set()
        weight_combo.event_generate('<Down>')  # 模拟按下向下键，激活下拉列表

        def on_weight_select():
            selected_weight = weight_var.get()
            weight_window.destroy()
            show_tag_input(selected_weight)

        def handle_key(event):
            if event.keysym == 'Return':
                on_weight_select()
            elif event.keysym in ('Up', 'Down'):
                # 获取当前值的索引
                current_value = weight_var.get()
                values = weight_combo['values']
                current_index = values.index(current_value)
                
                # 根据按键更新选择
                if event.keysym == 'Up':
                    new_index = (current_index - 1) % len(values)
                else:  # Down
                    new_index = (current_index + 1) % len(values)
                
                weight_var.set(values[new_index])
                return 'break'  # 阻止默认行为

        # 创建确认按钮
        confirm_button = tk.Button(
            weight_window, 
            text="确认", 
            command=on_weight_select
        )
        confirm_button.pack(pady=10)

        # 绑定键盘事件
        weight_combo.bind('<Return>', handle_key)
        weight_combo.bind('<Up>', handle_key)
        weight_combo.bind('<Down>', handle_key)
        weight_window.bind('<Escape>', lambda e: weight_window.destroy())

        # 添加快捷键提示
        hint_label = tk.Label(
            weight_window, 
            text="快捷键: ↑↓ = 切换选项, Enter = 确认, ESC = 关闭", 
            fg="gray"
        )
        hint_label.pack(pady=5)

        weight_window.mainloop()

    def show_tag_input(weight):
        # 创建标签输入窗口
        input_window = tk.Tk()
        input_window.title("添加标签")
        input_window.geometry("300x150")
        input_window.lift()
        input_window.focus_force()

        # 创建输入框和标签
        label = tk.Label(input_window, text=f"请输入要添加的标签 (权重: {weight}):")
        label.pack(pady=10)

        entry = tk.Entry(input_window, width=30)
        entry.pack(pady=10)
        entry.focus()

        def submit():
            new_tag = entry.get().strip()

            if not new_tag:
                messagebox.showwarning("警告", "请输入有效的标签!")
                # 警告框关闭后重新聚焦到输入框
                input_window.after(100, lambda: (input_window.focus_force(), entry.focus()))
                return

            try:
                # 读取JSON文件
                with open('/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 检查标签是否已存在，并找出它在哪个权重组
                existing_weight = None
                for weight_key, tags in data.items():
                    if new_tag in tags:
                        existing_weight = weight_key
                        break

                if existing_weight:
                    messagebox.showwarning(
                        "警告", 
                        f"该标签 '{new_tag}' 已存在于权重 {existing_weight} 分组中!"
                    )
                    # 警告框关闭后重新聚焦到输入框并全选文本
                    input_window.after(100, lambda: (
                        input_window.focus_force(),  # 让窗口获得焦点
                        entry.focus(),               # 让输入框获得焦点
                        entry.select_range(0, tk.END)  # 全选输入框中的文本
                    ))
                    return

                # 添加新标签到选定的权重分组
                data[weight].append(new_tag)

                # 写回JSON文件
                with open('/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)

                messagebox.showinfo("成功", f"标签 '{new_tag}' 已成功添加到权重 {weight} 分组!")
                input_window.destroy()

            except Exception as e:
                messagebox.showerror("错误", f"发生错误: {str(e)}")

        # 创建提交按钮
        submit_button = tk.Button(input_window, text="提交", command=submit)
        submit_button.pack(pady=10)

        # 绑定快捷键
        input_window.bind('<Return>', lambda e: submit())
        input_window.bind('<Escape>', lambda e: input_window.destroy())

        # 添加提示文本
        hint_label = tk.Label(
            input_window, 
            text="快捷键: Enter = 提交, ESC = 关闭", 
            fg="gray"
        )
        hint_label.pack(pady=5)

        input_window.mainloop()

    # 启动权重选择流程
    select_weight()

if __name__ == "__main__":
    add_tag()