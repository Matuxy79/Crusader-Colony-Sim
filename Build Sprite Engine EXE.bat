@echo off
setlocal
cd /d "%~dp0"

py -3 -m pip install -r requirements-build.txt
if errorlevel 1 goto :failed

py -3 tools\build_sprite_engine.py
if errorlevel 1 goto :failed

echo.
echo Built dist\CrusaderSpriteEngine.exe
echo Double-click Launch Sprite Engine.bat or the EXE to run it.
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error above.
pause
exit /b 1