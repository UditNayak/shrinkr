#!/bin/sh
# Argo Rollouts CLI, from its official image. Use from the repo root:
#   ./toolbox/rollouts.sh get rollout app -n shrinkr --watch
#   ./toolbox/rollouts.sh dashboard      web UI at http://localhost:3100 (Ctrl+C to stop)
set -e
ports=""
if [ "$1" = "dashboard" ]; then
  # listen on all addresses so the port can be published to the Mac
  set -- dashboard --address 0.0.0.0 -n shrinkr
  ports="-p 3100:3100"
fi
# runs as root to read the kubeconfig that the toolbox wrote
docker run --rm -it --user 0 --network kind $ports \
  -v shrinkr-kube:/root/.kube -e KUBECONFIG=/root/.kube/config \
  quay.io/argoproj/kubectl-argo-rollouts:v1.10.1 "$@"
