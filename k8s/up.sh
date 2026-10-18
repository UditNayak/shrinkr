#!/bin/sh
# Set up the kind cluster and Argo CD; Argo CD then deploys shrinkr from git.
# Run in the toolbox:  ./toolbox/run.sh k8s/up.sh
set -e

kind get clusters | grep -q shrinkr || kind create cluster --config k8s/kind-cluster.yaml
# use the cluster's internal address, reachable from the toolbox
kind export kubeconfig --name shrinkr --internal

kubectl apply -f k8s/namespace.yaml

# random password, created once and kept only in the cluster (not in git)
if ! kubectl -n shrinkr get secret shrinkr-db >/dev/null 2>&1; then
  password=$(openssl rand -hex 16)
  kubectl -n shrinkr create secret generic shrinkr-db \
    --from-literal=POSTGRES_PASSWORD="$password" \
    --from-literal=DATABASE_URL="postgresql+psycopg://shrinkr:$password@postgres:5432/shrinkr"
fi

kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.5/manifests/install.yaml
kubectl wait --for condition=established crd/applications.argoproj.io

# the Applications tell Argo CD what to deploy from the repository
kubectl apply -f k8s/argocd/

echo "Argo CD is deploying shrinkr. Check with: kubectl -n argocd get applications"
