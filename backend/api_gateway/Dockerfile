# api_gateway - Phase 1 skeleton Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY backend/api_gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/shared /app/shared
RUN pip install --no-cache-dir -r /app/shared/requirements.txt

COPY backend/api_gateway/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
