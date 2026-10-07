FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for libopus and audio
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopus0 \
    libopus-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy gateway and models
COPY gateway /app/gateway
COPY models /app/models

EXPOSE 8001

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8001"]
