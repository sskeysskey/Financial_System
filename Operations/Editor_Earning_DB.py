import sys
import sqlite3
import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

USER_HOME = os.path.expanduser("~")

# 查询数据库，返回列名和记录数据
def query_database_data(db_file, table_name, condition, fields, include_condition):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # 按照 date 和 name 排序，因为没有 id 了
    order_clause = "ORDER BY date DESC, name ASC"
    if include_condition and condition:
        query = f"SELECT {fields} FROM {table_name} WHERE {condition} {order_clause};"
    else:
        query = f"SELECT {fields} FROM {table_name} {order_clause};"
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description] if rows else []
    conn.close()
    return columns, rows

# 更新记录：改为根据 date 和 name 定位
def update_record(db_file, table_name, old_date, old_name, new_values):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # 动态拼接 set 部分
    set_clause = ", ".join([f"{col} = ?" for col in new_values.keys()])
    # 使用 date 和 name 作为唯一标识
    sql = f"UPDATE {table_name} SET {set_clause} WHERE date = ? AND name = ?"
    params = list(new_values.values()) + [old_date, old_name]
    cursor.execute(sql, params)
    conn.commit()
    conn.close()

# 删除记录：改为根据 date 和 name 定位
def delete_record(db_file, table_name, date, name):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    sql = f"DELETE FROM {table_name} WHERE date = ? AND name = ?"
    cursor.execute(sql, (date, name))
    conn.commit()
    conn.close()

# 刷新 Treeview
def refresh_treeview(tree, db_info):
    for item in tree.get_children():
        tree.delete(item)
    
    columns, rows = query_database_data(db_info['path'],
                                          db_info['table'],
                                          db_info['condition'],
                                          db_info['fields'],
                                          db_info['include_condition'])
    
    tree["columns"] = columns
    tree["show"] = "headings"
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="w", width=100)
    
    for row in rows:
        tree.insert("", tk.END, values=row)

# 打开编辑窗口
def open_edit_window(record, columns, db_info, tree, root):
    edit_win = tk.Toplevel(root)
    edit_win.title("编辑记录")
    edit_win.bind("<Escape>", lambda e: edit_win.destroy())
    
    # 获取原始的 date 和 name，用于定位记录
    date_idx = columns.index("date")
    name_idx = columns.index("name")
    old_date = record[date_idx]
    old_name = record[name_idx]
    
    entries = {}
    
    for idx, col in enumerate(columns):
        tk.Label(edit_win, text=col).grid(row=idx, column=0, padx=5, pady=5, sticky="e")
        entry = tk.Entry(edit_win, width=30)
        entry.insert(0, record[idx])
        entry.grid(row=idx, column=1, padx=5, pady=5)
        
        # date 和 name 作为主键，设为只读，防止用户修改导致无法定位
        if col in ["date", "name"]:
            entry.config(state="readonly")
        
        entries[col] = entry

    def save_changes():
        new_values = {}
        for col in columns:
            if col in ["date", "name"]: continue # 不更新主键
            new_values[col] = entries[col].get()
        try:
            update_record(db_info['path'], db_info['table'], old_date, old_name, new_values)
            edit_win.destroy()
            refresh_treeview(tree, db_info)
        except Exception as e:
            messagebox.showerror("错误", str(e))
    
    def delete_this_record():
        if messagebox.askyesno("确认删除", "是否要删除该记录？"):
            try:
                delete_record(db_info['path'], db_info['table'], old_date, old_name)
                messagebox.showinfo("成功", "记录删除成功！")
                edit_win.destroy()
                refresh_treeview(tree, db_info)
            except Exception as e:
                messagebox.showerror("错误", str(e))
    
    edit_win.bind("<Return>", lambda e: save_changes())
    tk.Button(edit_win, text="保存修改", command=save_changes).grid(row=len(columns), column=0, padx=5, pady=10)
    tk.Button(edit_win, text="删除记录", command=delete_this_record).grid(row=len(columns), column=1, padx=5, pady=10)

def on_double_click(event, tree, db_info, columns, root):
    selected = tree.selection()
    if selected:
        record = tree.item(selected[0], "values")
        open_edit_window(record, columns, db_info, tree, root)

def create_main_window(db_info):
    root = tk.Tk()
    root.title("数据库查询与编辑")
    root.geometry("900x600")
    root.lift()
    root.focus_force()
    
    should_exit = [False]
    def on_closing():
        should_exit[0] = True
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.bind("<Escape>", lambda e: on_closing())

    frame = tk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True)
    
    tree = ttk.Treeview(frame)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=vsb.set)
    
    refresh_treeview(tree, db_info)
    
    def delete_selected_record(event):
        selected = tree.selection()
        if selected:
            record = tree.item(selected[0], "values")
            cols = tree["columns"]
            # 获取定位信息
            date_val = record[cols.index("date")]
            name_val = record[cols.index("name")]
            
            if messagebox.askyesno("确认删除", "是否要删除该记录？"):
                try:
                    delete_record(db_info['path'], db_info['table'], date_val, name_val)
                    messagebox.showinfo("成功", "记录删除成功！")
                    refresh_treeview(tree, db_info)
                except Exception as e:
                    messagebox.showerror("错误", str(e))
    
    root.bind("<BackSpace>", delete_selected_record)
    tree.bind("<Double-1>", lambda event: on_double_click(event, tree, db_info, tree["columns"], root))
    
    root.mainloop()
    if should_exit[0]:
        os._exit(0)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        current_symbol = sys.argv[1].upper()
    else:
        current_symbol = None

    db_path = os.path.join(USER_HOME, 'Coding/Database/Finance.db')
    table_name = 'Earning' # 注意：如果需要切换表，这里可能需要逻辑支持

    while True:
        rows = []
        if current_symbol:
            condition = f"name = '{current_symbol}'"
            _, rows = query_database_data(db_path, table_name, condition, '*', True)

        if rows:
            break
        else:
            prompt_root = tk.Tk()
            prompt_root.withdraw()
            prompt_text = "请输入 Symbol:"
            if current_symbol:
                prompt_text = f"在数据库中未找到 Symbol: '{current_symbol}'\n\n请输入新的 Symbol (或取消以退出):"
            new_symbol = simpledialog.askstring("输入 Symbol", prompt_text, parent=prompt_root)
            prompt_root.destroy()

            if new_symbol:
                current_symbol = new_symbol.strip().upper()
            else:
                sys.exit(0)

    db_info = {
        'path': db_path,
        'table': table_name,
        'condition': f"name = '{current_symbol}'",
        'fields': '*',
        'include_condition': True
    }
    
    create_main_window(db_info)