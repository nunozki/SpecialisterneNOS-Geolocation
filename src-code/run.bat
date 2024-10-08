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

REM Cria o ambiente virtual se não existir
IF NOT EXIST .venv (
    echo Criando o ambiente virtual...
    py -3.12 -m venv .venv
)

REM Ativa o ambiente virtual
call .venv\Scripts\activate

REM Configura a variável de ambiente FLASK_APP
set FLASK_APP=main.py

REM Executa o servidor Flask
call .venv\Scripts\flask run

REM Aguarda 5 segundos para garantir que a API foi inicializada
timeout /t 5 >nul

REM Faz a requisição curl para a API
curl http://127.0.0.1:5000/postal_codes

curl http://localhost:5000/

REM Desativa o ambiente virtual (opcional)
deactivate

pause


