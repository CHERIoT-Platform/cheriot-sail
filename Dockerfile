# ============================================================================
# CHERIoT-Sail build environment
#
# Installs all dependencies required to build both simulator variants:
#   - c_emulator/cheriot_sim          (standard ELF simulator)
#   - c_emulator/cheri_riscv_rvfi_*   (RVFI DII + memory-dump simulator)
#
# Usage:
#   docker build -t cheriot-sail .
#   docker run --rm -v $(pwd):/work cheriot-sail make csim
#   docker run --rm -v $(pwd):/work cheriot-sail make rvfi
#
# Or use the provided helper script:
#   ./docker-run.sh make csim
#   ./docker-run.sh make rvfi
# ============================================================================

FROM ubuntu:22.04

# ---------------------------------------------------------------------------
# Avoid interactive prompts during apt-get
# ---------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# ---------------------------------------------------------------------------
# System packages
#   - build-essential    : gcc, g++, make, etc.
#   - libgmp-dev         : GNU Multiple Precision (required by Sail / GMP)
#   - zlib1g-dev         : zlib (required by Sail C runtime)
#   - pkg-config         : needed by Makefile pkg-config calls (gmp, zlib)
#   - libelfio-dev       : ELFIO header-only C++ library (mem_dump.cpp)
#   - opam               : OCaml package manager (for Sail)
#   - z3                 : SMT solver used by Sail's type checker
#   - curl / wget        : opam init downloads
#   - git                : submodule checkout
#   - ca-certificates    : TLS for git / opam
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        g++ \
        libgmp-dev \
        zlib1g-dev \
        pkg-config \
        opam \
        z3 \
        curl \
        wget \
        git \
        ca-certificates \
        rsync \
    && rm -rf /var/lib/apt/lists/*

# Replace libelfio-dev with this:
RUN git clone https://github.com/serge1/ELFIO.git /tmp/elfio && \
    cp -r /tmp/elfio/elfio /usr/local/include/ && \
    rm -rf /tmp/elfio

# ---------------------------------------------------------------------------
# Install Sail via opam
#
# opam must be initialised as a non-root user for sandboxing to work.
# We create a dedicated build user 'sail' for this purpose.
# ---------------------------------------------------------------------------
RUN useradd -m -s /bin/bash sail

# Switch to the sail user for the opam steps
USER sail
WORKDIR /home/sail

# Initialise opam without interactive setup; use the default compiler.
RUN opam init --auto-setup --disable-sandboxing --yes

# Install the sail package.  This may take several minutes on first run
# because it builds the OCaml compiler and all dependencies.
RUN opam install -y sail

# Make opam env available to subsequent RUN layers and the final CMD.
# We append the eval line to .bashrc AND write it to /home/sail/.opam_env
# so both interactive shells and the ENTRYPOINT can source it.
RUN echo 'eval $(opam env)' >> /home/sail/.bashrc \
    && opam env > /home/sail/.opam_env

# ---------------------------------------------------------------------------
# Switch back to root for final image setup
# ---------------------------------------------------------------------------
USER root

# ---------------------------------------------------------------------------
# ENTRYPOINT wrapper
#
# Ensures `sail` is on PATH for every command that runs inside the container
# by sourcing the opam environment before executing the user's command.
# ---------------------------------------------------------------------------
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# ---------------------------------------------------------------------------
# Default working directory – mount the repository here at runtime.
# e.g.  docker run --rm -v $(pwd):/work cheriot-sail make csim
# ---------------------------------------------------------------------------
WORKDIR /work

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["bash"]
