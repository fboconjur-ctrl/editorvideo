@echo off
setlocal enabledelayedexpansion
title Video Editor Local - Diagnostico

echo ============================================
echo   Gerando pacote de diagnostico...
echo ============================================
echo.

set "DIAG_DIR=%TEMP%\editorvideo_diagnostico_%RANDOM%"
mkdir "%DIAG_DIR%" 2>nul

echo === Python ===> "%DIAG_DIR%\diagnostico.txt"
python --version >> "%DIAG_DIR%\diagnostico.txt" 2>&1
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === Node.js/npm === >> "%DIAG_DIR%\diagnostico.txt"
node --version >> "%DIAG_DIR%\diagnostico.txt" 2>&1
npm --version >> "%DIAG_DIR%\diagnostico.txt" 2>&1
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === Interface compilada (backend\static) === >> "%DIAG_DIR%\diagnostico.txt"
if exist "%~dp0backend\static\index.html" (
    echo OK: backend\static\index.html existe. >> "%DIAG_DIR%\diagnostico.txt"
) else (
    echo NAO ENCONTRADA: rode setup_e_rodar.bat para compilar a interface. >> "%DIAG_DIR%\diagnostico.txt"
)
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === ffmpeg (PATH global) === >> "%DIAG_DIR%\diagnostico.txt"
where ffmpeg >> "%DIAG_DIR%\diagnostico.txt" 2>&1
ffmpeg -version >> "%DIAG_DIR%\diagnostico.txt" 2>&1
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === ffmpeg tem vidstab? === >> "%DIAG_DIR%\diagnostico.txt"
ffmpeg -filters 2>&1 | findstr /I "vidstab" >> "%DIAG_DIR%\diagnostico.txt"
if errorlevel 1 echo NAO ENCONTRADO >> "%DIAG_DIR%\diagnostico.txt"
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === Pasta tools\ (ffmpeg completo baixado automaticamente) === >> "%DIAG_DIR%\diagnostico.txt"
if exist "%~dp0tools" (
    dir /s /b "%~dp0tools" >> "%DIAG_DIR%\diagnostico.txt" 2>&1
) else (
    echo Pasta tools\ nao existe. >> "%DIAG_DIR%\diagnostico.txt"
)
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === ffmpeg dentro de tools\ (se existir) tem vidstab? === >> "%DIAG_DIR%\diagnostico.txt"
for /d %%D in ("%~dp0tools\ffmpeg-*") do (
    echo Testando %%D\bin\ffmpeg.exe >> "%DIAG_DIR%\diagnostico.txt"
    "%%D\bin\ffmpeg.exe" -filters 2>&1 | findstr /I "vidstab" >> "%DIAG_DIR%\diagnostico.txt"
)
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === Pacotes Python instalados no venv (backend) === >> "%DIAG_DIR%\diagnostico.txt"
if exist "%~dp0backend\.venv\Scripts\python.exe" (
    "%~dp0backend\.venv\Scripts\python.exe" -m pip list >> "%DIAG_DIR%\diagnostico.txt" 2>&1
) else (
    echo Ambiente virtual backend\.venv nao encontrado. >> "%DIAG_DIR%\diagnostico.txt"
)
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === Ultima versao do codigo (git log) === >> "%DIAG_DIR%\diagnostico.txt"
git -C "%~dp0" log -3 --oneline >> "%DIAG_DIR%\diagnostico.txt" 2>&1
echo. >> "%DIAG_DIR%\diagnostico.txt"

set "ZIP_PATH=%USERPROFILE%\Downloads\diagnostico_editor_%RANDOM%.zip"
powershell -NoProfile -Command "try { Compress-Archive -Path '%DIAG_DIR%\*' -DestinationPath '%ZIP_PATH%' -Force -ErrorAction Stop } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo.
    echo [AVISO] Nao foi possivel criar o .zip ^(pode ser antivirus bloqueando,
    echo ou a pasta Downloads sincronizada com OneDrive^). Mas o texto do
    echo diagnostico esta aqui, sem precisar do zip:
    echo.
    echo %DIAG_DIR%\diagnostico.txt
    echo.
    echo Abra esse arquivo .txt direto, copie o conteudo e cole na conversa.
    pause
    exit /b 0
)

echo.
echo ============================================
echo   Pronto! Pacote gerado em:
echo   %ZIP_PATH%
echo.
echo   Abra o zip, copie o conteudo do arquivo
echo   diagnostico.txt e cole na conversa com o Claude.
echo ============================================
pause
