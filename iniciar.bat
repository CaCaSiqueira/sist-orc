@echo off
cd /d "%~dp0"
title Orcamento Pessoal — rodando (nao feche esta janela)

:: ── Verifica se o ambiente virtual existe ────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo  ERRO: Ambiente virtual nao encontrado.
    echo  Execute instalar.bat primeiro.
    echo.
    pause
    exit /b 1
)

:: ── Ativa o ambiente virtual ─────────────────────────────────────────────────
call venv\Scripts\activate.bat

:: ── Abre o navegador apos 5 segundos (em segundo plano) ──────────────────────
start "" cmd /c "timeout /t 5 /nobreak >nul && start http://localhost:8501"

echo.
echo  ================================================
echo   Orcamento Pessoal iniciando...
echo   Aguarde o navegador abrir automaticamente.
echo.
echo   Acesso manual: http://localhost:8501
echo.
echo   ATENCAO: Nao feche esta janela!
echo   Para encerrar o app, feche esta janela.
echo  ================================================
echo.

:: ── Inicia o Streamlit ────────────────────────────────────────────────────────
streamlit run app.py ^
    --server.headless true ^
    --server.port 8501 ^
    --browser.gatherUsageStats false ^
    --server.enableCORS false
