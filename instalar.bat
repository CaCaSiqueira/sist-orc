@echo off
setlocal enabledelayedexpansion
title Instalador - Orcamento Pessoal

echo.
echo  ================================================
echo   Instalador - Orcamento Pessoal
echo  ================================================
echo.

set INSTALL_DIR=%USERPROFILE%\Documents\OrcamentoPessoal
set REPO_ZIP=https://github.com/CaCaSiqueira/sist-orc/archive/refs/heads/main.zip
set TEMP_ZIP=%TEMP%\sist-orc-install.zip
set TEMP_DIR=%TEMP%\sist-orc-extract

:: ── 1. Verifica Python ────────────────────────────────────────────────────────
echo [1/5] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo     Python nao encontrado. Baixando Python 3.11...
    curl -L -o "%TEMP%\python_installer.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    if %errorlevel% neq 0 (
        echo     ERRO ao baixar Python. Verifique sua conexao.
        pause & exit /b 1
    )
    echo     Instalando Python (aguarde)...
    "%TEMP%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
    del "%TEMP%\python_installer.exe"
    echo     Python instalado!
    echo.
    echo     ATENCAO: Feche e reabra este instalador para continuar.
    pause & exit /b
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo     %%i encontrado — OK

:: ── 2. Baixa o aplicativo ─────────────────────────────────────────────────────
echo [2/5] Baixando aplicativo...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
curl -L -o "%TEMP_ZIP%" "%REPO_ZIP%"
if %errorlevel% neq 0 (
    echo     ERRO: Nao foi possivel baixar. Verifique sua conexao.
    pause & exit /b 1
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
powershell -Command "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_DIR%' -Force"
:: Copia arquivos mas PRESERVA a pasta .streamlit (credenciais) se ja existir
robocopy "%TEMP_DIR%\sist-orc-main" "%INSTALL_DIR%" /E /XD ".streamlit" "venv" /NFL /NDL /NJH /NJS >nul
del "%TEMP_ZIP%"
rmdir /s /q "%TEMP_DIR%" 2>nul
echo     OK — instalado em %INSTALL_DIR%

:: ── 3. Ambiente virtual Python ────────────────────────────────────────────────
echo [3/5] Configurando ambiente Python (pode demorar na 1a vez)...
cd /d "%INSTALL_DIR%"
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo     ERRO ao instalar dependencias.
    pause & exit /b 1
)
echo     OK

:: ── 4. Configura credenciais ──────────────────────────────────────────────────
echo [4/5] Configurando credenciais...
if not exist "%INSTALL_DIR%\.streamlit\secrets.toml" (
    mkdir "%INSTALL_DIR%\.streamlit" 2>nul
    (
        echo # ─────────────────────────────────────────────────────────
        echo # PREENCHA COM SUAS CREDENCIAIS E SALVE O ARQUIVO ^(Ctrl+S^)
        echo # Depois feche o Notepad para continuar a instalacao.
        echo # ─────────────────────────────────────────────────────────
        echo.
        echo # Banco de dados ^(cole a URL do Supabase^)
        echo DATABASE_URL = "COLE_AQUI_A_URL_DO_SUPABASE"
        echo.
        echo # E-mail do administrador do sistema
        echo admin_email = "SEU_EMAIL@EXEMPLO.COM"
        echo.
        echo # Login de acesso ^(remova apos criar conta no banco^)
        echo [users]
        echo "SEU_EMAIL@EXEMPLO.COM" = "SUA_SENHA"
    ) > "%INSTALL_DIR%\.streamlit\secrets.toml"

    echo.
    echo  ┌─────────────────────────────────────────────────────────┐
    echo  │  IMPORTANTE: O arquivo de configuracao sera aberto.     │
    echo  │  Preencha DATABASE_URL, admin_email e senha.            │
    echo  │  Salve ^(Ctrl+S^) e feche o Notepad para continuar.      │
    echo  └─────────────────────────────────────────────────────────┘
    echo.
    pause

    notepad "%INSTALL_DIR%\.streamlit\secrets.toml"

    echo  Aguardando voce fechar o Notepad...
    :wait_notepad
    tasklist /fi "imagename eq notepad.exe" 2>nul | find /i "notepad.exe" >nul
    if not %errorlevel% neq 0 (
        timeout /t 2 /nobreak >nul
        goto wait_notepad
    )
) else (
    echo     Credenciais ja configuradas — OK
)

:: ── 5. Atalho na Area de Trabalho ─────────────────────────────────────────────
echo [5/5] Criando atalho na Area de Trabalho...
powershell -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$s = $ws.CreateShortcut([System.IO.Path]::Combine($env:USERPROFILE, 'Desktop', 'Orcamento Pessoal.lnk')); " ^
    "$s.TargetPath = '%INSTALL_DIR%\iniciar.bat'; " ^
    "$s.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$s.WindowStyle = 1; " ^
    "$s.IconLocation = '%SystemRoot%\System32\shell32.dll, 291'; " ^
    "$s.Description = 'Orcamento Pessoal'; " ^
    "$s.Save()"
echo     OK

echo.
echo  ================================================
echo   Instalacao concluida com sucesso!
echo.
echo   Um atalho foi criado na sua Area de Trabalho.
echo   Clique em "Orcamento Pessoal" para iniciar.
echo  ================================================
echo.
pause
