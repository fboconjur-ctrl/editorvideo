@echo off
setlocal enabledelayedexpansion
title Video Editor Local - Diagnostico

echo ============================================
echo   Gerando pacote de diagnostico...
echo ============================================
echo.

set "DIAG_DIR=%TEMP%\editorvideo_diagnostico"
if exist "%DIAG_DIR%" rmdir /s /q "%DIAG_DIR%"
mkdir "%DIAG_DIR%"

echo === Python ===> "%DIAG_DIR%\diagnostico.txt"
python --version >> "%DIAG_DIR%\diagnostico.txt" 2>&1
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === ffmpeg (PATH global) === >> "%DIAG_DIR%\diagnostico.txt"
where ffmpeg >> "%DIAG_DIR%\diagnostico.txt" 2>&1
ffmpeg -version >> "%DIAG_DIR%\diagnostico.txt" 2>&1
echo. >> "%DIAG_DIR%\diagnostico.txt"

echo === ffmpeg tem vidstab? === >> "%DIAG_DIR%\diagnostico.txt"
ffmpeg -filters 2>>"%DIAG_DIR%\diagnostico.txt" | findstr /I "vidstab" >> "%DIAG_DIR%\diagnostico.txt"
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
    "%%D\bin\ffmpeg.exe" -filters 2>>"%DIAG_DIR%\diagnostico.txt" | findstr /I "vidstab" >> "%DIAG_DIR%\diagnostico.txt"
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

set "ZIP_PATH=%USERPROFILE%\Downloads\diagnostico_editor.zip"
powershell -NoProfile -Command "Compress-Archive -Path '%DIAG_DIR%\*' -DestinationPath '%ZIP_PATH%' -Force"

echo.
echo ============================================
echo   Pronto! Pacote gerado em:
echo   %ZIP_PATH%
echo.
echo   Abra o zip, copie o conteudo do arquivo
echo   diagnostico.txt e cole na conversa com o Claude.
echo ============================================
pause
