from datetime import datetime, timedelta
from collections import defaultdict
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import os
import sys
import sqlite3
import json
import argparse

# —— 黑名单标签，凡是这些标签都不会计入得分
# BLACKLIST_TAGS = {
#         "云计算",
#         "房地产",
#         "天然气",
#         "赋能人工智能",
#         "黄金",
#         "贵金属",
#         "数据中心",
#         "电力",
#         "借助人工智能",
#         "房地产投资信托",
        
#     # … 你想排除的 tag 全都写在这里 …
# }
BLACKLIST_TAGS = {
        
        
    # … 你想排除的 tag 全都写在这里 …
}

# 白名单：只扫描这些表
WANTED_TABLES = [
    'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
    'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
    'Communication_Services', 'Financial_Services', 'Healthcare'
]

# 新增：给每个表一个“因子”，数字越大，意味着该表里 symbol 数量越多，
# 对应的 pct 要除以更大的数来“平滑”它的影响。
TABLE_FACTORS = {
    'Basic_Materials': 1,
    'Consumer_Cyclical': 2,
    'Real_Estate': 1,
    'Energy': 1,
    'Technology': 3,
    'Utilities': 1,
    'Industrials': 2.5,
    'Consumer_Defensive': 1,
    'Communication_Services': 1,
    'Financial_Services': 3,
    'Healthcare': 2,
}


def load_description(path):
    with open(path, 'r', encoding='utf-8') as f:
        desc = json.load(f)
    symbol_tags = {}
    # stocks
    for item in desc.get('stocks', []):
        symbol_tags[item['symbol']] = item.get('tag', [])
    # etfs
    for item in desc.get('etfs', []):
        symbol_tags[item['symbol']] = item.get('tag', [])
    return symbol_tags


def load_tag_weights(path):
    with open(path, 'r', encoding='utf-8') as f:
        tw = json.load(f)
    tag_weight = {}
    for w_str, tags in tw.items():
        w = float(w_str)
        for t in tags:
            tag_weight[t] = w
    return tag_weight


def get_tables(conn):
    """返回所有用户表名"""
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row[0] for row in cur.fetchall()]


def compute_pct_change(conn, table, symbol, days):
    """
    计算 symbol 在 table 中最近 days 天的收盘价百分比变化
    返回 float 或 None
    """
    cur = conn.cursor()
    # 1) 找最新交易日
    cur.execute(f"SELECT MAX(date) FROM {table} WHERE name=?", (symbol,))
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    latest_date = row[0]  # e.g. '2025-08-09'
    latest_dt = datetime.strptime(latest_date, '%Y-%m-%d').date()

    # 2) 目标对比日
    target_dt = latest_dt - timedelta(days=days)
    target_str = target_dt.isoformat()

    # 3) 查目标日或之前最近一天的收盘价
    cur.execute(
        f"""SELECT price FROM {table}
            WHERE name=? AND date<=?
            ORDER BY date DESC
            LIMIT 1""",
        (symbol, target_str)
    )
    row2 = cur.fetchone()
    if not row2:
        return None
    past_price = row2[0]

    # 4) 最新收盘价
    cur.execute(
        f"SELECT price FROM {table} WHERE name=? AND date=?",
        (symbol, latest_date)
    )
    row3 = cur.fetchone()
    if not row3 or past_price == 0:
        return None
    latest_price = row3[0]

    return (latest_price - past_price) / past_price


def main():
    parser = argparse.ArgumentParser(description="生成最近 N 天股价变动标签云")
    parser.add_argument("--db", default="/Users/yanzhang/Coding/Database/Finance.db",
                        help="SQLite 数据库文件路径")
    parser.add_argument("--desc", default="/Users/yanzhang/Coding/Financial_System/Modules/description.json",
                        help="description.json 路径")
    parser.add_argument("--tagsw", default="/Users/yanzhang/Coding/Financial_System/Modules/tags_weight.json",
                        help="tags_weight.json 路径")
    parser.add_argument("--days", type=int, default=30,
                        help="向前对比的天数 (默认 7 天)")
    parser.add_argument("--font", default=None,
                        help="生成中文标签云时指定的字体路径 (如 SimHei.ttf)")
    parser.add_argument("--out-up",   default="/Users/yanzhang/Downloads/tagcloud_up.png",
                        help="输出的“涨幅榜”标签云图片文件名")
    parser.add_argument("--out-down", default="/Users/yanzhang/Downloads/tagcloud_down.png",
                        help="输出的“跌幅榜”标签云图片文件名")
    args = parser.parse_args()

    # —— 新增：如果用户没指定，就用系统里 macOS 的黑体
    if args.font is None:
        args.font = "/Users/yanzhang/Library/Fonts/FangZhengHeiTiJianTi-1.ttf"  # Windows 下改成 "C:\\Windows\\Fonts\\msyh.ttc"

    if not os.path.isfile(args.db):
        print("找不到数据库文件:", args.db, file=sys.stderr)
        sys.exit(1)

    # 1) 加载描述和权重
    symbol_tags = load_description(args.desc)
    tag_weight  = load_tag_weights(args.tagsw)

    # 2) 打开数据库
    conn = sqlite3.connect(args.db)

    # 分别存涨幅榜和跌幅榜
    tag_scores_up   = defaultdict(float)
    tag_scores_down = defaultdict(float)

    tables = [t for t in get_tables(conn) if t in WANTED_TABLES]
    for table in tables:
        factor = TABLE_FACTORS.get(table, 1.0)
        cur = conn.execute(f"SELECT DISTINCT name FROM {table}")
        for (symbol,) in cur.fetchall():
            pct = compute_pct_change(conn, table, symbol, args.days)
            if pct is None or pct == 0:
                continue

            # —— 核心改动：先按表因子归一化 pct
            pct_adj = pct / factor

            for t in symbol_tags.get(symbol, []):
                # 跳过黑名单
                if t in BLACKLIST_TAGS:
                    continue
                w = tag_weight.get(t)
                if w is None:
                    continue
                score = w * abs(pct_adj)
                if pct_adj > 0:
                    tag_scores_up[t] += score
                else:
                    tag_scores_down[t] += score

    conn.close()

    # 设置 Matplotlib 显示中文
    plt.rcParams['font.sans-serif'] = [os.path.basename(args.font)]
    plt.rcParams['axes.unicode_minus'] = False

    def gen_and_save(freq_dict, out_path, title):
        if not freq_dict:
            print(f"警告：没有 {title} 数据，跳过生成。", file=sys.stderr)
            return
        wc = WordCloud(
            width=800, height=600,
            background_color="white",
            font_path=args.font,
            relative_scaling=0.5
        ).generate_from_frequencies(freq_dict)
        plt.figure(figsize=(10, 8))
        plt.imshow(wc, interpolation="bilinear")
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(out_path, dpi=300)
        print(f"已生成“{title}”标签云并保存为 {out_path}")

    # 生成涨幅榜 / 跌幅榜
    gen_and_save(tag_scores_up,   args.out_up,   "涨幅榜")
    gen_and_save(tag_scores_down, args.out_down, "跌幅榜")


if __name__ == "__main__":
    main()