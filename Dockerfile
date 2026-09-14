FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=America/Campo_Grande
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tzdata curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY collector ./collector
COPY web ./web
COPY sql ./sql
RUN pip install --no-cache-dir .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
