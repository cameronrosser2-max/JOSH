@echo off
echo.
echo  ================================================
echo    JOSH Instagram Bot — First Time Setup
echo  ================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Please download it from https://python.org/downloads
    echo  Make sure to check "Add Python to PATH" during install.
    pause
    exit /b
)

echo  Installing packages...
pip install -r requirements.txt --quiet

echo.
echo  Setup complete! Double-click RUN.bat to start the bot.
echo.
pause
