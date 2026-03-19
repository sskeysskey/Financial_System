tell application "Google Chrome"
	activate
	delay 0.5
end tell

tell application "System Events"
	keystroke "t" using command down
	delay 0.5
	keystroke "polymarket.com/"
	delay 0.5
	key code 36
end tell

set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
set imageName to "polymarket_launch.png"
set clickValue to "false" -- 如果需要执行鼠标点击操作，则为 "true"，否则为 "false"
set Opposite to "false" -- 如果需要是反向截图判断，则为 "true"，否则为 "false"

set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite

do shell script commandString
delay 0.5

set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
set imageName to "polymarket_filter.png"
set clickValue to "true" -- 如果需要执行鼠标点击操作，则为 "true"，否则为 "false"
set Opposite to "false" -- 如果需要是反向截图判断，则为 "true"，否则为 "false"

set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite

do shell script commandString
delay 0.5

set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
set imageName to "polymarket_24hr.png"
set clickValue to "true" -- 如果需要执行鼠标点击操作，则为 "true"，否则为 "false"
set Opposite to "false" -- 如果需要是反向截图判断，则为 "true"，否则为 "false"

set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite

do shell script commandString
delay 0.5

set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
set imageName to "polymarket_total.png"
set clickValue to "true" -- 如果需要执行鼠标点击操作，则为 "true"，否则为 "false"
set Opposite to "false" -- 如果需要是反向截图判断，则为 "true"，否则为 "false"

set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite

do shell script commandString
delay 0.5

do shell script "/opt/homebrew/bin/cliclick m:734,556"

--模拟 鼠标向下滚动
do shell script "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 -c \"
import pyautogui
import time
pyautogui.scroll(-50)
time.sleep(1)
\""

tell application "System Events"
	key code 14 using option down
end tell

set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
set imageName to "polymarket_finish.png"
set clickValue to "false" -- 如果需要执行鼠标点击操作，则为 "true"，否则为 "false"
set Opposite to "false" -- 如果需要是反向截图判断，则为 "true"，否则为 "false"

set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite

do shell script commandString
delay 1.5

tell application "System Events"
	keystroke "t" using command down
	delay 0.5
	keystroke "kalshi.com/browse?order_by=event-volume&status=open"
	delay 0.5
	key code 36
end tell
delay 0.5

set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
set imageName to "kalshi_launch.png"
set clickValue to "false" -- 如果需要执行鼠标点击操作，则为 "true"，否则为 "false"
set Opposite to "false" -- 如果需要是反向截图判断，则为 "true"，否则为 "false"

set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite

do shell script commandString
delay 0.5

tell application "System Events"
	key code 14 using option down
end tell

set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
set imageName to "kalshi_start.png"
set clickValue to "true" -- 如果需要执行鼠标点击操作，则为 "true"，否则为 "false"
set Opposite to "false" -- 如果需要是反向截图判断，则为 "true"，否则为 "false"

set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite

do shell script commandString
delay 0.5

-- ★ 新增：等待标志文件出现的逻辑
set flagFilePath to (path to downloads folder as text) & "kalshi_scraping_done.txt"
set posixFlagFilePath to POSIX path of flagFilePath

-- 确保开始前没有旧的标志文件
try
	do shell script "rm -f " & quoted form of posixFlagFilePath
end try

set isDone to false
-- 循环等待，每 10 秒检查一次，避免过度消耗 CPU
repeat while isDone is false
	try
		-- 如果文件存在，ls 命令会成功，否则会抛出错误
		do shell script "ls " & quoted form of posixFlagFilePath
		set isDone to true
	on error
		delay 10
	end try
end repeat

-- 抓取完成，删除标志文件以便下次运行
try
	do shell script "rm -f " & quoted form of posixFlagFilePath
end try

delay 2 -- 给页面一点时间渲染完成状态

-- ★ 继续执行后续的截图寻找
set pythonScriptPath to "/Users/yanzhang/Coding/python_code/screenshot.py"
set imageName to "kalshi_restart.png"
set clickValue to "false" -- 如果需要执行鼠标点击操作，则为 "true"，否则为 "false"
set Opposite to "false" -- 如果需要是反向截图判断，则为 "true"，否则为 "false"

set commandString to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3 " & quoted form of pythonScriptPath & " " & quoted form of imageName & " " & clickValue & " " & Opposite

do shell script commandString
delay 0.5

set pythonPath to "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
set scriptPath to "/Users/yanzhang/Coding/Financial_System/JavaScript/Prediction/Compare_Trend.py"
set command to pythonPath & space & quoted form of scriptPath

tell application "System Events"
	set isRunning to exists (process "Terminal")
end tell

if isRunning then
	-- 如果 Terminal 正在运行，激活它并新建一个标签页/窗口来执行脚本
	tell application "Terminal"
		activate
		do script command
	end tell
else
	-- 如果 Terminal 没有运行，先激活它（这会启动应用并创建第一个窗口）
	-- 然后，在那个新建的第一个窗口中执行脚本，以避免打开第二个窗口
	tell application "Terminal"
		activate
		do script command in window 1
	end tell
end if