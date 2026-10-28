#!/bin/sh
set -eu

source_name="${1:-}"
hour_prefixes="${2:-}"
destination="${3:-}"
bucket="${SUPABASE_S3_BUCKET:-raw-api}"

case "$source_name" in
  waqi|api_ninjas) ;;
  *) echo "Unsupported Supabase source: $source_name" >&2; exit 2 ;;
esac

case "$destination" in
  /data/waqi/*|/data/api_ninjas/*) ;;
  *) echo "Unsafe rclone destination: $destination" >&2; exit 2 ;;
esac

if [ -z "$hour_prefixes" ]; then
  echo "No UTC hour prefixes were supplied" >&2
  exit 2
fi

filter_file="$(mktemp)"
trap 'rm -f "$filter_file"' EXIT HUP INT TERM

old_ifs="$IFS"
IFS=,
set -- $hour_prefixes
IFS="$old_ifs"

if [ "$#" -ne 24 ]; then
  echo "Expected exactly 24 UTC hour prefixes, got $#" >&2
  exit 2
fi

for prefix do
  case "$prefix" in
    ????/??/??/??) printf '/%s/**\n' "$prefix" >> "$filter_file" ;;
    *) echo "Unsafe UTC hour prefix: $prefix" >&2; exit 2 ;;
  esac
done

mkdir -p "$destination"

echo "RCLONE_START source=$source_name hours=$# destination=$destination transfers=${RCLONE_TRANSFERS:-8}"
exec rclone copy \
  "supabase:${bucket}/${source_name}" \
  "$destination" \
  --include-from "$filter_file" \
  --checksum \
  --transfers "${RCLONE_TRANSFERS:-8}" \
  --checkers "${RCLONE_CHECKERS:-16}" \
  --retries "${RCLONE_RETRIES:-5}" \
  --low-level-retries "${RCLONE_LOW_LEVEL_RETRIES:-10}" \
  --contimeout "${RCLONE_CONNECT_TIMEOUT:-15s}" \
  --timeout "${RCLONE_IO_TIMEOUT:-5m}" \
  --stats 30s \
  --stats-one-line \
  --log-level INFO
