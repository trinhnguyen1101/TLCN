#!/bin/sh
# Executed by the one-shot minio-init Compose service. It is safe to rerun.
set -eu

mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing local/lakehouse

# Object storage has prefixes rather than real directories. These placeholders
# make the intended medallion layout immediately visible in MinIO Console.
for layer in bronze silver gold; do
  printf 'Lakehouse logical layer: %s\n' "$layer" | mc pipe "local/lakehouse/$layer/.keep"
done
