@echo off
cd /d "%~dp0"

set "APP=%~dp0app.py"
set "LOG=%~dp0启动日志.txt"
echo [%date% %time%] 启动器开始执行 > "%LOG%"
echo 当前目录: %cd% >> "%LOG%"

set "PYW="
set "PY="

rem ===== [1] 已知可用路径（这台电脑实测能跑的） =====
if exist "D:\anaconda3\pythonw.exe" set "PYW=D:\anaconda3\pythonw.exe"
if exist "D:\anaconda3\python.exe"  set "PY=D:\anaconda3\python.exe"

rem ===== [2] Windows 自带的 Python 启动器 =====
if not defined PYW if exist "%SystemRoot%\pyw.exe" set "PYW=%SystemRoot%\pyw.exe"
if not defined PY  if exist "%SystemRoot%\py.exe"  set "PY=%SystemRoot%\py.exe"

rem ===== [3] 几个常见安装位置 =====
if not defined PYW for %%d in ("C:\ProgramData\anaconda3" "C:\anaconda3" "C:\Python313" "C:\Python312" "C:\Python311") do if not defined PYW if exist "%%~d\pythonw.exe" set "PYW=%%~d\pythonw.exe"
if not defined PY  for %%d in ("C:\ProgramData\anaconda3" "C:\anaconda3" "C:\Python313" "C:\Python312" "C:\Python311") do if not defined PY  if exist "%%~d\python.exe"  set "PY=%%~d\python.exe"

rem ===== [4] 兜底：PATH 里的 pythonw / python =====
if not defined PYW for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PY  for /f "delims=" %%i in ('where python 2^>nul')  do if not defined PY  set "PY=%%i"

echo 找到 pythonw = %PYW% >> "%LOG%"
echo 找到 python  = %PY% >> "%LOG%"
echo 目标脚本 = %APP% >> "%LOG%"

if defined PYW if exist "%APP%" (
  start "" "%PYW%" "%APP%"
  echo 结果: 已用 pythonw 启动 >> "%LOG%"
  exit /b
)

if defined PY if exist "%APP%" (
  echo 结果: 没有 pythonw，改用带黑框的 python 启动 >> "%LOG%"
  "%PY%" "%APP%"
  if errorlevel 1 pause
  exit /b
)

echo 结果: 失败 - 没找到可用的 Python，或 app.py 不在这个文件夹 >> "%LOG%"

echo.
echo    ==================================================
echo     启动失败：没找到可用的 Python
echo    ==================================================
echo.
echo    这个工具需要电脑上装过 Python 才能跑。
echo.
echo    请做两件事之一：
echo      1、把这一屏截图发给 AI
echo      2、把这个文件发给 AI：启动日志.txt
echo.
echo    （之前能用的那台电脑，Python 装在 D:\anaconda3）
echo.
pause
exit /b
