@echo off
echo Testando se consigo escrever um arquivo simples...
echo teste > "%TEMP%\teste_editor.txt"
if errorlevel 1 (
    echo FALHOU ao escrever em %TEMP%
) else (
    echo OK: escrevi em %TEMP%\teste_editor.txt
)

echo.
echo Testando escrita na pasta atual...
echo teste > "%~dp0teste_local.txt"
if errorlevel 1 (
    echo FALHOU ao escrever na pasta do projeto
) else (
    echo OK: escrevi em %~dp0teste_local.txt
)

echo.
echo Testando escrita na pasta Downloads...
echo teste > "%USERPROFILE%\Downloads\teste_downloads.txt"
if errorlevel 1 (
    echo FALHOU ao escrever em Downloads
) else (
    echo OK: escrevi em %USERPROFILE%\Downloads\teste_downloads.txt
)

echo.
pause
