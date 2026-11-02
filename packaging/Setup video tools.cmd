@echo off
setlocal
if not exist "%~dp0Archiver.exe" (
  echo Keep this setup file beside Archiver.exe, then run it again.
  pause
  exit /b 1
)
"%~dp0Archiver.exe" --setup-tools "%~dp0."
set "setupResult=%ERRORLEVEL%"
echo.
pause
exit /b %setupResult%
