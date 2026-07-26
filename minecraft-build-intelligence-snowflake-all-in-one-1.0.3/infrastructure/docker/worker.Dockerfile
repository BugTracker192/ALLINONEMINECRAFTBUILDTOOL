FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 mbi
WORKDIR /app
COPY services/core /app/services/core
COPY apps/worker /app/apps/worker
RUN pip install --no-cache-dir /app/services/core /app/apps/worker
USER mbi
CMD ["celery", "-A", "mbi_worker.app:celery_app", "worker", "--loglevel=INFO", "--concurrency=2"]
