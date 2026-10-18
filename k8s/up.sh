#!/bin/sh
# Create the kind cluster if needed and deploy shrinkr. Run in the toolbox:
#   ./toolbox/run.sh k8s/up.sh
set -e

kind get clusters | grep -q shrinkr || kind create cluster --config k8s/kind-cluster.yaml
# use the cluster's internal address, reachable from the toolbox
kind export kubeconfig --name shrinkr --internal

# a new tag for every build, so Kubernetes sees a change and rolls out the new image
tag=$(date +%Y%m%d%H%M%S)
docker build -t shrinkr:$tag .
kind load docker-image shrinkr:$tag --name shrinkr

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

# migrations run first (a Helm hook); --wait returns when the new pods are ready
helm upgrade --install shrinkr charts/shrinkr -n shrinkr --set image.tag=$tag --wait

echo "shrinkr is running at http://localhost"
