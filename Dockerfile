FROM python:3.10-slim AS builder

LABEL stage="builder"

# Install build-time system dependencies
# - gcc & libssl-dev: Likely needed for C extensions (like bcrypt).
# - ca-certificates: For secure connections (HTTPS).
# - Check if libxml2-dev/libxslt1-dev are needed (if lxml is a dependency). Remove if not.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libssl-dev \
        ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip for potentially better dependency resolution and wheel handling
RUN pip install --no-cache-dir --upgrade pip

# Copy ONLY requirements.txt first.
# Docker caches this layer. It only invalidates if requirements.txt changes.
COPY requirements.txt .


# ------------- Stage 2: Installer -------------
# Installs Python packages based on requirements.txt from the previous stage.
# This is often the longest step, so caching it is beneficial.
# -------------
FROM builder AS installer

LABEL stage="installer"
# WORKDIR /app is inherited

# Install Python dependencies into a target directory (/install)
# Uses requirements.txt copied in the 'builder' stage.
# --no-cache-dir prevents pip caching within this layer.
# --prefix=/install installs packages into /install instead of the system default.
# This layer rebuilds only if the 'builder' stage changed.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ------------- Stage 3: Final -------------
# Creates the minimal final runtime image.
# Copies installed packages from 'installer' stage.
# Copies application code.
# -------------
FROM python:3.10-slim AS final

LABEL stage="final"

# Set recommended environment variables for Python in containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install ONLY essential runtime system dependencies.
# 'ca-certificates' is usually needed for HTTPS calls.
# 'psycopg2-binary' includes its own libraries, so 'libpq5' is likely NOT needed here.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the installed Python packages from the 'installer' stage's /install directory
# into the final image's Python site-packages location.
COPY --from=installer /install /usr/local

# Copy your application code into the image.
# ****** CRITICAL: Make sure you have a good .dockerignore file ******
# This prevents copying unnecessary files (.git, venv, .env, etc.)
COPY . .

# Expose port (Note: Cloud Run ignores this and uses the port from CMD/$PORT)
# EXPOSE 8080

# Set the command to run your application using Gunicorn.
# It binds to all interfaces (0.0.0.0) and uses the PORT env variable
# provided by Cloud Run (or defaults to 8080 if not set).
# Adjust workers and timeout as needed for your specific application/instance size.
# Ensure 'server.main.app:app' correctly points to your Flask application instance.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 5 --timeout 3600 server.main.app:app"]
