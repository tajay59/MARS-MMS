#!/bin/bash
# Creates or updates the Kafka users in users.yml: a SCRAM-SHA-512 credential each (setting it
# again rotates the password) and the ACLs listed. Idempotent. Runs over the loopback-only
# LOCAL listener, as the broker's one super user. ACLs dropped from users.yml are not removed:
# remove them by hand with kafka-acls.sh --remove.
set -euo pipefail

FILE="${1:?usage: create-users.sh users.yml}"
BOOTSTRAP="${KAFKA_BOOTSTRAP:-127.0.0.1:9094}"
BIN=/opt/kafka/bin

acl() {
  "$BIN/kafka-acls.sh" --bootstrap-server "$BOOTSTRAP" --add --allow-principal "User:$1" "${@:2}" > /dev/null
}

apply() {
  local name="$1" produce="$2" consume="$3" groups="$4" describe="$5" describe_groups="$6" optional="$7"
  local var="KAFKA_${name^^}_PASSWORD"
  local password="${!var:-}"
  if [ -z "$password" ]; then
    if [ "$optional" = true ]; then
      echo "user $name: $var is not set, skipped"
      return 0
    fi
    echo "$var is not set" >&2
    exit 1
  fi
  if [[ ! "$password" =~ ^[A-Za-z0-9_-]{16,}$ ]]; then
    echo "$var: use at least 16 letters, digits, - or _" >&2
    exit 1
  fi
  "$BIN/kafka-configs.sh" --bootstrap-server "$BOOTSTRAP" --alter --entity-type users \
    --entity-name "$name" --add-config "SCRAM-SHA-512=[iterations=8192,password=$password]" > /dev/null
  for topic in $produce; do acl "$name" --operation Write --operation Describe --topic "$topic"; done
  for topic in $consume; do acl "$name" --operation Read --operation Describe --topic "$topic"; done
  for group in $groups; do acl "$name" --operation Read --group "$group"; done
  for topic in $describe; do acl "$name" --operation Describe --topic "$topic"; done
  for group in $describe_groups; do acl "$name" --operation Describe --group "$group"; done
  echo "user $name: produce [$produce] consume [$consume] groups [$groups]"
}

name="" produce="" consume="" groups="" describe="" describe_groups="" optional=""
while IFS= read -r line; do
  line="${line%%#*}"
  case "$line" in
    *"- name:"*)
      [ -n "$name" ] && apply "$name" "$produce" "$consume" "$groups" "$describe" "$describe_groups" "$optional"
      name="$(echo "${line#*name:}" | tr -d '[:space:]')"
      produce="" consume="" groups="" describe="" describe_groups="" optional=""
      ;;
    *"produce:"*) produce="$(echo "${line#*produce:}" | xargs)" ;;
    *"consume:"*) consume="$(echo "${line#*consume:}" | xargs)" ;;
    *"describe_groups:"*) describe_groups="$(echo "${line#*describe_groups:}" | xargs)" ;;
    *"describe:"*) describe="$(echo "${line#*describe:}" | xargs)" ;;
    *"optional:"*) optional="$(echo "${line#*optional:}" | xargs)" ;;
    *"groups:"*) groups="$(echo "${line#*groups:}" | xargs)" ;;
  esac
done < "$FILE"
[ -n "$name" ] && apply "$name" "$produce" "$consume" "$groups" "$describe" "$describe_groups" "$optional"
echo "kafka users done"
