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

REM --- Verifica Node.js (necessario para compilar a interface) ---
where node >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Node.js nao foi encontrado no PATH.
    echo Instale em https://nodejs.org/ ^(versao LTS^) e abra um novo PowerShell depois.
    pause
    exit /b 1
)
echo [OK] Node.js encontrado.

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

REM --- Verifica se o ffmpeg tem o filtro vidstab (estabilizacao de video) ---
REM Se nao tiver (build "essentials"), baixa automaticamente um build
REM "full" e usa ele so nesta sessao (nao mexe no PATH permanente do Windows).
set "FFMPEG_FULL_BIN="
ffmpeg -filters 2>nul | findstr /I "vidstab" >nul
if errorlevel 1 (
    echo.
    echo O ffmpeg atual nao tem o filtro vidstab ^(necessario so para a opcao
    echo "Estabilizar imagem tremida"^). Baixando automaticamente um build
    echo completo do ffmpeg para uso nesta pasta ^(nao afeta seu PATH global^)...
    set "TOOLS_DIR=%~dp0tools"
    if not exist "!TOOLS_DIR!" mkdir "!TOOLS_DIR!"
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip' -OutFile '!TOOLS_DIR!\ffmpeg-full.zip' -UseBasicParsing } catch { exit 1 }"
    if errorlevel 1 (
        echo [AVISO] Nao foi possivel baixar o ffmpeg completo automaticamente.
        echo A estabilizacao de video vai falhar se voce marcar essa opcao;
        echo as demais funcoes do editor continuam normais.
    ) else (
        powershell -NoProfile -Command "Expand-Archive -Path '!TOOLS_DIR!\ffmpeg-full.zip' -DestinationPath '!TOOLS_DIR!' -Force"
        for /d %%D in ("!TOOLS_DIR!\ffmpeg-*") do set "FFMPEG_FULL_BIN=%%D\bin"
        if defined FFMPEG_FULL_BIN (
            set "PATH=!FFMPEG_FULL_BIN!;%PATH%"
            echo [OK] ffmpeg completo instalado em !TOOLS_DIR! e ativado para esta sessao.
        ) else (
            echo [AVISO] Baixou mas nao encontrou a pasta bin esperada. A estabilizacao pode nao funcionar.
        )
    )
)
echo.

REM --- Compila a interface (React) para dentro de backend/static ---
echo Instalando/compilando a interface ^(primeira vez pode demorar^)...
pushd "%~dp0frontend-app"
call npm install
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias da interface ^(npm install^).
    popd
    pause
    exit /b 1
)
call npm run build
if errorlevel 1 (
    echo [ERRO] Falha ao compilar a interface ^(npm run build^).
    popd
    pause
    exit /b 1
)
popd
echo [OK] Interface compilada.
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
echo   Abrindo http://localhost:8000 no navegador...
echo ============================================
echo.

REM Abre o navegador em segundo plano, com um pequeno atraso, para dar
REM tempo do servidor subir antes da pagina carregar.
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"

uvicorn main:app --reload --port 8000

pause
