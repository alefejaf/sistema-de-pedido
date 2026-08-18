# Imagem para self-hosting no TrueNAS SCALE (Docker/Apps).
# Não altera nenhuma logica do app: apenas empacota o que ja existe em
# requirements.txt e no codigo-fonte, para rodar `streamlit run app.py`.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl e usado apenas pelo HEALTHCHECK (endpoint /_stcore/health do Streamlit).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Instala as dependencias primeiro para aproveitar cache de camada do Docker
# quando so o codigo-fonte muda (requirements.txt continua o mesmo arquivo
# usado no Streamlit Community Cloud, sem alteracoes).
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copia somente os arquivos necessarios em runtime.
COPY app.py .
COPY grade_app/ ./grade_app/
COPY configs/ ./configs/
COPY config_padrao.xlsx .

# Config DE/PARA por cliente (configs/) e os backups automaticos
# (backups_config/) sao dados de runtime: ficam com dono do usuario nao-root
# e devem receber um volume persistente no docker-compose/TrueNAS, senao as
# edicoes feitas em CONFIGURACOES se perdem a cada recriacao do container.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/backups_config \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

# Streamlit expoe esse endpoint de saude desde a serie 1.x (requirements.txt
# pede streamlit>=1.33, que ja possui o endpoint).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

# Equivalente exato ao comando de inicializacao pedido:
#   streamlit run app.py --server.address=0.0.0.0 --server.port=8501
ENTRYPOINT ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
