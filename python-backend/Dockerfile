FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . ./

# Create data directory for SQLite databases
RUN mkdir -p /data

# Default port for API server
ENV PORT=8000
EXPOSE 8000

# Default command runs the API server
# Override with: celery -A celery_app worker --loglevel=info
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
