#!/bin/sh
# Grafana at http://localhost:3000 (user: admin). Ctrl+C to stop.
echo "admin password:"
docker run --rm --network kind -v shrinkr-kube:/root/.kube shrinkr-toolbox \
  sh -c "kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d; echo"
docker run --rm -it --network kind -p 3000:3000 -v shrinkr-kube:/root/.kube shrinkr-toolbox \
  kubectl port-forward --address 0.0.0.0 -n monitoring svc/monitoring-grafana 3000:80
