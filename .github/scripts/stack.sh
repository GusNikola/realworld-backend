#!/usr/bin/env bash
# Starts or stops a throwaway backend stack (PostgreSQL + API) on its own Docker
# network. Used by the e2e and performance jobs, and runnable locally.
#
#   stack.sh up NAME IMAGE   API reachable as http://NAME-api:8080/api on network NAME
#   stack.sh down NAME
set -euo pipefail

cmd=${1:?usage: stack.sh up NAME IMAGE | down NAME}
name=${2:?stack name required}

db_env=(-e POSTGRES_USER=conduit -e POSTGRES_PASSWORD=conduit -e POSTGRES_DB=conduit)

case "$cmd" in
up)
  image=${3:?image required}
  docker network create "$name" >/dev/null

  docker run -d --name "$name-db" --network "$name" --cpus 1 "${db_env[@]}" \
    postgres:16 >/dev/null
  # TCP only answers after the init scripts finish and the final server starts.
  for _ in $(seq 60); do
    docker exec "$name-db" pg_isready -h 127.0.0.1 -U conduit -d conduit >/dev/null 2>&1 && break
    sleep 1
  done

  # The image entrypoint runs the migrations before uvicorn starts. Trusting every
  # proxy lets the load test spread requests over many client addresses, so the
  # app's per-IP rate limiter does not distort the measurement.
  docker run -d --name "$name-api" --network "$name" --cpus 1 "${db_env[@]}" \
    -e APP_ENV=prod -e POSTGRES_HOST="$name-db" -e POSTGRES_PORT=5432 \
    -e JWT_SECRET_KEY=ci-only -e SECRET_KEY=ci-only \
    "$image" uvicorn conduit.app:app --host 0.0.0.0 --port 8080 --forwarded-allow-ips='*' \
    >/dev/null

  for _ in $(seq 60); do
    if docker exec "$name-api" curl -sf http://localhost:8080/api/health-check >/dev/null 2>&1; then
      echo "stack $name is up"
      exit 0
    fi
    sleep 1
  done
  echo "stack $name did not become healthy" >&2
  docker logs "$name-api" >&2 || true
  exit 1
  ;;
down)
  docker rm -f "$name-api" "$name-db" >/dev/null 2>&1 || true
  docker network rm "$name" >/dev/null 2>&1 || true
  ;;
*)
  echo "unknown command: $cmd" >&2
  exit 2
  ;;
esac
