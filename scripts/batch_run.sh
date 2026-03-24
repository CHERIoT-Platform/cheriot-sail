#!/usr/bin/env bash
# =============================================================================
# batch_run.sh — Run all DII instruction files through the CHERIoT-Sail RVFI
#                simulator in batch and collect ELF memory dumps + RVFI traces.
#
# Usage:
#   ./scripts/batch_run.sh [options]
#
# Options:
#   -s, --sim <path>     Path to the RVFI simulator binary.
#                        Default: ./c_emulator/cheri_riscv_rvfi_RV32
#   -i, --instr-dir <d> Directory containing .txt instruction files.
#                        Default: ./dii_inputs
#   -o, --output-dir <d> Directory where ELF dumps and traces are written.
#                        Default: ./dii_outputs
#   -j, --jobs <n>       Number of parallel jobs. Default: 1 (sequential).
#   -h, --help           Show this message.
#
# Output layout (per instruction file <stem>.txt):
#   <output-dir>/<stem>/run.elf     — post-execution ELF memory dump
#   <output-dir>/<stem>/rvfi.bin    — binary RVFI V1 trace
#   <output-dir>/<stem>/sim.log     — simulator stderr log
#
# After the run, compare Sail traces against RTL using compare_rvfi.py:
#   python3 scripts/compare_rvfi.py \
#       --sail   dii_outputs/test_01/rvfi.bin \
#       --rtl    rtl_outputs/test_01/rvfi.bin
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SIM="./c_emulator/cheri_riscv_rvfi_RV32"
INSTR_DIR="./dii_inputs"
OUTPUT_DIR="./dii_outputs"
JOBS=1

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--sim)         SIM="$2";        shift 2 ;;
        -i|--instr-dir)   INSTR_DIR="$2";  shift 2 ;;
        -o|--output-dir)  OUTPUT_DIR="$2"; shift 2 ;;
        -j|--jobs)        JOBS="$2";       shift 2 ;;
        -h|--help)
            sed -n '2,/^# ===/{ /^# ===/d; s/^# \{0,1\}//p }' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ ! -x "$SIM" ]]; then
    echo "ERROR: simulator not found or not executable: $SIM" >&2
    echo "Build it first with:  make rvfi   (or  make ELFIO_DIR=/opt/elfio rvfi)" >&2
    exit 1
fi

if [[ ! -d "$INSTR_DIR" ]]; then
    echo "ERROR: instruction directory not found: $INSTR_DIR" >&2
    exit 1
fi

# Collect all .txt instruction files
mapfile -t INSTR_FILES < <(find "$INSTR_DIR" -maxdepth 1 -name '*.txt' | sort)

if [[ ${#INSTR_FILES[@]} -eq 0 ]]; then
    echo "No .txt instruction files found in $INSTR_DIR" >&2
    exit 1
fi

echo "==> Found ${#INSTR_FILES[@]} instruction file(s) in $INSTR_DIR"
echo "==> Simulator : $SIM"
echo "==> Output dir: $OUTPUT_DIR"
echo "==> Parallel  : $JOBS job(s)"
echo ""

mkdir -p "$OUTPUT_DIR"

# ---------------------------------------------------------------------------
# Worker function — process one instruction file
# ---------------------------------------------------------------------------
run_one() {
    local instr_file="$1"
    local stem
    stem="$(basename "$instr_file" .txt)"
    local run_dir="$OUTPUT_DIR/$stem"
    mkdir -p "$run_dir"

    local elf_out="$run_dir/run.elf"
    local rvfi_out="$run_dir/rvfi.bin"
    local log_out="$run_dir/sim.log"

    echo "[RUN] $stem"

    # Run the simulator.  All diagnostic output goes to sim.log.
    # Exit code is intentionally not fatal: a failed run still produces a
    # partial trace that the comparison script can flag as divergent.
    "$SIM" \
        --instr-file  "$instr_file" \
        --rvfi-output "$rvfi_out" \
        --elf-output  "$elf_out" \
        >"$log_out" 2>&1 \
        && echo "[OK ] $stem" \
        || echo "[ERR] $stem  (see $log_out)"
}

export -f run_one
export SIM OUTPUT_DIR

# ---------------------------------------------------------------------------
# Run — sequential or parallel
# ---------------------------------------------------------------------------
if command -v parallel &>/dev/null && [[ "$JOBS" -gt 1 ]]; then
    printf '%s\n' "${INSTR_FILES[@]}" \
        | parallel -j "$JOBS" run_one {}
else
    if [[ "$JOBS" -gt 1 ]]; then
        echo "WARN: 'parallel' not found; falling back to sequential execution." >&2
    fi
    for f in "${INSTR_FILES[@]}"; do
        run_one "$f"
    done
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "==> Batch complete.  Results in $OUTPUT_DIR"
echo ""
echo "Next step — compare Sail traces against RTL:"
echo "  python3 scripts/compare_rvfi.py \\"
echo "      --sail-dir  $OUTPUT_DIR \\"
echo "      --rtl-dir   <path-to-rtl-outputs>"
