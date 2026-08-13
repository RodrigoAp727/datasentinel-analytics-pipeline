@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else (
    set "PYTHON_CMD=python"
)

"%PYTHON_CMD%" -m pip install -e .
"%PYTHON_CMD%" main.py --once --csv-path dados_teste.csv
endlocal
