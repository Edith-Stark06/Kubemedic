FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8000

# Build-time levers: bake a "good" (v1.0, healthy) or "bad" (v1.1, HEALTHY=false)
# image from the same source. The bad image reproduces the readiness regression.
ARG APP_VERSION=1.0
ARG HEALTHY=true
ENV APP_VERSION=${APP_VERSION} \
    HEALTHY=${HEALTHY}

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
