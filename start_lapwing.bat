@echo off
chcp 65001 >nul
echo ==========================================
echo Starting Lapwing + Open-LLM-VTuber
echo ==========================================
echo.

:: Set Anaconda path
set CONDA_PATH=C:\Users\asus\anaconda3
set PATH=%CONDA_PATH%;%CONDA_PATH%\Scripts;%CONDA_PATH%\condabin;%PATH%

:: Start Lapwing Backend
echo [1/2] Starting Lapwing backend on port 8000...
start "Lapwing Backend" cmd /k "cd /d D:\Github\Lapwing-Project && call %CONDA_PATH%\Scripts\activate.bat base && python -m uvicorn api:app --reload --port 8000"

:: Wait for Lapwing to start
echo Waiting for Lapwing to initialize...
timeout /t 8 /nobreak >nul

:: Start Open-LLM-VTuber Frontend
echo [2/2] Starting Open-LLM-VTuber frontend on port 12393...
start "Open-LLM-VTuber Frontend" cmd /k "cd /d D:\Github\Lapwing-Project\open-llm-vtuber && call %CONDA_PATH%\Scripts\activate.bat base && uv run run_server.py"

echo.
echo ==========================================
echo Both services started!
echo.
echo - Lapwing API: http://localhost:8000
echo - Open-LLM-VTuber: http://localhost:12393
echo ==========================================
echo.
echo Waiting 15 seconds before opening browser...
timeout /t 15 /nobreak >nul

:: Open browser
echo Opening browser...
start http://localhost:12393
