import sqlite3

db_path = '/Users/yanzhang/Documents/Database/Finance.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
INSERT INTO Currencies (date, name, price)
SELECT
  d.date,
  'CNYI',
  d.price / u.price
FROM Currencies d
JOIN Currencies u
  ON d.date = u.date
WHERE d.name = 'DXY'
  AND u.name = 'USDCNY';
""")

conn.commit()
conn.close()