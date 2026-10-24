@echo off
call "%~dp0start_comfy.cmd" >nul
"C:\AI\H3\venv\Scripts\python.exe" -X utf8 "%~dp0face_refine.py" %*
