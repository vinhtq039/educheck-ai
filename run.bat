@echo off
setlocal
cd /d "%~dp0"

title EduCheck AI

if not exist ".venv\Scripts\python.exe" (
    echo [EduCheck AI] Dang tao moi truong Python...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Khong the tao moi truong Python. Hay cai Python 3.12 tro len.
        pause
        exit /b 1
    )

    echo [EduCheck AI] Dang cai thu vien. Buoc nay chi chay mot lan...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Khong the cai thu vien. Hay kiem tra ket noi Internet.
        pause
        exit /b 1
    )
)

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
)

findstr /B /C:"OPENAI_API_KEY=" ".env" | findstr /V /R /C:"OPENAI_API_KEY=$" >nul
if errorlevel 1 (
    echo.
    echo [EduCheck AI] Vui long dien OPENAI_API_KEY vao file .env.
    echo Luu file va dong Notepad de tiep tuc.
    start /wait notepad.exe ".env"
)

echo.
echo [EduCheck AI] Dang khoi dong...
echo Trinh duyet se mo tai http://localhost:8501
echo Nhan Ctrl+C trong cua so nay de dung ung dung.
echo.

set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"
".venv\Scripts\python.exe" -m streamlit run app.py --browser.gatherUsageStats=false

if errorlevel 1 (
    echo.
    echo Ung dung da dung do co loi.
    pause
)
