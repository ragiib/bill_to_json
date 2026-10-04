# Use official slim Python 3.11 image
FROM python:3.11-slim

# Set environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install system dependencies for image processing and ONNX runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app

# Expose default port
EXPOSE 8080

# Cloud Run and Render inject $PORT at runtime; uvicorn dynamically binds to it
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
