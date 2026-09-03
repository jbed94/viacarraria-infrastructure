#!/usr/bin/env bash

set -euo pipefail

: "${CONDA_PREFIX:?Run this script through 'mamba run -n viacarraria-infrastructure ...'}"

helm_version="${HELM_VERSION:-3.19.0}"
kubectl_version="${KUBECTL_VERSION:-1.33.0}"
case "$(uname -m)" in
  x86_64) platform="amd64" ;;
  aarch64|arm64) platform="arm64" ;;
  *) printf 'Unsupported Linux architecture: %s\n' "$(uname -m)" >&2; exit 1 ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

helm_archive="helm-v${helm_version}-linux-${platform}.tar.gz"
curl --fail --silent --show-error --location --output "$tmp_dir/$helm_archive" \
  "https://get.helm.sh/$helm_archive"
curl --fail --silent --show-error --location --output "$tmp_dir/$helm_archive.sha256sum" \
  "https://get.helm.sh/$helm_archive.sha256sum"
(cd "$tmp_dir" && sha256sum --check "$helm_archive.sha256sum")
tar --extract --gzip --file "$tmp_dir/$helm_archive" --directory "$tmp_dir"
install -m 0755 "$tmp_dir/linux-${platform}/helm" "$CONDA_PREFIX/bin/helm"

curl --fail --silent --show-error --location --output "$tmp_dir/kubectl" \
  "https://dl.k8s.io/release/v${kubectl_version}/bin/linux/${platform}/kubectl"
curl --fail --silent --show-error --location --output "$tmp_dir/kubectl.sha256" \
  "https://dl.k8s.io/release/v${kubectl_version}/bin/linux/${platform}/kubectl.sha256"
printf '%s  %s\n' "$(cat "$tmp_dir/kubectl.sha256")" "$tmp_dir/kubectl" | sha256sum --check
install -m 0755 "$tmp_dir/kubectl" "$CONDA_PREFIX/bin/kubectl"

helm version --short
kubectl version --client=true --output=yaml