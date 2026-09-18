#!/usr/bin/env bash
set -euo pipefail

UNRAID_HOST="${UNRAID_HOST:-unraid}"
IMAGE_NAME="videomessaging-app:latest"
CONTAINER_NAME="videomessaging"

echo "==> Building local Docker image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

echo "==> Transferring Docker image to Unraid ($UNRAID_HOST)..."
docker save "$IMAGE_NAME" | gzip -1 | ssh "$UNRAID_HOST" "gunzip | docker load"

echo "==> Restarting container $CONTAINER_NAME on Unraid..."
ssh "$UNRAID_HOST" "docker restart $CONTAINER_NAME"

echo "==> Waiting for container to become ready..."
sleep 4
ssh "$UNRAID_HOST" "docker logs $CONTAINER_NAME 2>&1 | tail -n 10"

echo "==> Checking https://vidtest.biel.casa..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://vidtest.biel.casa || true)
echo "HTTP response status: $HTTP_STATUS"
echo "==> Deployment complete!"
