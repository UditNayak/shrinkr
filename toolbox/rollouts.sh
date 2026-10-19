#!/bin/sh
# Argo Rollouts CLI, from its official image. Use from the repo root:
#   ./toolbox/rollouts.sh get rollout app -n shrinkr --watch
set -e
# runs as root to read the kubeconfig that the toolbox wrote
docker run --rm -it --user 0 --network kind \
  -v shrinkr-kube:/root/.kube -e KUBECONFIG=/root/.kube/config \
  quay.io/argoproj/kubectl-argo-rollouts:v1.10.1 "$@"
