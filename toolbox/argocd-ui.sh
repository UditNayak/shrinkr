#!/bin/sh
# Argo CD web UI at https://localhost:8080 (user: admin). Ctrl+C to stop.

echo "admin password:"
docker run --rm --network kind -v shrinkr-kube:/root/.kube shrinkr-toolbox \
  sh -c "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo"

docker run --rm -it --network kind -p 8080:8080 -v shrinkr-kube:/root/.kube shrinkr-toolbox \
  kubectl port-forward --address 0.0.0.0 -n argocd svc/argocd-server 8080:443
