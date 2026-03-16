import sqlite3
import csv
import time
import os
import json
import sys
import tkinter as tk
import subprocess
import threading
from tkinter import messagebox
from datetime import datetime, timedelta
from tqdm import tqdm

# ===== 新增导入 =====
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_BACKUP_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")

DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
OUTPUT_DIR = NEWS_BACKUP_DIR
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_panel.json")
BLACKLIST_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Blacklist.json")
ANALYSE_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Analyse_Options.py")

MARKET_CAP_THRESHOLD = 400000000000

today_str = datetime.now().strftime('%y%m%d')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f'Options_{today_str}.csv')

# ===== 并发配置 =====
MAX_WORKERS = 4          # 并发线程数 (建议 3-6，太高容易被 Yahoo 限流)
REQUEST_DELAY = 0.15     # 每个日期请求之间的间隔秒数

# ================= 1. 数据库操作 =================

def get_target_symbols(db_path, threshold, silent=False):
    if not silent:
        tqdm.write(f"正在连接数据库: {db_path}...")
    try:
        if not os.path.exists(db_path):
            tqdm.write(f"❌ 数据库文件不存在: {db_path}")
            return []
        conn = sqlite3.connect(db_path, timeout=60.0)
        cursor = conn.cursor()
        query = "SELECT symbol, marketcap FROM MNSPP WHERE marketcap > ? ORDER BY marketcap DESC"
        cursor.execute(query, (threshold,))
        symbols = cursor.fetchall()
        if not silent:
            tqdm.write(f"共找到 {len(symbols)} 个市值大于 {threshold} 的代码。")
        return symbols
    except Exception as e:
        tqdm.write(f"数据库读取错误: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# ================= 2. 数据处理工具函数 =================

def format_date(date_str):
    try:
        date_str = date_str.strip()
        dt = datetime.strptime(date_str, "%b %d, %Y")
        return dt.strftime("%Y/%m/%d")
    except ValueError:
        return date_str

def clean_number(num_str):
    if not num_str or num_str.strip() == '-' or num_str.strip() == '':
        return 0
    try:
        clean_str = num_str.replace(',', '').strip()
        return int(clean_str)
    except ValueError:
        return 0

def clean_price_and_multiply(price_str):
    if not price_str or price_str.strip() == '-' or price_str.strip() == '':
        return 0.0
    try:
        clean_str = price_str.replace(',', '').strip()
        price_val = float(clean_str)
        return round(price_val * 100, 2)
    except ValueError:
        return 0.0

def show_error_popup(symbol):
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror(
            "严重错误 - 程序终止",
            f"无法获取代码 [{symbol}] 的期权日期列表！\n\n已尝试重试均失败。\n程序将停止运行以避免数据缺失。"
        )
        root.destroy()
    except Exception as e:
        print(f"弹窗显示失败: {e}")

def update_sectors_json(symbol, json_path):
    try:
        if not os.path.exists(json_path):
            tqdm.write(f"⚠️ JSON 文件不存在，无法更新: {json_path}")
            return
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if "Options_zero" not in data:
            data["Options_zero"] = {}
        data["Options_zero"][symbol] = ""
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        tqdm.write(f"📝JSON已更新: [{symbol}] -> Options_zero")
    except Exception as e:
        tqdm.write(f"⚠️ 更新 JSON 失败: {e}")

def show_final_summary_popup_from_json(json_path):
    try:
        if not os.path.exists(json_path):
            return
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        zero_group = data.get("Options_zero", {})
        zero_list = list(zero_group.keys())
        if not zero_list:
            return
        count = len(zero_list)
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if count > 20:
            details = "\n".join(zero_list[:20]) + f"\n...以及其他 {count - 20} 个"
        else:
            details = "\n".join(zero_list)
        messagebox.showinfo(
            "数据质量监控报告 (Options_zero)",
            f"任务结束。\n\n"
            f"目前【Options_zero】分组中共有 {count} 个 Symbol。\n"
            f"这些 Symbol 因 Open Interest 数据无效已被记录，\n"
            f"并在下次运行时自动跳过。\n\n"
            f"列表如下：\n{details}"
        )
        root.destroy()
    except Exception as e:
        print(f"弹窗显示失败: {e}")

# ================= 3. 自动执行分析脚本 =================

def run_analysis_program():
    print("\n" + "=" * 50)
    print("🚀 准备启动分析程序...")
    if os.path.exists(ANALYSE_SCRIPT_PATH):
        try:
            print(f"📂 脚本路径: {ANALYSE_SCRIPT_PATH}")
            subprocess.run([sys.executable, ANALYSE_SCRIPT_PATH], check=True)
            print("✅ 分析程序执行完毕。")
        except subprocess.CalledProcessError as e:
            print(f"❌ 分析程序执行出错 (Exit Code: {e.returncode})")
        except Exception as e:
            print(f"❌ 启动分析程序时发生未知错误: {e}")
    else:
        print(f"⚠️ 未找到分析脚本文件: {ANALYSE_SCRIPT_PATH}")
    print("=" * 50 + "\n")

# ================= 4. 新增：yfinance 单 Symbol 抓取函数 =================

def fetch_single_symbol_options(symbol, max_retries=3):
    """
    使用 yfinance 直接获取单个 Symbol 的期权数据。
    无需浏览器，直接走 Yahoo Finance JSON 接口。

    返回: (symbol, data_rows, status)
        - data_rows: [[symbol, date, type, strike, oi, last_price], ...]
        - status: "ok" / "no_dates" / 错误信息字符串
    """
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            exp_dates = ticker.options  # tuple: ('2025-06-20', '2025-06-27', ...)

            if not exp_dates:
                return symbol, [], "no_dates"

            # 过滤 6 个月内的日期
            first_dt = datetime.strptime(exp_dates[0], "%Y-%m-%d")
            cutoff_dt = first_dt + timedelta(days=180)
            filtered_dates = [
                d for d in exp_dates
                if datetime.strptime(d, "%Y-%m-%d") <= cutoff_dt
            ]

            all_rows = []
            for exp_date_str in filtered_dates:
                formatted_date = datetime.strptime(exp_date_str, "%Y-%m-%d").strftime("%Y/%m/%d")

                try:
                    chain = ticker.option_chain(exp_date_str)
                except Exception:
                    continue

                # 处理 Calls
                if chain.calls is not None and not chain.calls.empty:
                    for _, row in chain.calls.iterrows():
                        strike = str(row['strike'])
                        oi = int(row['openInterest']) if pd.notna(row.get('openInterest')) else 0
                        lp = round(float(row['lastPrice']) * 100, 2) if pd.notna(row.get('lastPrice')) else 0.0
                        all_rows.append([symbol, formatted_date, 'Calls', strike, oi, lp])

                # 处理 Puts
                if chain.puts is not None and not chain.puts.empty:
                    for _, row in chain.puts.iterrows():
                        strike = str(row['strike'])
                        oi = int(row['openInterest']) if pd.notna(row.get('openInterest')) else 0
                        lp = round(float(row['lastPrice']) * 100, 2) if pd.notna(row.get('lastPrice')) else 0.0
                        all_rows.append([symbol, formatted_date, 'Puts', strike, oi, lp])

                # 微延迟防限流
                time.sleep(REQUEST_DELAY)

            return symbol, all_rows, "ok"

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))  # 指数退避: 2s, 4s
            else:
                return symbol, [], str(e)

    return symbol, [], "max_retries_exceeded"

