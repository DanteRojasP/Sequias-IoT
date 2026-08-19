FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lima_cloud/ ./lima_cloud/

ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "lima_cloud.main"]
