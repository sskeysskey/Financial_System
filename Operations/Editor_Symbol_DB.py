import sys
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
import pyperclip

# 查询数据库，返回列名和记录数据
def query_database_data(db_file, table_name, condition, fields, include_condition):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    if include_condition and condition:
        query = f"SELECT {fields} FROM {table_name} WHERE {condition} ORDER BY date DESC, id DESC;"
    else:
        query = f"SELECT {fields} FROM {table_name} ORDER BY date DESC, id DESC;"
    cursor.execute(query)
    rows = cursor.fetchall()
    # 如果查询到数据，则获取列名
    columns = [desc[0] for desc in cursor.description] if rows else []
    conn.close()
    return columns, rows

# 更新记录：传入记录 id 和需要更新的各字段新值（字典形式）
def update_record(db_file, table_name, record_id, new_values):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # 动态拼接 set 部分
    set_clause = ", ".join([f"{col} = ?" for col in new_values.keys()])
    sql = f"UPDATE {table_name} SET {set_clause} WHERE id = ?"
    params = list(new_values.values()) + [record_id]
    cursor.execute(sql, params)
    conn.commit()
    conn.close()

# 删除记录
def delete_record(db_file, table_name, record_id):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    sql = f"DELETE FROM {table_name} WHERE id = ?"
    cursor.execute(sql, (record_id,))
    conn.commit()
    conn.close()

# 刷新 Treeview，重新拉取数据库中的数据
def refresh_treeview(tree, db_info):
    # 清除旧数据
    for item in tree.get_children():
        tree.delete(item)
    
    columns, rows = query_database_data(db_info['path'],
                                          db_info['table'],
                                          db_info['condition'],
                                          db_info['fields'],
                                          db_info['include_condition'])
    
    if not rows:
        # 显示提示框，用户点击“确定”后继续执行
        messagebox.showinfo("提示", "没有数据可显示")
        # 获取主窗口并销毁（这里使用 tree.winfo_toplevel() 获取主窗口）
        root = tree.winfo_toplevel()
        root.destroy()  # 销毁主窗口
        import sys
        sys.exit(0)     # 强制退出程序

    # 设置列
    tree["columns"] = columns
    tree["show"] = "headings"
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="w", width=100)
    
    # 插入数据
    for row in rows:
        tree.insert("", tk.END, values=row)

# 当用户双击一行时，打开编辑窗口
def open_edit_window(record, columns, db_info, tree, root):
    edit_win = tk.Toplevel(root)  # 明确指定父窗口
    edit_win.title("编辑记录")
    
    # 添加ESC键绑定，关闭编辑窗口
    edit_win.bind("<Escape>", lambda e: edit_win.destroy())
    
    entries = {}
    date_entry = None  # 用于存储date输入框的引用
    
    for idx, col in enumerate(columns):
        tk.Label(edit_win, text=col).grid(row=idx, column=0, padx=5, pady=5, sticky="e")
        entry = tk.Entry(edit_win, width=30)
        entry.insert(0, record[idx])
        entry.grid(row=idx, column=1, padx=5, pady=5)
        # 如果是 id 字段设为只读（假设 id 为主键）
        if col == "id":
            entry.config(state="readonly")
        entries[col] = entry
        if col == "date":  # 如果是date字段，保存其引用
            date_entry = entry

    # 保存修改的处理函数
    def save_changes():
        record_id = record[columns.index("id")]
        new_values = {}
        # 取出非 id 字段的值
        for col in columns:
            if col == "id":
                continue
            new_values[col] = entries[col].get()
        try:
            update_record(db_info['path'], db_info['table'], record_id, new_values)
            edit_win.destroy()
            refresh_treeview(tree, db_info)
        except Exception as e:
            messagebox.showerror("错误", str(e))
    
    # 删除记录的处理函数
    def delete_this_record():
        if messagebox.askyesno("确认删除", "是否要删除该记录？"):
            record_id = record[columns.index("id")]
            try:
                delete_record(db_info['path'], db_info['table'], record_id)
                messagebox.showinfo("成功", "记录删除成功！")
                edit_win.destroy()
                refresh_treeview(tree, db_info)
            except Exception as e:
                messagebox.showerror("错误", str(e))
    
    # 为整个窗口添加回车键绑定
    edit_win.bind("<Return>", lambda e: save_changes())
    
    tk.Button(edit_win, text="保存修改", command=save_changes).grid(row=len(columns), column=0, padx=5, pady=10)
    tk.Button(edit_win, text="删除记录", command=delete_this_record).grid(row=len(columns), column=1, padx=5, pady=10)
    # 如果找到date输入框，设置焦点
    if date_entry:
        date_entry.focus_set()

# 双击 Treeview 的事件响应函数
def on_double_click(event, tree, db_info, columns, root):
    selected = tree.selection()
    if selected:
        record = tree.item(selected[0], "values")
        open_edit_window(record, columns, db_info, tree, root)

