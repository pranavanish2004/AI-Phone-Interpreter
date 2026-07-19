# tts_service - Phase 1 skeleton Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY backend/tts_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/shared /app/shared
RUN pip install --no-cache-dir -r /app/shared/requirements.txt

COPY backend/tts_service/app ./app

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
