@echo off
cd /d "%~dp0"

echo Scrubbing latest POS files...
pushd "..\Distributor POS"
python pos_scrubber.py --folder .
if %errorlevel% neq 0 (
    echo.
    echo Scrubber failed. Check the POS files in "Distributor POS".
    popd
    pause
    exit /b 1
)
popd

echo.
echo Updating tracker...
python tracker.py
if %errorlevel% neq 0 (
    echo.
    echo Something went wrong. Make sure Python is installed.
    pause
) else (
    start partner_tracker.html
)
