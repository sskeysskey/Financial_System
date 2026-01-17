import sqlite3
import os
import html
import webbrowser
import platform  # <--- 新增

# ================= 配置区域 (跨平台修改) =================

# 1. 动态获取主目录
USER_HOME = os.path.expanduser("~")

# 2. 定义基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")

# 3. 默认数据库路径
DEFAULT_DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")

# 4. 默认报告输出目录
DEFAULT_REPORT_DIR = DOWNLOADS_DIR

# ========================================================

def generate_html_report(db_name, tables_data, output_file='db_visualization.html'):
    """
    根据提取的数据库信息生成HTML报告。
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
        is_all = data['is_all']
        
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

        # 表内容预览标题动态化
        display_title = "全部数据内容" if is_all else f"内容预览 (前 {len(content_preview)} 行)"
        html_content += f"<h3>{display_title}</h3>"
        
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

# --- 修改部分：增加 target_tables 参数 ---
def visualize_sqlite_db(db_path, output_dir, content_limit=100, target_tables=None):
    """
    :param content_limit: 可以是整数(如 500)，也可以是字符串 'all' 表示显示全部。
    """
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在于 '{db_path}'")
        return

    # 判断是否显示全部
    show_all = False
    if isinstance(content_limit, str) and content_limit.lower() == 'all':
        show_all = True

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
        all_tables = [row[0] for row in cursor.fetchall()]

        # --- 核心逻辑修改：过滤表名 ---
        if target_tables:
            # 只保留在 target_tables 列表中的表，并忽略大小写差异（可选）
            tables = [t for t in all_tables if t in target_tables]
            if not tables:
                print(f"警告: 在数据库中未找到指定的表 {target_tables}。")
                return
        else:
            tables = all_tables

        print(f"正在处理以下表: {', '.join(tables)}")

        # 2. 遍历确定的表
        for table_name in tables:
            print(f"正在处理表: {table_name}...")
            tables_data[table_name] = {'is_all': show_all}
            
            # a. 获取表结构和所有列名
            cursor.execute(f'PRAGMA table_info("{table_name}");')
            schema = cursor.fetchall()
            tables_data[table_name]['schema'] = schema
            col_names = [s[1] for s in schema]

            # 智能排序
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

            # --- 修改部分：根据 show_all 构建不同的 SQL ---
            if show_all:
                # 全部显示：直接查询并排序
                sql_query = f'SELECT {select_clause} FROM "{table_name}" ORDER BY "{order_col}" DESC;'
            else:
                # 确保 content_limit 是整数，防止字符串格式化进 SQL 时出错
                content_limit = int(content_limit) 
                
                # 限制显示：使用子查询获取最新的 N 行
                sql_query = f"""
                SELECT {select_clause}
                FROM (
                    SELECT * FROM "{table_name}"
                    ORDER BY "{order_col}" DESC
                    LIMIT {content_limit}
                ) AS sub
                ORDER BY "{order_col}" DESC;
                """
            
            # 执行查询
            cursor.execute(sql_query)
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
        # <--- 跨平台修改：处理 Windows 路径反斜杠和 file:// 格式 --->
        real_path = os.path.realpath(report_path)
        if os.name == 'nt':
            url = 'file:///' + real_path.replace('\\', '/')
        else:
            url = 'file://' + real_path
            
        webbrowser.open_new_tab(url)

# --- 主程序入口 ---
if __name__ == "__main__":
    # --- 修改部分 4: 使用跨平台配置路径 ---
    database_file_path = DEFAULT_DB_PATH
    report_save_directory = DEFAULT_REPORT_DIR
    
    # --- 配置项 1: 指定要显示的表 (None 表示全部) ---
    # 场景1：只看 Options
    my_target_tables = ["Options"]
    
    # 场景2：看 Options 和 Bonds
    # my_target_tables = ["Options", "Bonds"]
    
    # 场景3：看所有表（设为 None 或空列表 []）
    # my_target_tables = None 

    # --- 配置项 2: 数据显示量 ---
    # 选项 A: 显示固定行数，例如 500
    # my_content_limit = 500
    
    # 选项 B: 显示全部数据，设置为 'all'
    my_content_limit = 'all'
    
    # 调用时传入 target_tables 参数
    visualize_sqlite_db(
        database_file_path, 
        output_dir=report_save_directory, 
        content_limit=my_content_limit,
        target_tables=my_target_tables
    )