# 创建主窗口，显示查询结果并实现交互编辑功能
def create_main_window(db_info):
    root = tk.Tk()
    root.title("数据库查询与编辑")
    root.geometry("900x600")
    
    # 自动激活窗口在最前台
    root.lift()
    root.focus_force()
    
    # 添加一个标志来跟踪程序是否应该退出
    should_exit = [False]
    
    # 重写窗口关闭事件处理程序
    def on_closing():
        should_exit[0] = True
        root.destroy()
    
    # 设置窗口关闭处理
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # 按 ESC 键关闭窗口退出程序
    root.bind("<Escape>", lambda e: on_closing())

    frame = tk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True)
    
    tree = ttk.Treeview(frame)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    # 添加垂直滚动条
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=vsb.set)
    
    # 初始刷新数据
    columns, _ = query_database_data(db_info['path'], db_info['table'], 
                                      db_info['condition'], db_info['fields'], 
                                      db_info['include_condition'])
    refresh_treeview(tree, db_info)
    
    # 添加删除记录的函数
    def delete_selected_record(event):
        selected = tree.selection()
        if selected:
            record = tree.item(selected[0], "values")
            if messagebox.askyesno("确认删除", "是否要删除该记录？"):
                record_id = record[tree["columns"].index("id")]
                try:
                    delete_record(db_info['path'], db_info['table'], record_id)
                    messagebox.showinfo("成功", "记录删除成功！")
                    refresh_treeview(tree, db_info)
                except Exception as e:
                    messagebox.showerror("错误", str(e))
    
    # 绑定 Delete 键事件
    root.bind("<BackSpace>", delete_selected_record)
    
    # 双击时弹出编辑窗口，传递root作为参数
    tree.bind("<Double-1>", lambda event: on_double_click(event, tree, db_info, tree["columns"], root))
    
    # 使用mainloop并在退出时检查标志
    root.mainloop()
    
    # 如果标志设置为True，则确保程序完全退出
    if should_exit[0]:
        import os
        os._exit(0)  # 强制终止进程

if __name__ == '__main__':
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        clipboard_content = arg.upper()  # 转为大写以保持一致性
    else:
        # 使用tkinter创建简单的输入对话框而不是控制台输入
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        
        # 创建一个简单的输入对话框
        def get_input():
            dialog = tk.Toplevel(root)
            dialog.title("请输入Symbol")
            dialog.geometry("300x100")
            # 窗口居中显示
            dialog.update_idletasks()  # 更新以确保获取正确的窗口尺寸
            width = dialog.winfo_width()
            height = dialog.winfo_height()
            x = (dialog.winfo_screenwidth() // 2) - (width // 2)
            y = (dialog.winfo_screenheight() // 2) - (height // 2) - 200
            dialog.geometry('{}x{}+{}+{}'.format(width, height, x, y))
            
            # 自动激活窗口在最前台
            dialog.lift()
            dialog.focus_force()
            
            label = tk.Label(dialog, text="编辑财报数据")
            label.pack(pady=5)
            
            entry = tk.Entry(dialog, width=30)
            entry.pack(pady=5)
            entry.focus_set()  # 自动聚焦到输入框
            
            result = [None]  # 使用列表存储结果，便于在函数内修改
            
            def on_ok():
                result[0] = entry.get().upper()  # 获取输入并转为大写
                dialog.destroy()
            
            # 取消按钮
            def on_cancel():
                dialog.destroy()
                # 确保程序在取消时完全退出
                import os
                os._exit(0)
            
            # 按钮区域
            button_frame = tk.Frame(dialog)
            button_frame.pack(pady=5)
            
            ok_button = tk.Button(button_frame, text="确定", command=on_ok)
            ok_button.pack(side=tk.LEFT, padx=5)
            
            cancel_button = tk.Button(button_frame, text="取消", command=on_cancel)
            cancel_button.pack(side=tk.LEFT, padx=5)
            
            # 绑定回车键和ESC键
            dialog.bind("<Return>", lambda e: on_ok())
            dialog.bind("<Escape>", lambda e: on_cancel())
            
            # 等待对话框关闭
            dialog.wait_window(dialog)
            return result[0]
        
        clipboard_content = get_input()
        # 如果用户取消了输入，退出程序
        if clipboard_content is None:
            import os
            os._exit(0)  # 强制终止进程
        
        root.destroy()  # 销毁临时根窗口

    # 数据库配置信息
    db_info = {
        'path': '/Users/yanzhang/Documents/Database/Finance.db',  # 数据库路径
        'table': 'Earning',  # 数据表名称
        'condition': f"name = '{clipboard_content}'" if clipboard_content else "",
        'fields': '*',  # 查询全部字段
        'include_condition': True if clipboard_content else False
    }
    
    create_main_window(db_info)