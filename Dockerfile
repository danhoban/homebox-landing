FROM python:3.13-slim

WORKDIR /app

RUN useradd -r -u 1001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY templates/ ./templates/

USER appuser

EXPOSE 8080

CMD ["python", "-m", "app.main"]
