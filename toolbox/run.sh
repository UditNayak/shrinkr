#!/bin/sh
# Run a command in the toolbox, or open a shell. Use from the repo root:
#   ./toolbox/run.sh k8s/up.sh
set -e

docker build -q -t shrinkr-toolbox toolbox >/dev/null

# kind's nodes are on this network; the toolbox joins it to reach the cluster
docker network inspect kind >/dev/null 2>&1 || docker network create kind

docker run --rm -it --network kind \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v shrinkr-kube:/root/.kube \
  -v "$PWD":/work -w /work \
  shrinkr-toolbox "$@"
