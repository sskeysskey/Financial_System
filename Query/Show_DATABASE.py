import sqlite3
import os
import html
import webbrowser

def generate_html_report(db_name, tables_data, output_file='db_visualization.html'):
    """
    根据提取的数据库信息生成HTML报告。

    :param db_name: 数据库的名称
    :param tables_data: 一个字典，包含每个表的结构和内容
    :param output_file: 输出的HTML文件名 (现在是包含完整路径的文件名)
    """
    # HTML模板的开始部分，包含CSS样式
    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据库可视化报告: {html.escape(db_name)}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f8f9fa;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: #fff;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1, h2, h3 {{
            color: #0056b3;
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 10px;
        }}
        h1 {{ font-size: 2em; }}
        h2 {{ font-size: 1.75em; margin-top: 40px; }}
        h3 {{ font-size: 1.25em; color: #17a2b8; border-bottom: none; margin-top: 20px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        th, td {{
            border: 1px solid #dee2e6;
            padding: 10px 12px;
            text-align: left;
            vertical-align: top;
        }}
        th {{
            background-color: #f2f2f2;
            font-weight: 600;
            position: sticky;
            top: 0; /* For sticky headers */
        }}
        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        tr:hover {{
            background-color: #e9ecef;
        }}
        .table-container {{
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
            border-radius: 4px;
        }}
        details {{
            border: 1px solid #ccc;
            border-radius: 5px;
            margin-bottom: 15px;
            padding: 10px;
            background-color: #fff;
        }}
        summary {{
            font-weight: bold;
            font-size: 1.4em;
            cursor: pointer;
            padding: 10px;
            color: #004085;
            background-color: #cce5ff;
            border-radius: 4px;
            margin: -10px; /* Adjust to fit within details padding */
            padding-left: 20px;
        }}
        summary:hover {{
            background-color: #b8daff;
        }}
        .toc {{ /* Table of Contents */
            background: #eef;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 30px;
        }}
        .toc ul {{
            list-style-type: none;
            padding: 0;
        }}
        .toc li a {{
            text-decoration: none;
            color: #0056b3;
        }}
        .toc li a:hover {{
            text-decoration: underline;
        }}
        /* Responsive design for smaller screens */
        @media (max-width: 768px) {{
            body {{ padding: 10px; }}
            .container {{ padding: 15px; }}
            h1 {{ font-size: 1.5em; }}
            h2 {{ font-size: 1.25em; }}
            th, td {{ padding: 6px 8px; }}
            .table-container {{ max-height: 300px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>数据库报告: {html.escape(db_name)}</h1>
    """

    # 添加目录 (Table of Contents)
    html_content += '<div class="toc"><h3>数据库表索引</h3><ul>'
    for table_name in tables_data:
        html_content += f'<li><a href="#{table_name}">{html.escape(table_name)}</a></li>'
    html_content += '</ul></div>'

    # 为每个表生成详细信息
    for table_name, data in tables_data.items():
        schema = data['schema']
        content_preview = data['content']
        content_headers = data['content_headers']
        
        # 使用<details>和<summary>创建可折叠部分
        html_content += f"""
        <details id="{table_name}" open>
            <summary>{html.escape(table_name)}</summary>
            <div style="padding: 15px;">
        """

        # 表结构
        html_content += "<h3>表结构 (Schema)</h3>"
        if schema:
            html_content += '<div class="table-container"><table><thead><tr><th>列ID</th><th>名称</th><th>类型</th><th>非空</th><th>默认值</th><th>主键</th></tr></thead><tbody>'
            for row in schema:
                # (cid, name, type, notnull, dflt_value, pk)
                html_content += f"<tr><td>{row[0]}</td><td>{html.escape(str(row[1]))}</td><td>{html.escape(str(row[2]))}</td><td>{'是' if row[3] else '否'}</td><td>{html.escape(str(row[4]))}</td><td>{'是' if row[5] else '否'}</td></tr>"
            html_content += "</tbody></table></div>"
        else:
            html_content += "<p>无法获取表结构信息。</p>"

        # 表内容预览
        html_content += f"<h3>内容预览 (前 {len(content_preview)} 行)</h3>"
        if content_preview:
            html_content += '<div class="table-container"><table><thead><tr>'
            for header in content_headers:
                html_content += f"<th>{html.escape(header)}</th>"
            html_content += "</tr></thead><tbody>"
            for row in content_preview:
                html_content += "<tr>"
                for cell in row:
                    # 对每个单元格内容进行HTML转义，防止特殊字符破坏页面结构
                    cell_content = html.escape(str(cell)) if cell is not None else "<i>NULL</i>"
                    html_content += f"<td>{cell_content}</td>"
                html_content += "</tr>"
            html_content += "</tbody></table></div>"
        else:
            html_content += "<p>该表为空或无内容可预览。</p>"
        
        html_content += "</div></details>"

    # HTML模板的结尾部分
    html_content += """
    </div>
</body>
</html>
    """
    
    # 确保目标目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"已创建目录: {output_dir}")

    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"报告已生成: {output_file}")
    return os.path.abspath(output_file)

# --- 修改部分 1: 增加 output_dir 参数 ---
def visualize_sqlite_db(db_path, output_dir, content_limit=100):
    """
    连接到SQLite数据库，提取信息，并生成可视化报告。
    (此版本已更新，可自动格式化 changed_at 并智能排序)

    :param db_path: SQLite数据库文件的路径
    :param output_dir: 生成的HTML报告的输出目录
    :param content_limit: 每个表预览内容的行数限制
    """
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在于 '{db_path}'")
        return

    tables_data = {}
    conn = None  # 在 try 外部初始化 conn
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path, timeout=60.0)
        cursor = conn.cursor()

        # 1. 获取所有用户表名（过滤掉 sqlite_ 开头的系统表）
        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            AND name NOT LIKE 'sqlite_%';
        """)
        tables = [row[0] for row in cursor.fetchall()]
        print(f"在数据库中找到 {len(tables)} 个表: {', '.join(tables)}")

        # 2. 遍历每个表，获取结构和内容
        for table_name in tables:
            print(f"正在处理表: {table_name}...")
            tables_data[table_name] = {}

            # a. 获取表结构和所有列名
            cursor.execute(f'PRAGMA table_info("{table_name}");')
            schema = cursor.fetchall()
            tables_data[table_name]['schema'] = schema
            col_names = [s[1] for s in schema]

            # ==================== 新增/修改部分开始 ====================

            # b. 智能决定用于排序的列，使查询更健壮
            if 'id' in col_names:
                order_col = 'id'
            elif 'date' in col_names:
                order_col = 'date'
            elif 'changed_at' in col_names:
                order_col = 'changed_at'
            else:
                order_col = 'rowid' # 使用 rowid 作为最后的保障

            # c. 动态构建 SELECT 子句，用于格式化 changed_at
            select_fields = []
            if 'changed_at' in col_names:
                for col in col_names:
                    if col == 'changed_at':
                        # 对 changed_at 列应用格式化和时区转换
                        select_fields.append(f"strftime('%Y-%m-%d %H:%M:%S', {col}, 'localtime') AS {col}")
                    else:
                        # 其他列保持原样，使用引号避免关键字问题
                        select_fields.append(f'"{col}"')
                select_clause = ", ".join(select_fields)
            else:
                # 如果没有 changed_at 列，就查询所有字段
                select_clause = "*"

            # d. 构建最终的、更强大的SQL查询语句
            #    注意：列名和表名都用双引号括起来，以支持包含特殊字符的名称
            sql_query = f"""
            SELECT {select_clause}
            FROM (
                SELECT * FROM "{table_name}"
                ORDER BY "{order_col}" DESC
                LIMIT {content_limit}
            ) AS sub
            ORDER BY "{order_col}" DESC;
            """
            print(f"为表 '{table_name}' 执行的SQL: {sql_query.strip()}")
            
            # 执行查询
            cursor.execute(sql_query)
            
            # ==================== 新增/修改部分结束 ====================
            
            content_preview = cursor.fetchall()
            # 获取列名
            content_headers = [description[0] for description in cursor.description] if cursor.description else []
            
            tables_data[table_name]['content'] = content_preview
            tables_data[table_name]['content_headers'] = content_headers

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        return
    finally:
        if conn:
            conn.close()

    # --- 修改部分 2: 构建完整的输出路径 ---
    db_name = os.path.basename(db_path)
    # 为了避免文件名冲突，可以基于数据库名来命名HTML文件
    output_filename = f"{os.path.splitext(db_name)[0]}_visualization.html"
    # 使用 os.path.join 来创建完整、跨平台的输出路径
    report_output_path = os.path.join(output_dir, output_filename)

    # 3. 生成HTML报告
    # --- 修改部分 3: 将新的完整路径传递给生成函数 ---
    report_path = generate_html_report(db_name, tables_data, output_file=report_output_path)
    
    # 4. 在浏览器中打开报告
    if report_path:
        webbrowser.open_new_tab(f'file://{report_path}')

# --- 主程序入口 ---
if __name__ == "__main__":
    # 请将这里的路径修改为您自己的数据库文件路径
    # 对于Windows用户，路径可能像这样: r"C:\Users\YourUser\Documents\Database\Finance.db"
    database_file_path = "/Users/yanzhang/Coding/Database/Finance.db"
    # database_file_path = "/Users/yanzhang/Downloads/user_data.db"
    
    # --- 修改部分 4: 指定HTML报告的输出目录 ---
    # 这是您希望保存HTML文件的目录
    report_save_directory = "/Users/yanzhang/Downloads"
    
    # 调用主函数开始执行，并传入输出目录
    visualize_sqlite_db(database_file_path, output_dir=report_save_directory, content_limit=500)