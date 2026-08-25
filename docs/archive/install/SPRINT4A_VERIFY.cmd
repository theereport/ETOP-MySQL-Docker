@echo off
cd /d "%~dp0"
echo.
echo Checking frontend build...
call npm.cmd run build
if errorlevel 1 goto :failed

echo.
echo Frontend build passed.
echo Start the backend and verify:
echo http://127.0.0.1:8000/api/v1/platform/health
echo.
pause
exit /b 0

:failed
echo.
echo Sprint 4A build failed. Review the error above.
pause
exit /b 1
