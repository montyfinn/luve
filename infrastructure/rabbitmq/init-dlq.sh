#!/bin/sh
# Idempotent, post-boot RabbitMQ DLQ setup for the grading queue (T5b).
#
# Creates a dead-letter exchange + queue + binding and attaches a dead-letter
# POLICY to the existing `luve.session.completed` queue WITHOUT changing its
# declare arguments (so it never triggers PRECONDITION_FAILED 406). Poison
# messages that the worker reject(requeue=False)s are then retained in the DLQ
# instead of being dropped.
#
# Uses the management HTTP API via rabbitmqadmin, so it needs no Erlang cookie
# and can run from any container on the same network. Safe to run repeatedly.
set -eu

RABBITMQ_HOST="${RABBITMQ_HOST:-localhost}"
RABBITMQ_MGMT_PORT="${RABBITMQ_MGMT_PORT:-15672}"
: "${RABBITMQ_USER:?RABBITMQ_USER is required}"
: "${RABBITMQ_PASS:?RABBITMQ_PASS is required}"

SOURCE_QUEUE="luve.session.completed"
DLX="luve.dlx"
DLQ="luve.session.completed.dlq"

# Credentials are passed to rabbitmqadmin but never echoed.
adm() {
  rabbitmqadmin --host="$RABBITMQ_HOST" --port="$RABBITMQ_MGMT_PORT" \
    --username="$RABBITMQ_USER" --password="$RABBITMQ_PASS" "$@"
}

# Wait for the management API to accept requests (depends_on healthy only
# guarantees the broker node is up, not that the HTTP API is ready).
i=0
until adm list users >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 30 ]; then
    echo "rabbitmq-dlq-init: management API not reachable at ${RABBITMQ_HOST}:${RABBITMQ_MGMT_PORT}" >&2
    exit 1
  fi
  echo "rabbitmq-dlq-init: waiting for management API (attempt ${i})"
  sleep 2
done

echo "rabbitmq-dlq-init: declaring exchange ${DLX} (direct, durable)"
adm declare exchange name="$DLX" type=direct durable=true

echo "rabbitmq-dlq-init: declaring queue ${DLQ} (durable)"
adm declare queue name="$DLQ" durable=true

echo "rabbitmq-dlq-init: binding ${DLX} -> ${DLQ} (routing_key=${SOURCE_QUEUE})"
adm declare binding source="$DLX" destination="$DLQ" \
  destination_type=queue routing_key="$SOURCE_QUEUE"

echo "rabbitmq-dlq-init: setting policy dlq-grading on the source queue"
adm declare policy name=dlq-grading apply-to=queues priority=0 \
  pattern='^luve\.session\.completed$' \
  definition='{"dead-letter-exchange":"luve.dlx","dead-letter-routing-key":"luve.session.completed"}'

echo "rabbitmq-dlq-init: done"
