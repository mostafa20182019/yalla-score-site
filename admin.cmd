@echo off
rem Yalla Score admin launcher: serves this folder on localhost so the
rem YouTube preview works (file:// has no Referer -> YouTube Error 153).
cd /d "%~dp0"
start "" "http://localhost:8123/admin-videos.html"
start "" "http://localhost:8123/admin-articles.html"
echo Admin pages opened in the browser. Keep this window open while working.
echo (Close it when you finish - it is the local server.)
python -m http.server 8123 >nul 2>&1
if errorlevel 1 (
  echo Server already running on port 8123 - pages will use it.
  timeout /t 4 >nul
)
