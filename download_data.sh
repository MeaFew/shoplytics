#!/usr/bin/env bash
# Download real dataset for ecommerce-user-analytics
# Source: Alibaba Tianchi — Taobao User Behavior (29M records)
# Size: ~1.1GB compressed → ~1.1GB CSV

set -euo pipefail

RELEASE_URL="https://github.com/MeaFew/ecommerce-user-analytics/releases/download/v1.0-data/data.zip"
DEST_DIR="$(dirname "$0")"

echo "Downloading data for ecommerce-user-analytics..."
curl -L -o "${DEST_DIR}/data.zip" "${RELEASE_URL}"

echo "Extracting..."
unzip -o "${DEST_DIR}/data.zip" -d "${DEST_DIR}/data/raw/"
# Also extract data_dictionary.csv to processed/
mkdir -p "${DEST_DIR}/data/processed"
unzip -o "${DEST_DIR}/data.zip" "data_dictionary.csv" -d "${DEST_DIR}/data/processed/" 2>/dev/null || true

rm "${DEST_DIR}/data.zip"
echo "Done. Run 'make all' to run the full pipeline."
