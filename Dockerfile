FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
COPY docker/entrypoint.sh /entrypoint.sh
RUN useradd --uid 10001 --create-home app && mkdir -p /data/videos /app/staticfiles && chown -R app:app /data /app
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "/entrypoint.sh"]
