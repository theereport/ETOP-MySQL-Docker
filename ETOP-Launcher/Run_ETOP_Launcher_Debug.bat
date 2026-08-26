@echo off
setlocal
title ETOP Launcher Debug

cd /d "%~dp0"

echo ==========================================
echo ETOP Launcher Debug
echo ==========================================
echo Folder: %CD%
echo.

echo Checking launcher file...
if not exist "ETOP_Launcher.pyw" (
    echo ERROR: ETOP_Launcher.pyw was not found in:
    echo %CD%
    echo.
    pause
    exit /b 1
)

echo Checking Python...
where python.exe
echo.

set "PYTHON_EXE=C:\Users\Josh.Corbit\AppData\Local\Programs\Python\Python313\python.exe"

if exist "%PYTHON_EXE%" (
    echo Using:
    echo %PYTHON_EXE%
    echo.
    "%PYTHON_EXE%" "ETOP_Launcher.pyw"
    echo.
    echo Launcher exited with code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

where python.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    echo Using python.exe from PATH.
    echo.
    python.exe "ETOP_Launcher.pyw"
    echo.
    echo Launcher exited with code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

echo ERROR: Python could not be found.
pause
exit /b 1
