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

if ! kubectl -n monitoring get secret grafana-admin >/dev/null 2>&1; then
  kubectl -n monitoring create secret generic grafana-admin \
    --from-literal=admin-user=admin --from-literal=admin-password="$(openssl rand -hex 12)"
fi

kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.5/manifests/install.yaml
kubectl wait --for condition=established crd/applications.argoproj.io
# the UI on a fixed NodePort, mapped to https://localhost:8080 by kind-cluster.yaml
kubectl -n argocd patch svc argocd-server -p '{"spec":{"type":"NodePort","ports":[{"port":443,"nodePort":30443}]}}'

# Argo Rollouts runs the canary for the app; installed before shrinkr uses a Rollout
kubectl apply -n argo-rollouts --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-rollouts/v1.10.1/manifests/install.yaml
kubectl wait --for condition=established crd/rollouts.argoproj.io

# the Applications tell Argo CD what to deploy from the repository
kubectl apply -f k8s/argocd/

# Rollouts dashboard at http://localhost:3100; Docker restarts it whenever Docker starts
docker rm -f shrinkr-rollouts-dashboard >/dev/null 2>&1 || true
docker run -d --name shrinkr-rollouts-dashboard --restart unless-stopped --user 0 --network kind \
  -p 127.0.0.1:3100:3100 -v shrinkr-kube:/root/.kube -e KUBECONFIG=/root/.kube/config \
  quay.io/argoproj/kubectl-argo-rollouts:v1.10.1 dashboard --address 0.0.0.0 -n shrinkr >/dev/null

echo "Argo CD is deploying shrinkr. Check with: kubectl -n argocd get applications"
