FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# HEALTHY=true  → normal operation (readiness passes, bookings accepted)
# HEALTHY=false → degraded (readiness fails, real Kubernetes events generated)
ENV HEALTHY=true
ENV APP_VERSION=1.0

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
