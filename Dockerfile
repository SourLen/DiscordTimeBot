FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY timebot ./timebot

# Sessions live here; mount a volume so they survive container replacement.
ENV DATABASE_PATH=/app/data/timebot.db
VOLUME ["/app/data"]

RUN useradd --create-home --uid 10001 timebot \
    && mkdir -p /app/data && chown -R timebot:timebot /app
USER timebot

CMD ["python", "main.py"]
