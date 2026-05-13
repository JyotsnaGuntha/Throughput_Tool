@echo off
setlocal

cd /d "%~dp0"

set "VENV_DIR=%~dp0venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "BOOTSTRAP_FLAG=%VENV_DIR%\Scripts\.deps_installed"

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python was not found on this machine.
        pause
        exit /b 1
    )
    set "PY_LAUNCHER=py -3"
) else (
    set "PY_LAUNCHER=python"
)

if not exist "%PYTHON_EXE%" (
    %PY_LAUNCHER% -m venv "%VENV_DIR%"
)

if not exist "%BOOTSTRAP_FLAG%" (
    "%PYTHON_EXE%" -m pip install --upgrade pip
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
    type nul > "%BOOTSTRAP_FLAG%"
)

"%PYTHON_EXE%" "%~dp0Tool_V1.1.py"
set "EXIT_CODE=%errorlevel%"

if not "%EXIT_CODE%"=="0" (
    echo Application exited with code %EXIT_CODE%.
)

pause
exit /b %EXIT_CODE%