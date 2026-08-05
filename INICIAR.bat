@echo off
setlocal
title Analise xG / xGA - Brasileirao
cd /d "%~dp0"

echo.
echo  ==================================================
echo    ANALISE xG / xGA  -  Plataforma TCC
echo  ==================================================
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

rem --- Confere o Streamlit -----------------------------------------------
%PY% -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo  Streamlit nao encontrado. Instalando dependencias...
    echo.
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  [ERRO] Falha ao instalar as dependencias.
        pause
        exit /b 1
    )
)

rem --- Escolhe uma porta livre -------------------------------------------
set "PORTA=8501"
for %%P in (8501 8502 8503 8504 8505) do (
    if not defined ACHOU (
        netstat -ano 2>nul | findstr /r /c:":%%P .*LISTENING" >nul || (
            set "PORTA=%%P"
            set "ACHOU=1"
        )
    )
)

echo  Iniciando na porta %PORTA%...
echo.
echo  Endereco:  http://localhost:%PORTA%
echo.
echo  O navegador abre sozinho em alguns segundos.
echo  PARA ENCERRAR: feche esta janela.
echo.
echo  ==================================================
echo.

rem --- Abre o navegador quando o servidor estiver de pe ------------------
start "" /min cmd /c "timeout /t 7 /nobreak >nul & start "" http://localhost:%PORTA%"

%PY% -m streamlit run app.py --server.port %PORTA%

echo.
echo  ==================================================
echo    Aplicativo encerrado.
echo  ==================================================
pause
endlocal
