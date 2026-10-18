#!/bin/sh
# Create the kind cluster if needed and deploy shrinkr. Run in the toolbox:
#   ./toolbox/run.sh k8s/up.sh
set -e

kind get clusters | grep -q shrinkr || kind create cluster --config k8s/kind-cluster.yaml
# use the cluster's internal address, reachable from the toolbox
kind export kubeconfig --name shrinkr --internal

docker build -t shrinkr:dev .
kind load docker-image shrinkr:dev --name shrinkr

kubectl apply -f k8s/namespace.yaml

# random password, created once and kept only in the cluster
if ! kubectl -n shrinkr get secret shrinkr-db >/dev/null 2>&1; then
  password=$(openssl rand -hex 16)
  kubectl -n shrinkr create secret generic shrinkr-db \
    --from-literal=POSTGRES_PASSWORD="$password" \
    --from-literal=DATABASE_URL="postgresql+psycopg://shrinkr:$password@postgres:5432/shrinkr"
fi

kubectl apply -f k8s/postgres.yaml -f k8s/redis.yaml
kubectl -n shrinkr rollout status statefulset/postgres

# a finished Job can't be re-run, so replace it and wait for it
kubectl -n shrinkr delete job migrate --ignore-not-found
kubectl apply -f k8s/migrate.yaml
kubectl -n shrinkr wait --for=condition=complete job/migrate --timeout=120s

kubectl apply -f k8s/app.yaml -f k8s/worker.yaml
# the tag is always shrinkr:dev, so restart to pick up the new image
kubectl -n shrinkr rollout restart deployment/app deployment/worker
kubectl -n shrinkr rollout status deployment/app

echo "shrinkr is running at http://localhost"
