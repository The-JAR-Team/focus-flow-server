#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Set your Docker Hub username here
DOCKERHUB_USERNAME="somejon"  # Replace with your actual Docker Hub username
IMAGE_NAME="focus-flow" # Your repository name on Docker Hub

# --- Get Version from Command Line Argument ---
if [ -z "$1" ]; then
  echo "Usage: $0 <version_tag>"
  echo "Example: $0 1.0758"
  exit 1
fi
VERSION="$1"
echo "Using provided version tag: $VERSION"

# --- Generate Build Timestamp ---
# Get current timestamp in ISO 8601 format (UTC)
BUILD_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "Using build timestamp: $BUILD_TIMESTAMP"

# --- Construct Full Image Name for Docker Hub ---
IMAGE_TAG_FULL="${DOCKERHUB_USERNAME}/${IMAGE_NAME}:${VERSION}"
IMAGE_TAG_LATEST="${DOCKERHUB_USERNAME}/${IMAGE_NAME}:latest"

# --- Build the Docker Image ---
echo "Building Docker image, setting internal version to $VERSION and build timestamp..."
# Pass both VERSION and BUILD_TIMESTAMP as build arguments
docker build \
  --build-arg SERVER_VERSION_ARG="$VERSION" \
  --build-arg BUILD_TIMESTAMP_ARG="$BUILD_TIMESTAMP" \
  -t "$IMAGE_TAG_FULL" \
  -f Dockerfile .

# Optionally tag as 'latest'
echo "Tagging image as latest..."
docker tag "$IMAGE_TAG_FULL" "$IMAGE_TAG_LATEST"


# --- Login to Docker Hub (Important Prerequisite!) ---
echo "Ensure you are logged into Docker Hub before proceeding!"
# read -p "Press Enter to continue after logging in..." # Optional pause


# --- Push the Image(s) to Docker Hub ---
echo "Pushing image $IMAGE_TAG_FULL to Docker Hub..."
docker push "$IMAGE_TAG_FULL"

echo "Pushing image $IMAGE_TAG_LATEST to Docker Hub..."
docker push "$IMAGE_TAG_LATEST"


echo "Build and push complete for version $VERSION."
echo "Image pushed: $IMAGE_TAG_FULL"
echo "Image pushed: $IMAGE_TAG_LATEST"
