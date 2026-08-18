@echo off
chcp 65001 >nul
setlocal
title Atualizar e Publicar - Analise xG / xGA
cd /d "%~dp0"

echo.
echo  ==================================================
echo    ATUALIZAR DADOS E PUBLICAR NO GITHUB
echo  ==================================================
echo.
echo  Use isso em qualquer rede normal (casa, hotel, wifi
echo  de aeroporto, hotspot do celular) para atualizar o
echo  site publicado enquanto estiver fora de casa.
echo.

rem --- Localiza o Python -------------------------------------------------
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY py --version >nul 2>&1 && set "PY=py"
if not defined PY (
    echo  [ERRO] Python nao foi encontrado no sistema.
    echo.
    echo  Instale em https://python.org/downloads e marque a opcao
    echo  "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

rem --- Confere as dependencias --------------------------------------------
%PY% -c "import soccerdata" >nul 2>&1
if errorlevel 1 (
    echo  Dependencias nao encontradas. Instalando...
    echo.
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  [ERRO] Falha ao instalar as dependencias.
        pause
        exit /b 1
    )
)

%PY% scripts\atualizar_e_publicar.py

echo.
echo  ==================================================
pause
endlocal
