from datetime import datetime, timedelta
import sqlite3

def compare_today_yesterday(cursor, table_name, name, today):
    yesterday = today - timedelta(days=1)
    day_of_week = yesterday.weekday()

    if day_of_week == 0:  # 昨天是周一
        ex_yesterday = yesterday - timedelta(days=3)  # 取上周五
    elif day_of_week == 5:  # 昨天是周六
        yesterday = yesterday - timedelta(days=1)  # 取周五
        ex_yesterday = yesterday - timedelta(days=1)
    elif day_of_week == 6:  # 昨天是周日
        yesterday = yesterday - timedelta(days=2)  # 取周五
        ex_yesterday = yesterday - timedelta(days=1)
    else:
        ex_yesterday = yesterday - timedelta(days=1)

    query = f"""
    SELECT date, price FROM {table_name} 
    WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
    """
    cursor.execute(query, (name, yesterday.strftime("%Y-%m-%d"), ex_yesterday.strftime("%Y-%m-%d")))
    results = cursor.fetchall()

    if len(results) == 2:
        yesterday_price = results[0][1]
        ex_yesterday_price = results[1][1]
        change = yesterday_price - ex_yesterday_price
        percentage_change = (change / ex_yesterday_price) * 100
        return f"{percentage_change:+.2f}%"

    return "N/A"