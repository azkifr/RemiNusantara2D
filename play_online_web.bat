@echo off
title Remi Nusantara 2D Online
echo ============================================================
echo   Menjalankan Remi Nusantara 2D Online (Royale Edition)
echo   Alamat: http://localhost:8080
echo ============================================================
echo.

:: Otomatis buka browser ke permainan
start http://localhost:8080

:: Jalankan server Python
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python "%~dp0src\web_game_server.py"
) else (
    if exist "C:\Program Files\Blender Foundation\Blender 3.6\3.6\python\bin\python.exe" (
        "C:\Program Files\Blender Foundation\Blender 3.6\3.6\python\bin\python.exe" "%~dp0src\web_game_server.py"
    ) else (
        echo [ERROR] Python tidak ditemukan di sistem atau Blender 3.6!
        pause
    )
)
