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
# This now includes gunicorn
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

# EXPOSE 5000 # Note: Cloud Run ignores EXPOSE, uses port from CMD/$PORT instead

# --- CHANGE THE CMD TO USE GUNICORN ---
# Gunicorn needs to know where your Flask app object is.
# Assuming your Flask app instance in 'server/main/app.py' is named 'app',
# the path is 'server.main.app:app'.
# We bind to 0.0.0.0 and the $PORT Cloud Run provides.
# '-w 2' starts 2 worker processes (adjust based on Cloud Run instance CPU/memory).
# Using 'sh -c' allows the $PORT environment variable to be expanded correctly.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 3 --timeout 3600 server.main.app:app"]

# For testing without Gunicorn:
#CMD ["python", "server/main/app.py"]