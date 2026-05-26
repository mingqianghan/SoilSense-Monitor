@echo off
REM ── SoilSense Monitor — Windows build script ──────────────────────────
REM Produces dist\SoilSenseMonitor\ containing SoilSenseMonitor.exe and
REM everything needed to run it. Distribute the entire folder.

setlocal

REM ── Pick a Python interpreter ─────────────────────────────────────────
REM Order: (1) PYTHON env-var override   (2) author's Anaconda install
REM        (3) any 'python' on PATH      (4) 'py' launcher
if defined PYTHON goto :have_python
set PYTHON=D:\Software\Anaconda\python.exe
if exist "%PYTHON%" goto :have_python
for /f "delims=" %%i in ('where python 2^>nul') do set "PYTHON=%%i" & goto :have_python
for /f "delims=" %%i in ('where py 2^>nul')     do set "PYTHON=%%i" & goto :have_python

echo ERROR: No Python interpreter found.
echo Install Python 3.10+ and ensure 'python' is on PATH, or set the
echo PYTHON environment variable to your interpreter's full path.
exit /b 1

:have_python
echo Using Python: %PYTHON%

echo.
echo === Cleaning old build artifacts ===
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo.
echo === Installing / upgrading PyInstaller ===
"%PYTHON%" -m pip install --upgrade pyinstaller

echo.
echo === Building SoilSense Monitor ===
"%PYTHON%" -m PyInstaller SoilSense.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See the error output above.
    exit /b 1
)

echo.
echo === Build complete ===
echo Output: dist\SoilSenseMonitor\SoilSenseMonitor.exe
echo To distribute, zip the entire dist\SoilSenseMonitor\ folder.
echo.

endlocal
