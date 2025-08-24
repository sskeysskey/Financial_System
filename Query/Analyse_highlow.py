import json
import sqlite3
from datetime import date
from dateutil.relativedelta import relativedelta
import os
from collections import OrderedDict

# --- Configuration ---
DB_PATH = "/Users/yanzhang/Coding/Database/Finance.db"
JSON_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json"
OUTPUT_PATH = "/Users/yanzhang/Coding/News/HighLow.txt"
BACKUP_OUTPUT_PATH = "/Users/yanzhang/Coding/News/backup/HighLow.txt" # Path for the backup file

TARGET_CATEGORIES = [
    "Bonds", "Currencies", "Crypto", "Indices",
    "Commodities", "ETFs", "Economics"
]

# 修改为（注意插入顺序决定输出顺序）：
TIME_INTERVALS_CONFIG = {
    "[0.5 months]": relativedelta(days=-15),   # ← 新增半月
    "[1 months]":   relativedelta(months=-1),
    "[3 months]":   relativedelta(months=-3),
    "[6 months]":   relativedelta(months=-6),
    "[1Y]":         relativedelta(years=-1),
    "[2Y]":         relativedelta(years=-2),
    "[5Y]":         relativedelta(years=-5)
}

def get_db_connection(db_file):
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database {db_file}: {e}")
        raise

def load_json_data(json_file):
    """Loads data from a JSON file."""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: JSON file not found at {json_file}")
        raise
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {json_file}")
        raise

def get_latest_price_and_date(cursor, table_name, symbol):
    """Fetches the latest price and date for a given symbol in a table."""
    try:
        query = f'SELECT date, price FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1'
        cursor.execute(query, (symbol,))
        return cursor.fetchone()
    except sqlite3.OperationalError as e:
        print(f"Warning: Could not query table '{table_name}' for symbol '{symbol}'. Error: {e}. Skipping symbol.")
        return None

def get_prices_in_range(cursor, table_name, symbol, start_date_str, end_date_str):
    """Fetches all prices for a symbol within a given date range."""
    try:
        query = f'SELECT price FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?'
        cursor.execute(query, (symbol, start_date_str, end_date_str))
        return [row['price'] for row in cursor.fetchall() if row['price'] is not None]
    except sqlite3.OperationalError as e:
        print(f"Warning: Could not query price range in table '{table_name}' for symbol '{symbol}'. Error: {e}. Skipping range.")
        return []

def parse_highlow_file(filepath):
    """Parses a HighLow.txt file into a dictionary structure."""
    parsed_data = {label: {"Low": [], "High": []} for label in TIME_INTERVALS_CONFIG.keys()}
    current_interval_label = None
    current_list_type = None # "Low" or "High"

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("[") and line.endswith("]"):
                    current_interval_label = line
                    if current_interval_label not in parsed_data: # Handle unknown intervals gracefully
                        parsed_data[current_interval_label] = {"Low": [], "High": []}
                    current_list_type = None # Reset list type for new interval
                elif line.lower() == "low:":
                    current_list_type = "Low"
                elif line.lower() == "high:":
                    current_list_type = "High"
                elif current_interval_label and current_list_type:
                    # Remove (new) tags and split symbols
                    symbols = [s.replace("(new)", "").strip() for s in line.split(',') if s.strip()]
                    parsed_data[current_interval_label][current_list_type].extend(symbols)
    except FileNotFoundError:
        print(f"Info: Backup file {filepath} not found. Assuming all items are new.")
    except Exception as e:
        print(f"Error parsing backup file {filepath}: {e}")
    return parsed_data


