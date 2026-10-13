FROM python:3.12-slim

# Python sin buffers (los logs aparecen al instante) y sin archivos .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# El código fuente NO se copia: docker-compose monta ./src en /app
# para poder editarlo desde VS Code y que Django recargue solo.

EXPOSE 8000
