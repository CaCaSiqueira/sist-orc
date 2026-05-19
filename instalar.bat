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

:: 1. Verifica Python
echo [1/5] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 goto instalar_python
echo     OK
goto continuar

:instalar_python
echo     Python nao encontrado. Baixando Python 3.11...
curl -L -o "%TEMP%\python_installer.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if %errorlevel% neq 0 (
    echo     ERRO ao baixar Python. Verifique sua conexao.
    pause
    exit /b 1
)
echo     Instalando Python (aguarde alguns minutos)...
"%TEMP%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
del "%TEMP%\python_installer.exe"
echo.
echo     Python instalado!
echo     ATENCAO: Feche esta janela e execute instalar.bat novamente.
echo.
pause
exit /b

:continuar

:: 2. Baixa o aplicativo
echo [2/5] Baixando aplicativo do GitHub...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
curl -L -o "%TEMP_ZIP%" "%REPO_ZIP%"
if %errorlevel% neq 0 (
    echo     ERRO: Nao foi possivel baixar. Verifique sua conexao.
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo     Extraindo arquivos...
powershell -Command "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_DIR%' -Force"
robocopy "%TEMP_DIR%\sist-orc-main" "%INSTALL_DIR%" /E /XD ".streamlit" "venv" /NFL /NDL /NJH /NJS >nul
del "%TEMP_ZIP%"
rmdir /s /q "%TEMP_DIR%" 2>nul
echo     OK

:: 3. Ambiente virtual Python
echo [3/5] Configurando ambiente Python (pode demorar na 1a vez)...
cd /d "%INSTALL_DIR%"
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo     ERRO ao instalar dependencias.
    pause
    exit /b 1
)
echo     OK

:: 4. Configura credenciais
echo [4/5] Configurando credenciais...
if exist "%INSTALL_DIR%\.streamlit\secrets.toml" (
    echo     Credenciais ja configuradas - OK
    goto criar_atalho
)

mkdir "%INSTALL_DIR%\.streamlit" 2>nul
(
    echo # PREENCHA COM SUAS CREDENCIAIS E SALVE O ARQUIVO
    echo # Depois feche o Notepad para continuar a instalacao.
    echo.
    echo # Banco de dados
    echo DATABASE_URL = "COLE_AQUI_A_URL_DO_SUPABASE"
    echo.
    echo # E-mail do administrador
    echo admin_email = "SEU_EMAIL@EXEMPLO.COM"
    echo.
    echo # Login de acesso
    echo [users]
    echo "SEU_EMAIL@EXEMPLO.COM" = "SUA_SENHA"
) > "%INSTALL_DIR%\.streamlit\secrets.toml"

echo.
echo  IMPORTANTE: O Notepad vai abrir com o arquivo de configuracao.
echo  Preencha os seus dados, salve (Ctrl+S) e feche o Notepad.
echo.
pause
notepad "%INSTALL_DIR%\.streamlit\secrets.toml"
echo     OK

:: 5. Atalho na Area de Trabalho
:criar_atalho
echo [5/5] Criando atalho na Area de Trabalho...
powershell -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%USERPROFILE%\Desktop\Orcamento Pessoal.lnk'); $s.TargetPath='%INSTALL_DIR%\iniciar.bat'; $s.WorkingDirectory='%INSTALL_DIR%'; $s.WindowStyle=1; $s.IconLocation='%SystemRoot%\System32\shell32.dll,291'; $s.Save()"
echo     OK

echo.
echo  ================================================
echo   Instalacao concluida com sucesso!
echo.
echo   Atalho criado na Area de Trabalho.
echo   Clique em "Orcamento Pessoal" para iniciar.
echo  ================================================
echo.
pause
