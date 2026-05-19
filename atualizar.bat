@echo off
cd /d "%~dp0"
title Atualizando Orcamento Pessoal...

echo.
echo  ================================================
echo   Atualizador - Orcamento Pessoal
echo  ================================================
echo.

set REPO_ZIP=https://github.com/CaCaSiqueira/sist-orc/archive/refs/heads/main.zip
set TEMP_ZIP=%TEMP%\sist-orc-update.zip
set TEMP_DIR=%TEMP%\sist-orc-extract

:: ── Baixa a versao mais recente ───────────────────────────────────────────────
echo [1/3] Baixando atualizacao...
curl -L -o "%TEMP_ZIP%" "%REPO_ZIP%"
if %errorlevel% neq 0 (
    echo.
    echo  ERRO: Nao foi possivel baixar. Verifique sua conexao.
    pause
    exit /b 1
)
echo     OK

:: ── Extrai e atualiza arquivos (preserva .streamlit com suas credenciais) ─────
echo [2/3] Aplicando atualizacao...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
powershell -Command "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_DIR%' -Force"
robocopy "%TEMP_DIR%\sist-orc-main" "%~dp0" /E /XD ".streamlit" "venv" /NFL /NDL /NJH /NJS >nul
del "%TEMP_ZIP%"
rmdir /s /q "%TEMP_DIR%" 2>nul
echo     OK

:: ── Atualiza dependencias ─────────────────────────────────────────────────────
echo [3/3] Atualizando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check
echo     OK

echo.
echo  ================================================
echo   Atualizacao concluida!
echo   Execute "iniciar.bat" ou clique no atalho.
echo  ================================================
echo.
pause