def write_results_to_file(results_data, output_filepath):
    """Writes the results dictionary to the specified output file."""
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    try:
        with open(output_filepath, 'w', encoding='utf-8') as outfile:
            for interval_label, data in results_data.items():
                # ===== 新增逻辑：如果过滤后一个区间高低点都为空，则不输出该区间 =====
                if not data["Low"] and not data["High"]:
                    continue
                # =================================================================

                outfile.write(f"{interval_label}\n")
                outfile.write("Low:\n")
                if data["Low"]:
                    outfile.write(", ".join(data["Low"]) + "\n")
                else:
                    outfile.write("\n")

                outfile.write("High:\n")
                if data["High"]:
                    outfile.write(", ".join(data["High"]) + "\n")
                else:
                    outfile.write("\n")

                if interval_label != list(results_data.keys())[-1]:
                    outfile.write("\n")
        print(f"Successfully wrote results to {output_filepath}")
    except IOError as e:
        print(f"Error: Could not write to output file {output_filepath}. Error: {e}")


def main():
    """Main function to perform the analysis and write the output."""
    print("Starting financial analysis...")

    # Ensure output directories exist
    for path in [OUTPUT_PATH, BACKUP_OUTPUT_PATH]:
        output_dir = os.path.dirname(path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"Created directory: {output_dir}")

    try:
        all_sectors_data = load_json_data(JSON_PATH)
        conn = get_db_connection(DB_PATH)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Critical setup error: {e}. Exiting.")
        return

    # ===== 新增：提前获取所有ETF符号，方便后续筛选 =====
    etf_symbols = set(all_sectors_data.get("ETFs", []))
    # =================================================

    # This will hold the raw results from the current analysis (without "(new)" tags)
    current_run_results = {label: {"Low": [], "High": []} for label in TIME_INTERVALS_CONFIG.keys()}

    for category_name in TARGET_CATEGORIES:
        if category_name not in all_sectors_data:
            print(f"Warning: Category '{category_name}' not found in JSON. Skipping.")
            continue

        symbols_in_category = all_sectors_data[category_name]
        if not symbols_in_category:
            continue

        table_name = category_name
        print(f"\nProcessing Category: {table_name}")
        for symbol_name in symbols_in_category:
            # print(f"  Analyzing Symbol: {symbol_name}")
            latest_data = get_latest_price_and_date(cursor, table_name, symbol_name)

            if not latest_data:
                print(f"    No data found for symbol '{symbol_name}' in table '{table_name}'.")
                continue
            try:
                latest_date_str, latest_price = latest_data['date'], latest_data['price']
                latest_date_obj = date.fromisoformat(latest_date_str)
            except (TypeError, ValueError) as e:
                print(f"    Invalid date format or data for {symbol_name} ('{latest_date_str}'). Error: {e}. Skipping.")
                continue
            if latest_price is None:
                print(f"    Latest price for {symbol_name} on {latest_date_str} is NULL. Skipping.")
                continue
            # print(f"    Latest price for {symbol_name}: {latest_price} on {latest_date_str}")

            for interval_label, time_delta in TIME_INTERVALS_CONFIG.items():
                start_date_obj = latest_date_obj + time_delta
                start_date_str = start_date_obj.isoformat()
                prices_in_interval = get_prices_in_range(
                    cursor, table_name, symbol_name,
                    start_date_str, latest_date_str
                )

                # ===== 新增这两行 =====
                # 如果这个区间里只有最新一条（或根本没有）数据，就跳过，不当高低点
                if len(prices_in_interval) < 2:
                    continue
                # =======================

                min_price_in_interval = min(prices_in_interval)
                max_price_in_interval = max(prices_in_interval)

                if latest_price == min_price_in_interval:
                    if symbol_name not in current_run_results[interval_label]["Low"]:
                        current_run_results[interval_label]["Low"].append(symbol_name)
                        # print(f"      !!! {symbol_name} is at a {interval_label} LOW: {latest_price}")
                
                if latest_price == max_price_in_interval:
                    if symbol_name not in current_run_results[interval_label]["High"]:
                        current_run_results[interval_label]["High"].append(symbol_name)
                        # print(f"      !!! {symbol_name} is at a {interval_label} HIGH: {latest_price}")
    if conn:
        conn.close()

    # --- New logic for comparing with backup and adding (new) tags ---
    print(f"\nReading backup file from {BACKUP_OUTPUT_PATH}...")
    backup_results_parsed = parse_highlow_file(BACKUP_OUTPUT_PATH)

    # 构建一个只存放“新增”符号的结果字典
    results_for_main_output = {
        label: {"Low": [], "High": []}
        for label in TIME_INTERVALS_CONFIG.keys()
    }

    print("Filtering only newly appeared symbols (no '(new)' tag)...")
    for interval_label in TIME_INTERVALS_CONFIG.keys():
        for list_type in ("Low", "High"):
            current_symbols = current_run_results[interval_label][list_type]
            backup_symbols  = backup_results_parsed.get(interval_label, {}).get(list_type, [])
            # 只保留在 current_symbols 中但不在 backup_symbols 中的
            new_only = [sym for sym in current_symbols if sym not in backup_symbols]
            if new_only:
                print(f"  {interval_label} {list_type} 新增: {', '.join(new_only)}")
            results_for_main_output[interval_label][list_type] = new_only

    # ===== 修改部分：将过滤逻辑推广到Low和High =====
    print("\nApplying ETF High/Low filter for the main output file...")
    # 变量名修改得更通用
    ETF_SHORT_TERM_EXCLUSION_INTERVALS = ["[0.5 months]", "[1 months]", "[3 months]"]
    
    for interval_label, data in results_for_main_output.items():
        # 检查是否是需要过滤的短期区间
        if interval_label in ETF_SHORT_TERM_EXCLUSION_INTERVALS:
            # 同时处理 "Low" 和 "High" 列表
            for list_type in ("Low", "High"):
                symbol_list = data[list_type]
                if not symbol_list:
                    continue
                
                # 重建列表，只保留那些不是ETF的品种
                original_count = len(symbol_list)
                filtered_list = [symbol for symbol in symbol_list if symbol not in etf_symbols]
                
                if len(filtered_list) < original_count:
                    removed_count = original_count - len(filtered_list)
                    print(f"  Filtered out {removed_count} ETF(s) from '{interval_label}' {list_type} list for main output.")
                
                # 用过滤后的列表更新结果
                results_for_main_output[interval_label][list_type] = filtered_list
    # =================================================================

    has_any_new = any(
        results_for_main_output[label][lt]
        for label in results_for_main_output
        for lt in ("Low", "High")
    )

    # 只有在发现新增符号时才写主输出文件
    if has_any_new:
        # 只保留那些真正有新增的区间
        filtered_results = {
            label: data
            for label, data in results_for_main_output.items()
            if data["Low"] or data["High"]
        }

        # 1) 先倒序：5Y→2Y→1Y→6m→3m→1m
        rev_filtered = OrderedDict(reversed(list(filtered_results.items())))

        # 2) 跨区间去重：同一类型（Low/High）在更长区间出现过，就不在后面的区间显示
        cascade = OrderedDict()
        seen_low, seen_high = set(), set()
        for interval_label, data in rev_filtered.items():
            # 只取之前没出现过的
            new_low  = [s for s in data["Low"]  if s not in seen_low]
            new_high = [s for s in data["High"] if s not in seen_high]

            # 只有当去重后列表不为空时，才添加到最终结果中
            if new_low or new_high:
                cascade[interval_label] = {
                    "Low":  new_low,
                    "High": new_high
                }
                seen_low .update(new_low)
                seen_high.update(new_high)
        
        # 再次检查，因为去重后可能变为空
        if cascade:
            print(f"\nWriting cascaded new-only results to {OUTPUT_PATH}…")
            write_results_to_file(cascade, OUTPUT_PATH)
        else:
            print("\nNo new symbols remaining after cascading. Skip writing main output file.")

    else:
        print("\nNo new symbols found. Skip writing main output file.")

    # 无论是否有新增，都要用完整的 current_run_results 更新备份文件
    print(f"\nUpdating backup file at {BACKUP_OUTPUT_PATH} with current raw results...")
    write_results_to_file(current_run_results, BACKUP_OUTPUT_PATH)

    print("\nAnalysis complete. Output files generated/updated.")

if __name__ == "__main__":
    main()