# ================= 5. 爬虫核心逻辑 (已优化) =================

def scrape_options():
    # --- 1. 获取目标 Symbols (合并模式) --- (与原代码完全相同)

    json_options_set = set()
    json_pe_volume_set = set()
    json_pe_volume_up_set = set()
    json_zero_set = set()
    blacklist_options_set = set()
    json_pe_volume_high_set = set()
    json_pe_w_set = set()
    json_pe_deeper_set = set()
    json_etf_volume_high_set = set()
    json_etf_volume_low_set = set()

    count_json_options = 0
    count_json_pe_volume = 0
    count_json_pe_volume_up = 0
    count_json_zero = 0
    count_json_pe_volume_high = 0
    count_json_pe_w = 0
    count_json_pe_deeper = 0
    count_json_etf_volume_high = 0
    count_json_etf_volume_low = 0

    # 加载黑名单
    try:
        if os.path.exists(BLACKLIST_JSON_PATH):
            with open(BLACKLIST_JSON_PATH, 'r', encoding='utf-8') as f:
                bl_data = json.load(f)
                blacklist_options_set = {str(s).strip() for s in bl_data.get("Options", [])}
        else:
            tqdm.write(f"⚠️ 提示: 未找到黑名单文件: {BLACKLIST_JSON_PATH}")
    except Exception as e:
        tqdm.write(f"⚠️ 读取黑名单出错: {e}")

    # 从 Sectors_panel 加载基础列表
    try:
        if os.path.exists(SECTORS_JSON_PATH):
            with open(SECTORS_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                options_keys = data.get("Options", {}).keys()
                json_options_set = set(options_keys)
                count_json_options = len(json_options_set)

                pe_vol_keys = data.get("PE_Volume", {}).keys()
                json_pe_volume_set = set(pe_vol_keys)
                count_json_pe_volume = len(json_pe_volume_set)

                pe_vol_up_keys = data.get("PE_Volume_up", {}).keys()
                json_pe_volume_up_set = set(pe_vol_up_keys)
                count_json_pe_volume_up = len(json_pe_volume_up_set)

                zero_keys = data.get("Options_zero", {}).keys()
                json_zero_set = set(zero_keys)
                count_json_zero = len(json_zero_set)

                pe_vol_high_keys = data.get("PE_Volume_high", {}).keys()
                json_pe_volume_high_set = set(pe_vol_high_keys)
                count_json_pe_volume_high = len(json_pe_volume_high_set)

                pe_w_keys = data.get("PE_W", {}).keys()
                json_pe_w_set = set(pe_w_keys)
                count_json_pe_w = len(json_pe_w_set)

                pe_deeper_keys = data.get("PE_Deeper", {}).keys()
                json_pe_deeper_set = set(pe_deeper_keys)
                count_json_pe_deeper = len(json_pe_deeper_set)

                etf_vol_high_keys = data.get("ETF_Volume_high", {}).keys()
                json_etf_volume_high_set = set(etf_vol_high_keys)
                count_json_etf_volume_high = len(json_etf_volume_high_set)

                etf_vol_low_keys = data.get("ETF_Volume_low", {}).keys()
                json_etf_volume_low_set = set(etf_vol_low_keys)
                count_json_etf_volume_low = len(json_etf_volume_low_set)
        else:
            tqdm.write(f"⚠️ 警告: 未找到 JSON 文件: {SECTORS_JSON_PATH}")
    except Exception as e:
        tqdm.write(f"⚠️ 读取 JSON 配置文件出错: {e}")

    merged_symbols_set = (
        json_options_set
    )

    symbol_cap_map = {}
    try:
        if os.path.exists(DB_PATH):
            temp_conn = sqlite3.connect(DB_PATH, timeout=30.0)
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute("SELECT symbol, marketcap FROM MNSPP WHERE marketcap IS NOT NULL")
            all_caps = temp_cursor.fetchall()
            for s, c in all_caps:
                symbol_cap_map[s] = c
            temp_conn.close()
    except Exception as e:
        tqdm.write(f"⚠️ 读取数据库市值映射失败: {e}")

    custom_symbols_list = []
    for s in merged_symbols_set:
        cap = symbol_cap_map.get(s, 0)
        if not isinstance(cap, (int, float)):
            cap = 0
        custom_symbols_list.append((s, cap))

    db_symbols_list = get_target_symbols(DB_PATH, MARKET_CAP_THRESHOLD, silent=True)
    custom_names_set = {s[0] for s in custom_symbols_list}
    db_unique_list = [s for s in db_symbols_list if s[0] not in custom_names_set]
    all_symbols_before_blacklist = custom_symbols_list + db_unique_list

    total_exclusion_set = blacklist_options_set.union(json_zero_set)
    symbols = [s for s in all_symbols_before_blacklist if s[0] not in total_exclusion_set]
    blacklisted_count = len(all_symbols_before_blacklist) - len(symbols)

    if not symbols:
        tqdm.write("未找到任何 Symbol 或全部被黑名单/Options_zero 过滤，程序结束。")
        return

    # 检查已存在的 Symbol 并过滤
    existing_symbols = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    for row in reader:
                        if row and len(row) > 0:
                            existing_symbols.add(row[0])
        except Exception as e:
            tqdm.write(f"⚠️ 读取现有文件检查 Symbol 时出错: {e}，将重新抓取所有。")

    original_count = len(symbols)
    symbols = [s for s in symbols if s[0] not in existing_symbols]
    skipped_count = original_count - len(symbols)

    total_json_count = count_json_options

    log_msg = (
        f"任务列表加载完成: [JSON({total_json_count}) + 数据库({len(db_symbols_list)})] | "
        f"排除列表(Blacklist+Zero): {blacklisted_count} (其中Zero:{count_json_zero}) | "
        f"总去重: {len(symbols) + skipped_count} | "
        f"已完成: {skipped_count} | 待抓取: {len(symbols)}"
    )
    tqdm.write(log_msg)

    if not symbols:
        tqdm.write("✅ 所有目标 Symbol 均已存在于 CSV 中，无需执行抓取任务。")
        show_final_summary_popup_from_json(SECTORS_JSON_PATH)
        return True

    # --- CSV 文件初始化 ---
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    file_exists = os.path.exists(OUTPUT_FILE)
    if not file_exists:
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Symbol', 'Expiry Date', 'Type', 'Strike', 'Open Interest', 'Last Price'])
        tqdm.write(f"创建新文件: {OUTPUT_FILE}")
    else:
        tqdm.write(f"文件已存在，将以追加模式运行: {OUTPUT_FILE}")

    # =====================================================
    #  核心改动：用 yfinance + ThreadPoolExecutor 替代 Selenium
    # =====================================================

    csv_lock = threading.Lock()          # CSV 写入线程锁
    json_lock = threading.Lock()         # JSON 更新线程锁

    def process_one_symbol(symbol_data):
        """线程工作函数：抓取 + 校验 + 写入"""
        symbol, market_cap = symbol_data

        # 格式化市值用于日志
        if market_cap >= 1e12:
            cap_str = f"{market_cap / 1e12:.2f}T"
        elif market_cap >= 1e9:
            cap_str = f"{market_cap / 1e9:.2f}B"
        elif market_cap > 0:
            cap_str = f"{market_cap / 1e6:.1f}M"
        else:
            cap_str = "N/A"

        sym, data, status = fetch_single_symbol_options(symbol)

        if status == "ok" and data:
            total_rows = len(data)
            zero_count = sum(1 for row in data if row[4] == 0)
            zero_ratio = zero_count / total_rows if total_rows > 0 else 0

            if zero_ratio > 0.95:
                tqdm.write(f"⚠️ [{sym}] ({cap_str}) 数据无效 (0值率: {zero_ratio:.1%}) -> 跳过写入，更新JSON")
                with json_lock:
                    update_sectors_json(sym, SECTORS_JSON_PATH)
            else:
                with csv_lock:
                    try:
                        with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                            csv.writer(f).writerows(data)
                    except Exception as e:
                        tqdm.write(f"[{sym}] 写入文件失败: {e}")
                tqdm.write(f"✅ [{sym}] ({cap_str}) {total_rows} 条, {len(set(r[1] for r in data))} 个日期")
        elif status == "no_dates":
            tqdm.write(f"⚠️ [{sym}] ({cap_str}) 无期权日期数据")
        else:
            tqdm.write(f"❌ [{sym}] ({cap_str}) 错误: {status[:100]}")

    # ===== 并行执行 =====
    tqdm.write(f"\n🚀 启动并行抓取 (线程数: {MAX_WORKERS}, 共 {len(symbols)} 个 Symbol)...\n")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one_symbol, sd): sd for sd in symbols}

        pbar = tqdm(total=len(futures), desc="总体进度", position=0)
        for future in as_completed(futures):
            try:
                future.result()  # 触发异常抛出（如果有的话）
            except Exception as e:
                sym_data = futures[future]
                tqdm.write(f"❌ [{sym_data[0]}] 线程异常: {e}")
            pbar.update(1)
        pbar.close()

    elapsed = time.time() - start_time
    tqdm.write(f"\n⏱️ 抓取完成，耗时: {elapsed:.1f} 秒 ({elapsed / 60:.1f} 分钟)")
    tqdm.write(f"数据已保存至: {OUTPUT_FILE}")

    # 最终报告
    tqdm.write("正在生成最终报告...")
    show_final_summary_popup_from_json(SECTORS_JSON_PATH)

    return True


if __name__ == "__main__":
    task_success = scrape_options()
    if task_success:
        run_analysis_program()