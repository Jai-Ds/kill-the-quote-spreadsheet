@echo off
cd /d "%~dp0"
set PY=%USERPROFILE%\.venvs\aerchain311\python.exe
if not exist "%PY%" (
  echo Python environment not found at %PY%
  echo Create it with Python 3.11, then run: pip install -r requirements.txt
  pause
  exit /b 1
)
start "" /b cmd /c "ping -n 7 127.0.0.1 >nul & start http://localhost:8501"
"%PY%" -m streamlit run app.py --server.headless true
pause
