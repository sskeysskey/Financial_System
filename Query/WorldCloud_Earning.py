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
        
#         "赋能人工智能",
#         "黄金",
#         "贵金属",
#         "数据中心",
        
#         "借助人工智能",
#         "房地产投资信托",
        
#     # … 你想排除的 tag 全都写在这里 …
# }

BLACKLIST_TAGS = {
        
}

# 原来的 smoothing 因子
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

def load_sectors(path):
    """
    读取 Sectors_All.json，返回 symbol->sector_name 的映射
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    sym2sector = {}
    for sector, syms in data.items():
        for s in syms:
            sym2sector[s] = sector
    return sym2sector

import os
import sys

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

def main():
    parser = argparse.ArgumentParser(description="根据 Earning 表生成财报涨跌幅标签云")
    parser.add_argument("--db",      default=os.path.join(BASE_CODING_DIR, "Database", "Finance.db"),
                        help="SQLite 数据库文件路径")
    parser.add_argument("--desc",    default=os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json"),
                        help="description.json 路径")
    parser.add_argument("--tagsw",   default=os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "tags_weight.json"),
                        help="tags_weight.json 路径")
    parser.add_argument("--sectors", default=os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json"),
                        help="Sectors_All.json 路径，用来找 sector 对应的因子")
    parser.add_argument("--months",  type=int, default=2,
                        help="向前扫描多少个月（取最近一次财报），默认 2 个月")
    parser.add_argument("--font",    default=None,
                        help="中文标签云字体文件路径，如 SimHei.ttf")
    parser.add_argument("--out-up",   default=os.path.join(USER_HOME, "Downloads", "tagcloud_up_earning.png"),
                        help="输出的“财报涨幅榜”标签云图片文件名")
    parser.add_argument("--out-down", default=os.path.join(USER_HOME, "Downloads", "tagcloud_down_earing.png"),
                        help="输出的“财报跌幅榜”标签云图片文件名")
    args = parser.parse_args()

    # 默认字体
    if args.font is None:
        if sys.platform == 'darwin':
            args.font = os.path.join(USER_HOME, "Library", "Fonts", "FangZhengHeiTiJianTi-1.ttf")
        elif sys.platform == 'win32':
            args.font = "C:\\Windows\\Fonts\\msyh.ttc"
        else:
            args.font = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"

    # 校验文件
    for p in (args.db, args.desc, args.tagsw, args.sectors):
        if not os.path.isfile(p):
            print(f"找不到文件: {p}", file=sys.stderr)
            sys.exit(1)

    # 1) 加载描述和权重、mapping
    symbol_tags = load_description(args.desc)
    tag_weight   = load_tag_weights(args.tagsw)
    sym2sector   = load_sectors(args.sectors)

    # 2) 打开数据库
    conn = sqlite3.connect(args.db)

    # 3) 从 Earning 表中拉取最近 args.months 个月内的所有记录，
    #    按 (name, date DESC) 排序，取每个 symbol 最新一条
    cutoff_dt = (datetime.today() - timedelta(days=30 * args.months)).date().isoformat()
    cur = conn.execute(
        "SELECT name, date, price FROM Earning "
        "WHERE date >= ? "
        "ORDER BY name ASC, date DESC",
        (cutoff_dt,)
    )
    latest_earnings = {}
    for name, date_str, price in cur.fetchall():
        if name not in latest_earnings:
            latest_earnings[name] = float(price)  # 价格即百分比涨跌

    conn.close()

    # 准备两个 defaultdict 来累加 tag 分数
    tag_scores_up   = defaultdict(float)
    tag_scores_down = defaultdict(float)

    # 4) 对每个 symbol 做打分
    for sym, pct in latest_earnings.items():
        # 找 sector
        sector = sym2sector.get(sym)
        if not sector:
            continue
        # 找平滑因子
        factor = TABLE_FACTORS.get(sector, 1.0)
        pct_adj = pct / factor

        # 找这个 symbol 的所有 tags
        tags = symbol_tags.get(sym, [])
        if not tags:
            continue
        for t in tags:
            if t in BLACKLIST_TAGS:
                continue
            w = tag_weight.get(t)
            if w is None:
                continue
            score = w * abs(pct_adj)
            if pct_adj > 0:
                tag_scores_up[t]   += score
            else:
                tag_scores_down[t] += score

    # 5) 画图前的 Matplotlib 配置
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

    gen_and_save(tag_scores_up,   args.out_up,   "财报涨幅榜")
    gen_and_save(tag_scores_down, args.out_down, "财报跌幅榜")


if __name__ == "__main__":
    main()