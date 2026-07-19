# translation_service - Phase 1 skeleton Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY backend/translation_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/shared /app/shared
RUN pip install --no-cache-dir -r /app/shared/requirements.txt

COPY backend/translation_service/app ./app

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
