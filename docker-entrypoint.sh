#!/bin/bash
# docker-entrypoint.sh
#
# Sources the opam environment (which puts `sail` on PATH) before running
# the user's command.  This is needed because opam writes its environment
# variables to the sail user's home directory and they must be eval-ed at
# runtime, not baked into the image layers.

set -e

# Load the opam environment that was saved during the image build.
# This sets OPAM_SWITCH_PREFIX, CAML_LD_LIBRARY_PATH, PATH, etc.
if [ -f /home/sail/.opam_env ]; then
    # shellcheck disable=SC1091
    source /home/sail/.opam_env
fi

exec "$@"
