#!/bin/sh
# Prints the web UI addresses and their admin passwords.
echo "App:     http://localhost"
echo "Argo CD: https://localhost:8080   user admin, password:"
docker run --rm --network kind -v shrinkr-kube:/root/.kube shrinkr-toolbox \
  sh -c "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo"
echo "Grafana: http://localhost:3000    user admin, password:"
docker run --rm --network kind -v shrinkr-kube:/root/.kube shrinkr-toolbox \
  sh -c "kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d; echo"
