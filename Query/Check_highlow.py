import json
import sqlite3
from datetime import date
from dateutil.relativedelta import relativedelta
import os
import re # For parsing the backup file
from collections import defaultdict
import copy # For deep copying results

# --- Configuration ---
DB_PATH = "/Users/yanzhang/Documents/Database/Finance.db"
JSON_PATH = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
OUTPUT_PATH = "/Users/yanzhang/Documents/News/highlow.txt"
BACKUP_OUTPUT_PATH = "/Users/yanzhang/Documents/News/backup/highlow.txt" # Path for the backup file

# Categories to process as per your request
TARGET_CATEGORIES = [
    "Bonds", "Currencies", "Crypto", "Indices",
    "Commodities", "ETFs", "Economics"
]

# Time intervals and their corresponding labels for the output file
TIME_INTERVALS_CONFIG = {
    "[1 months]": relativedelta(months=-1),
    "[3 months]": relativedelta(months=-3),
    "[6 months]": relativedelta(months=-6),
    "[1Y]": relativedelta(years=-1),
    "[2Y]": relativedelta(years=-2),
    "[5Y]": relativedelta(years=-5)
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
    """Parses a highlow.txt file into a dictionary structure."""
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
            print(f"  Analyzing Symbol: {symbol_name}")
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
            print(f"    Latest price for {symbol_name}: {latest_price} on {latest_date_str}")

            for interval_label, time_delta in TIME_INTERVALS_CONFIG.items():
                start_date_obj = latest_date_obj + time_delta
                start_date_str = start_date_obj.isoformat()
                prices_in_interval = get_prices_in_range(cursor, table_name, symbol_name, start_date_str, latest_date_str)

                if not prices_in_interval:
                    continue
                
                min_price_in_interval = min(prices_in_interval)
                max_price_in_interval = max(prices_in_interval)

                if latest_price == min_price_in_interval:
                    if symbol_name not in current_run_results[interval_label]["Low"]:
                        current_run_results[interval_label]["Low"].append(symbol_name)
                        print(f"      !!! {symbol_name} is at a {interval_label} LOW: {latest_price}")
                
                if latest_price == max_price_in_interval:
                    if symbol_name not in current_run_results[interval_label]["High"]:
                        current_run_results[interval_label]["High"].append(symbol_name)
                        print(f"      !!! {symbol_name} is at a {interval_label} HIGH: {latest_price}")
    if conn:
        conn.close()

    # --- New logic for comparing with backup and adding (new) tags ---
    print(f"\nReading backup file from {BACKUP_OUTPUT_PATH}...")
    backup_results_parsed = parse_highlow_file(BACKUP_OUTPUT_PATH)

    # Create a deep copy of current_run_results to modify for the main output file (with "(new)" tags)
    # The current_run_results itself will be saved to backup without "(new)" tags.
    results_for_main_output = copy.deepcopy(current_run_results)

    print("Comparing current results with backup and adding '(new)' tags...")
    for interval_label in TIME_INTERVALS_CONFIG.keys():
        for list_type in ["Low", "High"]: # "Low" or "High"
            newly_generated_symbols = results_for_main_output[interval_label][list_type]
            backup_symbols = backup_results_parsed.get(interval_label, {}).get(list_type, [])
            
            # Create a new list to hold symbols, possibly with "(new)" tags
            updated_symbol_list = []
            for symbol in newly_generated_symbols:
                if symbol not in backup_symbols:
                    updated_symbol_list.append(f"{symbol}(new)")
                    print(f"  Marked as new in {interval_label} {list_type}: {symbol}")
                else:
                    updated_symbol_list.append(symbol)
            results_for_main_output[interval_label][list_type] = updated_symbol_list
    # --- End of new logic ---

    # Write results to the main output file (with "(new)" tags)
    print(f"\nWriting results with (new) tags to {OUTPUT_PATH}...")
    write_results_to_file(results_for_main_output, OUTPUT_PATH)

    # Write the raw current run results (without "(new)" tags) to the backup file, overwriting it
    print(f"\nUpdating backup file at {BACKUP_OUTPUT_PATH} with current raw results...")
    write_results_to_file(current_run_results, BACKUP_OUTPUT_PATH)

    print("\nAnalysis complete. Output files generated/updated.")

if __name__ == "__main__":
    main()