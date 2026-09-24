# Ambiente dos gráficos, para não depender do Python instalado na máquina.
FROM python:3.12-slim
RUN pip install --no-cache-dir matplotlib==3.9.2
WORKDIR /lab
ENTRYPOINT ["python3", "analise/graficos.py"]
