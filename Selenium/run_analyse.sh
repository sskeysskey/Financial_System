#!/bin/bash
# 文件：~/Coding/Financial_System/run_analyse.sh
PY=/Library/Frameworks/Python.framework/Versions/Current/bin/python3
BASE=/Users/yanzhang/Coding/Financial_System

"$PY" "$BASE/Query/Analyse_Short.py" --live || exit 1
"$PY" "$BASE/Query/Analyse_Earning_Season.py" --live || exit 1
"$PY" "$BASE/Query/Analyse_Earning_no_Season.py" --live || exit 1
"$PY" "$BASE/Query/Analyse_Earning_Volume.py" --live || exit 1
"$PY" "$BASE/Query/Analyse_Earning_Support.py" --live || exit 1
"$PY" "$BASE/Query/Analyse_ETF_Volume.py" --live || exit 1
"$PY" "$BASE/Operations/Imigrate_new_exist.py" || exit 1