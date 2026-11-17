# SkyWatch read-only API. Build context is this api/ directory (see
# docker-compose.yml), so the app imports as `main:app`.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8000

# 0.0.0.0 so the port is reachable from outside the container.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
