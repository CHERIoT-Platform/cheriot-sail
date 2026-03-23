#!/usr/bin/env bash
# docker-run.sh
#
# Helper script to build the Docker image (if needed) and run commands
# inside the CHERIoT-Sail build container.
#
# Usage:
#   ./docker-run.sh                         # interactive bash shell
#   ./docker-run.sh make csim               # build standard simulator
#   ./docker-run.sh make rvfi               # build RVFI DII simulator
#   ./docker-run.sh make ARCH=RV64 rvfi     # build RV64 RVFI DII simulator
#   ./docker-run.sh make clean              # clean build artifacts
#   ./docker-run.sh bash -c "make csim && make rvfi"  # multiple commands
#
# The current directory is mounted into the container at /work, so build
# outputs (c_emulator/*, generated_definitions/*) appear in your local
# directory after the run completes.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IMAGE_NAME="cheriot-sail"
IMAGE_TAG="latest"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

# Resolve the repository root (directory containing this script)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Build the image if it does not already exist or if --rebuild is passed
# ---------------------------------------------------------------------------
REBUILD=0
if [[ "${1:-}" == "--rebuild" ]]; then
    REBUILD=1
    shift
fi

if [[ "$REBUILD" -eq 1 ]] || ! docker image inspect "${FULL_IMAGE}" &>/dev/null; then
    echo "==> Building Docker image '${FULL_IMAGE}' ..."
    docker build -t "${FULL_IMAGE}" "${REPO_ROOT}"
    echo "==> Image built successfully."
fi

# ---------------------------------------------------------------------------
# Determine docker run flags
# ---------------------------------------------------------------------------

# Mount the repository root as /work (read-write so build outputs land locally)
MOUNT_FLAGS=(-v "${REPO_ROOT}:/work")

# If running interactively (no arguments, or explicit 'bash'/'sh')
TTY_FLAGS=()
if [[ $# -eq 0 ]] || [[ "${1:-}" == "bash" ]] || [[ "${1:-}" == "sh" ]]; then
    TTY_FLAGS=(-it)
fi

# Pass through host user/group so files written inside the container are
# owned by the current user, not root.  (Only works on Linux.)
USER_FLAGS=()
if [[ "$(uname -s)" == "Linux" ]]; then
    USER_FLAGS=(--user "$(id -u):$(id -g)")
    # Ensure the opam env file is readable by the mapped UID
    # (it was written by uid 1000 inside the image; on macOS this is fine)
fi

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
    echo "==> Starting interactive shell in '${FULL_IMAGE}' ..."
    echo "    Repository mounted at /work"
    echo "    Type 'exit' to leave the container."
    echo ""
fi

docker run \
    --rm \
    "${TTY_FLAGS[@]}" \
    "${MOUNT_FLAGS[@]}" \
    "${FULL_IMAGE}" \
    "${@:-bash}"
