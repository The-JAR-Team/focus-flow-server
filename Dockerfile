# ------------- Stage 1: Builder -------------
# Installs build tools and dependencies needed for compiling Python packages.
FROM python:3.10-slim AS builder

LABEL stage="builder"

# Install build-time system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libssl-dev \
        ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy ONLY requirements.txt first to leverage Docker cache.
COPY requirements.txt .


# ------------- Stage 2: Installer -------------
# Installs Python packages based on requirements.txt.
FROM builder AS installer

LABEL stage="installer"
# WORKDIR /app is inherited

# Install Python dependencies into a target directory (/install)
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ------------- Stage 3: Final -------------
# Creates the minimal final runtime image.
FROM python:3.10-slim AS final

LABEL stage="final"

# --- Add ARGs for build-time variables ---
ARG SERVER_VERSION_ARG=unknown
ARG BUILD_TIMESTAMP_ARG="not set" # Added build timestamp arg

# Set recommended environment variables for Python in containers
# --- Set ENV vars using the ARGs ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SERVER_VERSION=$SERVER_VERSION_ARG \
    BUILD_TIMESTAMP=$BUILD_TIMESTAMP_ARG

WORKDIR /app

# Install ONLY essential runtime system dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the installed Python packages from the 'installer' stage.
COPY --from=installer /install /usr/local

# Copy your application code into the image.
COPY . .

# Expose port (Informational)
# EXPOSE 8080

# Set the command to run your application using Gunicorn.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 10 --timeout 3600 server.main.app:app"]

