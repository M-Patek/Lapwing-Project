@echo off
chcp 65001
echo ==========================================
echo Starting Lapwing + Live2DViewerEX
echo ==========================================
echo.

set CONDA_PATH=C:\Users\asus\anaconda3

:: Start Lapwing
echo [1/3] Starting Lapwing...
start "Lapwing" cmd /k "cd /d D:\Github\Lapwing-Project && call %CONDA_PATH%\Scripts\activate.bat base && uvicorn api:app --port 8000"

timeout /t 5 /nobreak >nul

:: Start Live2DViewerEX with LapwingAI model from workshop
echo [2/3] Starting Live2DViewerEX with LapwingAI...
cd /d "D:\Steam\steamapps\common\Live2DViewerEX"
start "" "launcher.exe" "D:\Steam\steamapps\workshop\content\616720\LapwingAI\hiyori\Hiyori.model3.json"

timeout /t 10 /nobreak >nul

:: Start Live2D Sync
echo [3/3] Starting emotion sync...
start "Live2D Sync" cmd /k "cd /d D:\Github\Lapwing-Project && call %CONDA_PATH%\Scripts\activate.bat base && python live2d_sync.py"

echo.
echo ==========================================
echo Started!
echo.
echo - Lapwing API: http://localhost:8000
echo - Live2DViewerEX API: http://localhost:50750
echo - Model: Hiyori (from Steam Workshop)
echo.
echo Make sure to enable HTTP API in Live2DViewerEX settings!
echo ==========================================
pause
