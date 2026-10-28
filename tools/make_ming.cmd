@echo off
REM Ming-3.0-TTS 0.5B one-shot (fixed-track fallback default since 2026-10-29, MIT). Usage: make_ming.cmd jobs.json   (see make_ming.py header). ASCII only.
setlocal
set PYTHONUTF8=1
C:\AI\Voice\venv\Scripts\python.exe C:\AI\tools\make_ming.py %1
endlocal
