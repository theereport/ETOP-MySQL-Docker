@echo off
setlocal
cd /d "%~dp0"

set "PYTHONW_EXE=C:\Users\Josh.Corbit\AppData\Local\Programs\Python\Python313\pythonw.exe"
set "PYTHON_EXE=C:\Users\Josh.Corbit\AppData\Local\Programs\Python\Python313\python.exe"

if not exist "ETOP_Launcher.pyw" (
    echo ETOP_Launcher.pyw was not found in %CD%
    pause
    exit /b 1
)

if exist "%PYTHONW_EXE%" (
    "%PYTHONW_EXE%" "ETOP_Launcher.pyw"
    exit /b 0
)

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" "ETOP_Launcher.pyw"
    exit /b 0
)

where pythonw.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    pythonw.exe "ETOP_Launcher.pyw"
    exit /b 0
)

where python.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    python.exe "ETOP_Launcher.pyw"
    exit /b 0
)

echo Python could not be found.
pause
