FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8001

# Build-time levers: the "good" and "bad" revisions are the SAME source built
# with different arguments, which is what makes the demo failure a believable
# regression rather than two different programs.
#
#   HEALTHY=true   normal operation -- /ready passes, bookings accepted
#   HEALTHY=false  degraded -- /ready fails, so the pod never becomes Ready
#                  and the rollout stalls while the old pods keep serving
#
# ARG before ENV matters. Without the ARG lines these are fixed at build time
# and `--build-arg HEALTHY=false` is silently ignored -- which produces a
# "bad" image that is actually healthy, and an incident injection that appears
# to work and changes nothing.
ARG APP_VERSION=1.0
ARG HEALTHY=true
ENV APP_VERSION=${APP_VERSION} \
    HEALTHY=${HEALTHY}

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
