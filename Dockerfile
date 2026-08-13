FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md main.py ./
COPY src ./src
COPY config ./config
COPY dados_teste.csv ./dados_teste.csv

RUN pip install --upgrade pip setuptools wheel && \
    pip install .


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY main.py ./main.py
COPY src ./src
COPY config ./config
COPY dados_teste.csv ./dados_teste.csv

RUN mkdir -p /app/logs /app/reports

CMD ["python", "main.py", "--once", "--csv-path", "/app/dados_teste.csv"]
