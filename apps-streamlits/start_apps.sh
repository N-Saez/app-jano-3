#!/bin/bash


# Iniciar las apps de streamlit
nohup python3.11 -m streamlit run /home/ubuntu/app4.py --server.port 8504 --server.enableCORS false --server.address 0.0.0.0 > /home/ubuntu/streamlit4.log 2>&1 &
nohup python3.11 -m streamlit run /home/ubuntu/app3.py --server.port 8503 --server.enableCORS false --server.address 0.0.0.0 > /home/ubuntu/streamlit3.log 2>&1 &
nohup python3.11 -m streamlit run /home/ubuntu/app2.py --server.port 8502 --server.enableCORS false --server.address 0.0.0.0 > /home/ubuntu/streamlit2.log 2>&1 &

source /home/ubuntu/venvYacimientos/bin/activate

# Iniciar el script dash con Python 3.12
nohup python3.12 /home/ubuntu/appYacimientos.py > /home/ubuntu/dash.log 2>&1 &

# Desactivar el entorno virtual
deactivate
