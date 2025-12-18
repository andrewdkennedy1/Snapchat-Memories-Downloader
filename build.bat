@echo off
setlocal enabledelayedexpansion

REM Build a single-file, windowed (no console) executable with PyInstaller.

pushd "%~dp0"

set "PYTHON="
if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"
if not defined PYTHON (
  for /f "delims=" %%I in ('where python 2^>nul') do (
    set "PYTHON=%%I"
    goto :found_python
  )
)
if not defined PYTHON (
  for /f "delims=" %%I in ('where py 2^>nul') do (
    set "PYTHON=%%I -3"
    goto :found_python
  )
)

:found_python
if not defined PYTHON (
  echo ERROR: Python not found.
  echo - Install Python 3 and ensure "python.exe" is on PATH, or create a venv in ".\venv".
  echo - Then re-run: build.bat
  popd
  exit /b 1
)

echo Installing dependencies...
%PYTHON% -m pip install -r requirements.txt

echo Building executable...
%PYTHON% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  "SnapchatMemoriesDownloader.spec"

set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
