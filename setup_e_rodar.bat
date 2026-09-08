@echo off
setlocal enabledelayedexpansion
title Video Editor Local - Setup

echo ============================================
echo   Video Editor Local - Instalacao e Execucao
echo ============================================
echo.

REM --- Verifica Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado no PATH.
    echo Instale em https://www.python.org/downloads/
    echo IMPORTANTE: marque a opcao "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)
echo [OK] Python encontrado.

REM --- Verifica ffmpeg ---
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [ERRO] ffmpeg nao foi encontrado no PATH.
    echo Baixe em https://www.gyan.dev/ffmpeg/builds/ ^(release essentials^),
    echo descompacte e adicione a pasta "bin" as variaveis de ambiente PATH do Windows.
    pause
    exit /b 1
)
echo [OK] ffmpeg encontrado.
echo.

cd /d "%~dp0backend"

REM --- Cria ambiente virtual se nao existir ---
if not exist ".venv" (
    echo Criando ambiente virtual Python...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo.
echo Instalando dependencias ^(pode demorar alguns minutos na primeira vez^)...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao instalar dependencias. Veja a mensagem acima.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Tudo pronto! Iniciando o servidor...
echo   Deixe esta janela aberta enquanto usa o editor.
echo   Abra o arquivo frontend\index.html no navegador.
echo ============================================
echo.

uvicorn main:app --reload --port 8000

pause
