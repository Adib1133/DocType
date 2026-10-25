@echo off
cd /d "%~dp0"
if exist "dist\DocType\DocType.exe" (
    start "" "dist\DocType\DocType.exe"
    exit /b
)
python app.py
if errorlevel 1 (
    echo Install dependencies with: python -m pip install -r requirements.txt
    pause
)
