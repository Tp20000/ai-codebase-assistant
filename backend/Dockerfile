FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first (layer caching — only re-installs if requirements.txt changes)
COPY requirements.txt .

# Install Python dependencies with cache mount
# --mount=type=cache keeps downloaded packages between builds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code (changes here don't trigger pip reinstall)
COPY . .

# Create necessary directories
RUN mkdir -p /app/keys /app/uploads /app/chroma_db /app/logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
