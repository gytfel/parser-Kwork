@echo off
rem Launch the bot on Windows: double-click run.bat or run "run.bat setup" / "run.bat check"
chcp 65001 >nul
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>nul
if errorlevel 1 (
    echo Не найден Python 3.10 или новее.
    echo Скачайте его с https://www.python.org/downloads/ и при установке отметьте "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение .venv...
    %PY% -m venv .venv || (pause & exit /b 1)
)

if not exist ".venv\.installed" (
    echo Устанавливаю зависимости...
    ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || (pause & exit /b 1)
    type nul > ".venv\.installed"
)

".venv\Scripts\python.exe" -m kwork_bot %*
pause
