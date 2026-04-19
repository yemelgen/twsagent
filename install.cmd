@echo off
chcp 65001 >NUL
cd %~dp0
if not exist %windir%/py.exe (
	echo Python version 3.9 or higher is required to run this App.
	echo Please install Python and try again.
	echo You can download it on https://www.python.org/downloads
	goto :end
)
%windir%/py.exe install.py
:end
pause
