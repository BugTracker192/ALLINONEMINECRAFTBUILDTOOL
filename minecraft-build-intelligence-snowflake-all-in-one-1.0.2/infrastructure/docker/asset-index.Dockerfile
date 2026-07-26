FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 mbi
WORKDIR /app
COPY services/core /app/services/core
COPY scripts/index_resource_pack.py /app/scripts/index_resource_pack.py
RUN pip install --no-cache-dir /app/services/core
USER mbi
ENTRYPOINT ["python", "/app/scripts/index_resource_pack.py"]
