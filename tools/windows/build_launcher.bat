@echo off
cd /d "%~dp0"

python -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --noconsole ^
  --name ScholarArchive ^
  --distpath . ^
  --workpath build\pyinstaller ^
  --specpath build\pyinstaller ^
  launcher.py

if exist ScholarArchive.exe (
  echo.
  echo Build complete: %CD%\ScholarArchive.exe
  echo You can pin this exe to the taskbar.
)

pause
