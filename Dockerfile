# Stage 1: Build dependencies
FROM python:3.10-slim AS builder

WORKDIR /app

# Install build dependencies (these won't be in the final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .

# Upgrade pip and install Python dependencies into /install
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.10-slim

ENV PYTHONPATH=/app

WORKDIR /app

# Install minimal runtime dependencies (if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy installed dependencies from the builder stage
COPY --from=builder /install /usr/local

# Copy your application code; ensure you have a .dockerignore to exclude sensitive files (.env, etc.)
COPY . .

EXPOSE 5000

CMD ["python", "server/main/app.py"]
