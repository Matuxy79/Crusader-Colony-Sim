@echo off
setlocal
cd /d "%~dp0"

if exist "dist\CrusaderSpriteEngine.exe" (
    if "%~1"=="" (
        start "" "dist\CrusaderSpriteEngine.exe"
    ) else (
        "dist\CrusaderSpriteEngine.exe" %*
    )
    exit /b 0
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" sprite_engine_v2.py %*
) else (
    py -3 sprite_engine_v2.py %*
)

if errorlevel 1 (
    echo.
    echo Launch failed. Install dependencies with: py -3 -m pip install -r requirements.txt
    pause
)