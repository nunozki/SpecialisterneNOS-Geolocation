@echo off

REM Verifica se o Python 3.12.7 está instalado
python --version 2>nul | findstr /r /c:"Python 3.12.7" >nul
IF ERRORLEVEL 1 (
    echo Python 3.12.7 não encontrado.
    echo Abrindo a Microsoft Store para instalar Python 3.12.7...

    REM Abre a Microsoft Store na página do Python
    start ms-windows-store://pdp/?ProductId=9PJPW5L2Z5X5

    echo Após a instalação, pressione qualquer tecla para continuar...
    pause >nul
)

REM Instala as dependências do requirements.txt
pip install -r requirements.txt

REM Cria o ambiente virtual
py -3.12 -m venv .venv

REM Ativa o ambiente virtual
call .venv\Scripts\activate

REM Executa o arquivo main.py
python main.py

REM Desativa o ambiente virtual (opcional)
deactivate

pause
