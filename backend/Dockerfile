FROM python:3.12-slim

# git: the backend reads repositories for the web pages and creates them.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 1000 -m git \
    && mkdir -p /data/repos /data/releases && chown git:git /data/repos /data/releases \
    && git config --system safe.directory '*'

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

USER git
EXPOSE 5000

ENV GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=8 \
    GUNICORN_TIMEOUT=3600 \
    GUNICORN_MAX_REQUESTS=1000 \
    GUNICORN_MAX_REQUESTS_JITTER=100

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:5000 \
    --worker-class gthread \
    --workers ${GUNICORN_WORKERS} \
    --threads ${GUNICORN_THREADS} \
    --timeout ${GUNICORN_TIMEOUT} \
    --max-requests ${GUNICORN_MAX_REQUESTS} \
    --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER} \
    --worker-tmp-dir /dev/shm \
    --preload \
    'app:create_app()'"]
