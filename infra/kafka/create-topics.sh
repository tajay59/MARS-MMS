#!/bin/bash
# Creates or updates the topics in topics.yml. Idempotent. Partitions only ever grow:
# Kafka cannot shrink them, and changing the count moves keys between partitions.
set -euo pipefail

FILE="${1:?usage: create-topics.sh topics.yml}"
BOOTSTRAP="${KAFKA_BOOTSTRAP:-kafka:9092}"
BIN=/opt/kafka/bin

apply() {
  local name="$1" partitions="$2" retention="$3"
  if "$BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --describe --topic "$name" > /dev/null 2>&1; then
    "$BIN/kafka-configs.sh" --bootstrap-server "$BOOTSTRAP" --alter --entity-type topics \
      --entity-name "$name" --add-config "retention.ms=$retention" > /dev/null
    echo "updated $name"
  else
    "$BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --create --topic "$name" \
      --partitions "$partitions" --replication-factor 1 --config "retention.ms=$retention" > /dev/null
    echo "created $name ($partitions partitions)"
  fi
}

name="" partitions="" retention=""
while IFS= read -r line; do
  line="${line%%#*}"
  case "$line" in
    *"- name:"*)
      [ -n "$name" ] && apply "$name" "$partitions" "$retention"
      name="$(echo "${line#*name:}" | tr -d '[:space:]')"
      partitions="" retention=""
      ;;
    *"partitions:"*) partitions="$(echo "${line#*partitions:}" | tr -d '[:space:]')" ;;
    *"retention_ms:"*) retention="$(echo "${line#*retention_ms:}" | tr -d '[:space:]')" ;;
  esac
done < "$FILE"
[ -n "$name" ] && apply "$name" "$partitions" "$retention"
echo "kafka-init done"
