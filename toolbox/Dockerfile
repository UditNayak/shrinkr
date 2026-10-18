FROM docker:29.9.1-cli

ARG KIND_VERSION=v0.33.0
ARG KUBECTL_VERSION=v1.37.1
ARG HELM_VERSION=v4.3.1
# arm64 on Apple Silicon, amd64 elsewhere (set by docker build)
ARG TARGETARCH

RUN apk add --no-cache openssl \
 && wget -qO /usr/local/bin/kind https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${TARGETARCH} \
 && wget -qO /usr/local/bin/kubectl https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl \
 && wget -qO- https://get.helm.sh/helm-${HELM_VERSION}-linux-${TARGETARCH}.tar.gz | tar -xz -C /usr/local/bin --strip-components=1 linux-${TARGETARCH}/helm \
 && chmod +x /usr/local/bin/kind /usr/local/bin/kubectl

CMD ["sh"]
