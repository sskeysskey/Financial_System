import sys
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

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
    
    # 注意：此处已移除原先在找不到数据时会退出程序的代码块。
    # 新的逻辑可以更好地处理（例如删除最后一条记录后）列表为空的情况。

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
    # 首先，确定要检查的初始 Symbol
    if len(sys.argv) > 1:
        current_symbol = sys.argv[1].upper()
    else:
        # 如果没有命令行参数，则初始 Symbol 为空，将直接触发弹窗询问
        current_symbol = None

    # 数据库固定信息
    db_path = '/Users/yanzhang/Coding/Database/Finance.db'
    table_name = 'Earning'

    # 循环直到找到一个有数据的 Symbol 或者用户取消操作
    while True:
        rows = []
        # 只有在 current_symbol 有效时才查询数据库
        if current_symbol:
            condition = f"name = '{current_symbol}'"
            _, rows = query_database_data(db_path, table_name, condition, '*', True)

        if rows:
            # 找到了数据，跳出循环，准备创建主窗口
            break
        else:
            # 如果没有找到数据（或者初始就没有 Symbol），则弹窗让用户输入
            # 创建一个临时的 Tk 根窗口以承载 simpledialog
            prompt_root = tk.Tk()
            prompt_root.withdraw()  # 隐藏这个临时窗口

            prompt_text = "请输入 Symbol:"
            # 如果是查询失败，提示用户上一个失败的 Symbol
            if current_symbol:
                prompt_text = f"在数据库中未找到 Symbol: '{current_symbol}'\n\n请输入新的 Symbol (或取消以退出):"

            new_symbol = simpledialog.askstring(
                "输入 Symbol",
                prompt_text,
                parent=prompt_root
            )
            
            prompt_root.destroy() # 销毁临时窗口

            if new_symbol:
                # 用户输入了新的 Symbol，更新它并继续下一次循环
                current_symbol = new_symbol.strip().upper()
            else:
                # 如果用户点击了“取消”或关闭了对话框，则退出整个程序
                sys.exit(0)

    # 当循环结束时，我们保证 current_symbol 是一个有效的、在数据库中有对应数据的 Symbol
    # 现在，根据这个有效的 Symbol 创建 db_info
    db_info = {
        'path': db_path,
        'table': table_name,
        'condition': f"name = '{current_symbol}'",
        'fields': '*',
        'include_condition': True
    }
    
    # 使用包含有效数据的 db_info 创建并运行主应用窗口
    create_main_window(db_info)