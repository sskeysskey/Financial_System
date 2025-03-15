import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
import pyperclip
import argparse

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
    
    columns, rows = query_database_data(db_info['path'], db_info['table'], 
                                          db_info['condition'], db_info['fields'], 
                                          db_info['include_condition'])
    
    if not rows:
        messagebox.showinfo("提示", "没有数据可显示")
        return
    
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
def open_edit_window(record, columns, db_info, tree):
    edit_win = tk.Toplevel()
    edit_win.title("编辑记录")
    
    # 添加ESC键绑定
    edit_win.bind("<Escape>", lambda e: edit_win.destroy())
    
    entries = {}
    # 针对每个字段创建一个标签和 Entry 控件来展示数据
    for idx, col in enumerate(columns):
        tk.Label(edit_win, text=col).grid(row=idx, column=0, padx=5, pady=5, sticky="e")
        entry = tk.Entry(edit_win, width=30)
        entry.insert(0, record[idx])
        entry.grid(row=idx, column=1, padx=5, pady=5)
        # 如果是 id 字段设为只读（假设 id 为主键）
        if col == "id":
            entry.config(state="readonly")
        entries[col] = entry

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
            messagebox.showinfo("成功", "记录更新成功！")
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

# 双击 Treeview 的事件响应函数
def on_double_click(event, tree, db_info, columns):
    selected = tree.selection()
    if selected:
        record = tree.item(selected[0], "values")
        open_edit_window(record, columns, db_info, tree)

# 创建主窗口，显示查询结果并实现交互编辑功能
def create_main_window(db_info):
    root = tk.Tk()
    root.title("数据库查询与编辑")
    root.geometry("900x600")
    
    # 自动激活窗口在最前台
    root.lift()
    root.focus_force()
    
    # 按 ESC 键关闭窗口退出程序
    root.bind("<Escape>", lambda e: root.destroy())

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
    
    # 双击时弹出编辑窗口
    tree.bind("<Double-1>", lambda event: on_double_click(event, tree, db_info, tree["columns"]))
    
    root.mainloop()

if __name__ == '__main__':
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='数据库查询程序')
    parser.add_argument('name', type=str, help='要查询的名称', default='')
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 数据库配置信息
    db_info = {
        'path': '/Users/yanzhang/Documents/Database/Finance.db',  # 数据库路径
        'table': 'Earning',  # 数据表名称
        'condition': f"name = '{args.name}'" if args.name else "",
        'fields': '*',  # 查询全部字段
        'include_condition': True if args.name else False
    }
    
    create_main_window(db_info)