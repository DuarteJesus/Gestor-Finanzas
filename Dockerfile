FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/gestor_finanzas_server.db

WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt \
    && mkdir -p /data
COPY api.py .

EXPOSE 8000
VOLUME ["/data"]
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]