@echo off
rem Runs the news digest from any folder. Uses "python", or the "py" launcher if python isn't on PATH.
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0digest.py" %*
) else (
  py -3 "%~dp0digest.py" %*
)
