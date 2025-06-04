import json
import sqlite3
from datetime import date
from dateutil.relativedelta import relativedelta # For easy date calculations like "6 months ago"
import os

# --- Configuration ---
DB_PATH = "/Users/yanzhang/Documents/Database/Finance.db"
JSON_PATH = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
OUTPUT_PATH = "/Users/yanzhang/Documents/News/highlow.txt"

# Categories to process as per your request
TARGET_CATEGORIES = [
    "Bonds", "Currencies", "Crypto", "Indices",
    "Commodities", "ETFs", "Economics"
]

# Time intervals and their corresponding labels for the output file
# The relativedelta objects represent "going back in time"
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
        conn.row_factory = sqlite3.Row # Access columns by name
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
        # This can happen if the table doesn't exist or has an unexpected structure
        print(f"Warning: Could not query table '{table_name}' for symbol '{symbol}'. Error: {e}. Skipping symbol.")
        return None


def get_prices_in_range(cursor, table_name, symbol, start_date_str, end_date_str):
    """Fetches all prices for a symbol within a given date range."""
    try:
        query = f'SELECT price FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?'
        cursor.execute(query, (symbol, start_date_str, end_date_str))
        # Filter out None prices that might be in the database
        return [row['price'] for row in cursor.fetchall() if row['price'] is not None]
    except sqlite3.OperationalError as e:
        print(f"Warning: Could not query price range in table '{table_name}' for symbol '{symbol}'. Error: {e}. Skipping range.")
        return []


def main():
    """Main function to perform the analysis and write the output."""
    print("Starting financial analysis...")

    # Ensure output directory exists
    output_dir = os.path.dirname(OUTPUT_PATH)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    try:
        all_sectors_data = load_json_data(JSON_PATH)
        conn = get_db_connection(DB_PATH)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Critical setup error: {e}. Exiting.")
        return

    # Initialize results structure
    # Example: results = {"[6 months]": {"Low": [], "High": []}, ...}
    results = {label: {"Low": [], "High": []} for label in TIME_INTERVALS_CONFIG.keys()}

    for category_name in TARGET_CATEGORIES:
        if category_name not in all_sectors_data:
            print(f"Warning: Category '{category_name}' not found in JSON. Skipping.")
            continue

        symbols_in_category = all_sectors_data[category_name]
        if not symbols_in_category:
            # print(f"Info: No symbols in category '{category_name}'. Skipping.") # Can be verbose
            continue

        table_name = category_name # As per problem: table name matches category name

        print(f"\nProcessing Category: {table_name}")
        for symbol_name in symbols_in_category:
            print(f"  Analyzing Symbol: {symbol_name}")

            latest_data = get_latest_price_and_date(cursor, table_name, symbol_name)

            if not latest_data:
                print(f"    No data found for symbol '{symbol_name}' in table '{table_name}'.")
                continue

            try:
                latest_date_str, latest_price = latest_data['date'], latest_data['price']
                # Convert date string (YYYY-MM-DD) to a date object
                latest_date_obj = date.fromisoformat(latest_date_str)
            except (TypeError, ValueError) as e:
                print(f"    Invalid date format or data for {symbol_name} ('{latest_date_str}'). Error: {e}. Skipping.")
                continue
            
            if latest_price is None: # Check if price is NULL
                print(f"    Latest price for {symbol_name} on {latest_date_str} is NULL. Skipping.")
                continue

            print(f"    Latest price for {symbol_name}: {latest_price} on {latest_date_str}")

            for interval_label, time_delta in TIME_INTERVALS_CONFIG.items():
                # Calculate the start date for the interval
                start_date_obj = latest_date_obj + time_delta
                start_date_str = start_date_obj.isoformat()

                # Fetch all prices for the symbol within this historical interval (inclusive of the latest date)
                prices_in_interval = get_prices_in_range(cursor, table_name, symbol_name, start_date_str, latest_date_str)

                if not prices_in_interval:
                    # print(f"      No price data for {symbol_name} in interval {interval_label} ({start_date_str} to {latest_date_str}).")
                    continue
                
                min_price_in_interval = min(prices_in_interval)
                max_price_in_interval = max(prices_in_interval)

                # print(f"      Interval {interval_label} ({start_date_str} to {latest_date_str}): Min={min_price_in_interval}, Max={max_price_in_interval}")

                if latest_price == min_price_in_interval:
                    if symbol_name not in results[interval_label]["Low"]:
                        results[interval_label]["Low"].append(symbol_name)
                        print(f"      !!! {symbol_name} is at a {interval_label} LOW: {latest_price}")
                
                if latest_price == max_price_in_interval:
                    if symbol_name not in results[interval_label]["High"]:
                        results[interval_label]["High"].append(symbol_name)
                        print(f"      !!! {symbol_name} is at a {interval_label} HIGH: {latest_price}")

    # Close the database connection
    if conn:
        conn.close()

    # Write results to the output file
    print(f"\nWriting results to {OUTPUT_PATH}...")
    try:
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as outfile:
            for interval_label, data in results.items():
                outfile.write(f"{interval_label}\n")
                outfile.write("Low:\n")
                if data["Low"]:
                    outfile.write(", ".join(data["Low"]) + "\n")
                else:
                    outfile.write("\n") # Empty line if no lows for this period

                outfile.write("High:\n")
                if data["High"]:
                    outfile.write(", ".join(data["High"]) + "\n")
                else:
                    outfile.write("\n") # Empty line if no highs for this period
                
                if interval_label != list(results.keys())[-1]: # Add extra newline unless it's the last block
                    outfile.write("\n")

        print("Analysis complete. Output file generated.")
    except IOError:
        print(f"Error: Could not write to output file {OUTPUT_PATH}")

if __name__ == "__main__":
    main()