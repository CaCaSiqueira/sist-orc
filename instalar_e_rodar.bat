@echo off
echo ============================================
echo   Orcamento Pessoal - Instalacao e Inicio
echo ============================================

:: Verifica se Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERRO: Python nao encontrado!
    echo.
    echo Por favor instale o Python em:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: marque a opcao "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo Python encontrado. Instalando dependencias...
python -m pip install -r requirements.txt

echo.
echo Iniciando o app...
echo Acesse no navegador: http://localhost:8501
echo.
python -m streamlit run app.py
pause
