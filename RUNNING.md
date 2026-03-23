# Running the CHERIoT-Sail Simulator

This document explains how to check out the repository, build both simulator
variants, and run programs through the simulator — either from a pre-built ELF
file or by injecting raw instructions through the RVFI DII instruction-file
interface.

---

## Table of Contents

1. [Repository Branches](#1-repository-branches)
2. [Prerequisites](#2-prerequisites)
3. [Docker Build Environment](#3-docker-build-environment)
4. [Checking Out the Repository](#4-checking-out-the-repository)
5. [Building the Simulators](#5-building-the-simulators)
6. [Running from an ELF File](#6-running-from-an-elf-file)
7. [RVFI DII Mode — Overview](#7-rvfi-dii-mode--overview)
8. [Running from an Instruction File (`-f`)](#8-running-from-an-instruction-file--f)
9. [Running in Socket Mode (`-r`)](#9-running-in-socket-mode--r)
10. [Instruction File Format](#10-instruction-file-format)
11. [Example Instruction Files](#11-example-instruction-files)
12. [Memory Dump Output](#12-memory-dump-output)
13. [Re-executing from a Dumped ELF](#13-re-executing-from-a-dumped-elf)
14. [Full Command-Line Reference](#14-full-command-line-reference)

---

## 1. Repository Branches

The work described in this document lives on specific feature branches.

| Repository | Branch | Purpose |
|---|---|---|
| `cheriot-sail` (this repo) | `dii-read-from-file` | Adds `-f <instr_file>` mode and post-execution ELF memory dump to the RVFI DII simulator |
| `sail-riscv` (submodule) | `read-from-file` | Adds `riscv_sim.c` support for file-based DII, memory write-back, and `mem_dump_elf()` call sites |

---

## 2. Prerequisites

### Ubuntu / Debian (20.04 or later)

```bash
# Core build tools
sudo apt-get update
sudo apt-get install -y \
    build-essential git curl wget \
    pkg-config libgmp-dev zlib1g-dev \
    g++ libelfio-dev \
    opam z3

# Install Sail via opam
opam init --auto-setup
opam install sail
eval $(opam env)
```

> **Note on ELFIO:** The RVFI DII simulator uses
> [ELFIO](https://github.com/serge1/ELFIO) (header-only C++) to write the
> post-execution memory dump ELF.  If `libelfio-dev` is not in your distro's
> package manager you can install it manually:
>
> ```bash
> git clone https://github.com/serge1/ELFIO.git /opt/elfio
> # Then pass ELFIO_DIR when building (see §4)
> ```

### Verifying the Sail installation

```bash
eval $(opam env)
sail --version
# Should print: Sail 0.x (or similar)
```

---

## 3. Docker Build Environment

If you prefer not to install Sail and its dependencies on your host machine,
a self-contained Docker image is provided.  It installs every dependency
(GCC, G++, GMP, ELFIO, opam, Sail, Z3) and mounts the repository into the
container at `/work`, so build outputs appear in your local directory.

### Files

| File | Purpose |
|---|---|
| `Dockerfile` | Image definition — Ubuntu 22.04 base with all deps |
| `docker-entrypoint.sh` | Sources the opam environment before every command |
| `docker-run.sh` | Convenience wrapper: builds image on first run, then runs commands |

### One-time image build

```bash
# Build the image (takes 5–15 minutes on first run while Sail compiles)
docker build -t cheriot-sail .

# Or use the helper script — it builds automatically on first use:
./docker-run.sh --rebuild
```

### Running commands inside the container

The `docker-run.sh` script mounts the current directory as `/work` and runs
any arguments you give it as the container command.

```bash
# Interactive shell (useful for exploring or debugging)
./docker-run.sh

# Build the standard ELF simulator
./docker-run.sh make csim

# Build the RVFI DII simulator (RV32, default)
./docker-run.sh make rvfi

# Build the RVFI DII simulator (RV64)
./docker-run.sh make ARCH=RV64 rvfi

# Build both variants in one command
./docker-run.sh bash -c "make csim && make rvfi"

# Clean build artifacts
./docker-run.sh make clean

# Run an instruction file (binaries must already be built)
./docker-run.sh ./c_emulator/cheri_riscv_rvfi_RV32 \
    -f c_emulator/test_exc1.txt -v instr

# Re-run from a dump ELF
./docker-run.sh ./c_emulator/cheriot_sim memdump_000000.elf
```

### Running docker directly (without the helper script)

```bash
# Equivalent to ./docker-run.sh make rvfi
docker run --rm \
    -v "$(pwd):/work" \
    cheriot-sail \
    make rvfi

# Interactive shell
docker run --rm -it \
    -v "$(pwd):/work" \
    cheriot-sail \
    bash
```

### Rebuilding the image

```bash
# Force a rebuild (e.g. after updating the Dockerfile)
./docker-run.sh --rebuild make csim

# Or directly with docker
docker build --no-cache -t cheriot-sail .
```

### Notes

- Build outputs (`c_emulator/cheriot_sim`, `c_emulator/cheri_riscv_rvfi_*`,
  `generated_definitions/`) are written to your local directory via the
  volume mount and persist after the container exits.
- On Linux, `docker-run.sh` passes `--user $(id -u):$(id -g)` so generated
  files are owned by your user.  On macOS this flag is omitted (Docker
  Desktop handles ownership transparently).
- The `sail-riscv` submodule must be initialised before building inside the
  container:
  ```bash
  # On the host (not inside the container):
  git submodule update --init --recursive
  # Then run docker-run.sh make csim, etc.
  ```

---

## 4. Checking Out the Repository

### 3.1 Fresh clone onto the correct branches

```bash
# Clone the outer repository onto the feature branch
git clone \
    --branch dii-read-from-file \
    --recurse-submodules \
    https://github.com/CHERIoT-Platform/cheriot-sail.git
cd cheriot-sail
```

Because `--recurse-submodules` uses the commit pinned in the outer repo, the
`sail-riscv` submodule is already checked out to the right commit on the
`read-from-file` branch.  You can confirm this:

```bash
cd sail-riscv
git branch          # should show: * (HEAD detached at <hash>)  or  read-from-file
git log --oneline -5
cd ..
```

### 3.2 Updating an existing clone

```bash
# Outer repo
git fetch origin
git checkout dii-read-from-file
git pull

# Submodule — move to the read-from-file branch and pull
git submodule update --init --recursive
cd sail-riscv
git checkout read-from-file
git pull origin read-from-file
cd ..
```

### 3.3 Directory layout after checkout

```
cheriot-sail/
├── Makefile                    # Top-level build system
├── RUNNING.md                  # This document
├── src/                        # CHERIoT ISA extensions (Sail sources)
├── sail-riscv/                 # Submodule: base RISC-V Sail model
│   ├── model/                  # Sail language ISA specifications
│   │   └── rvfi_dii.sail       # RVFI DII packet definitions
│   └── c_emulator/             # C/C++ simulator harness
│       ├── riscv_sim.c         # Main simulator loop, CLI argument parsing
│       ├── mem_dump.h          # ELF memory dump interface
│       ├── mem_dump.cpp        # ELF dump implementation (ELFIO)
│       ├── mem.hpp / mem.cpp   # Sparse memory model (C++ port of PR#1549)
│       └── riscv_platform*.c/h # Platform support (HTIF, CLINT, UART)
├── c_emulator/                 # Build output directory
│   ├── cheriot_sim             # Standard simulator (alias for cheri_riscv_sim_RV32)
│   ├── cheri_riscv_sim_RV32    # Standard RV32 simulator
│   ├── cheri_riscv_sim_RV64    # Standard RV64 simulator
│   ├── cheri_riscv_rvfi_RV32   # RVFI DII RV32 simulator
│   └── cheri_riscv_rvfi_RV64   # RVFI DII RV64 simulator
└── generated_definitions/      # Sail compiler output (auto-generated)
```

---

## 5. Building the Simulators

All `make` commands are run from the repository root.

```bash
eval $(opam env)   # make sure sail is on PATH
```

### 4.1 Standard C simulator (ELF execution)

```bash
# Build for RV32 (default)
make csim
# Produces: c_emulator/cheriot_sim  (symlink to c_emulator/cheri_riscv_sim_RV32)

# Build for RV64 explicitly
make ARCH=RV64 c_emulator/cheri_riscv_sim_RV64
```

The standard simulator runs ELF files directly.  It does **not** have
the RVFI DII instruction injection or memory dump features.

### 4.2 RVFI DII simulator (instruction file / socket mode + memory dump)

```bash
# Build for RV32 (default architecture)
make ELFIO_DIR=/usr/include rvfi
# Produces: c_emulator/cheri_riscv_rvfi_RV32

# Build for RV64
make ARCH=RV64 ELFIO_DIR=/usr/include rvfi
# Produces: c_emulator/cheri_riscv_rvfi_RV64

# If you installed ELFIO manually to /opt/elfio:
make ELFIO_DIR=/opt/elfio rvfi
```

> **What `-DRVFI_DII` enables:** Compiling with this flag activates:
> - `-f <file>` — instruction file mode (inject raw instructions from a text file)
> - `-r <port>` — socket mode (receive instructions from an RVFI-DII client)
> - Post-execution ELF memory dump (`memdump_XXXXXX.elf`)

---

## 6. Running from an ELF File

This uses the **standard simulator** (`cheri_riscv_sim_*` or `cheriot_sim`).

```bash
# Basic run — loads and executes an ELF
./c_emulator/cheriot_sim path/to/program.elf

# Specify RAM size (default is 4 MB)
./c_emulator/cheriot_sim -z 64 path/to/program.elf

# Run with full instruction trace
./c_emulator/cheriot_sim -v instr path/to/program.elf

# Run with all tracing enabled
./c_emulator/cheriot_sim -v all path/to/program.elf

# Run and write trace to a file
./c_emulator/cheriot_sim --trace-output trace.log path/to/program.elf

# Limit execution to 10,000 instructions
./c_emulator/cheriot_sim -l 10000 path/to/program.elf

# Run multiple ELF files (first is the main file; extras are loaded
# into memory at their VMA without symbol scanning)
./c_emulator/cheriot_sim main.elf extra_rom.elf

# Disable boot ROM (useful for bare-metal programs that provide their
# own reset vector)
./c_emulator/cheriot_sim --no-boot-rom path/to/program.elf
```

### What the simulator prints on ELF load

```
Loading ELF ...
ELF Entry @ 0x80000000
```

Then the program runs.  Exit is signalled via the HTIF `tohost` memory-mapped
register; a zero write means success, non-zero means failure.

---

## 7. RVFI DII Mode — Overview

RVFI DII (RISC-V Formal Interface — Direct Instruction Injection) is a
protocol for injecting instructions into a running simulator one at a time
and receiving an execution trace packet back for each instruction.

The **CHERIoT RVFI DII simulator** (`cheri_riscv_rvfi_*`) supports two
input sources:

| Mode | Flag | Description |
|---|---|---|
| **File mode** | `-f <instr_file>` | Read instructions from a plain-text file; no socket needed |
| **Socket mode** | `-r <port>` | Listen on a TCP port; a DII client sends instruction packets |

In both modes the simulator:

1. Initialises the hart at `PC = 0x80000000` (rv_ram_base).
2. Executes each injected instruction.
3. After each instruction, makes an RVFI execution-trace packet available
   (sent over socket in socket mode; silently discarded in file mode unless
   you enable `-v rvfi`).
4. When all instructions have been consumed (file mode) or an
   `EndOfTrace` packet is received (socket mode), dumps the settled
   post-execution memory state to a file `memdump_XXXXXX.elf`.

### How instruction injection works

Unlike normal ELF execution the DII path **does not fetch instructions from
memory**.  Instead:

1. The simulator calls `zrvfi_set_instr_packet(instr)` to inject the raw
   32-bit encoding directly into the decode stage.
2. Before injection, the instruction bytes are also written to Sail's memory
   model at the current PC with `write_mem()`, so the post-execution memory
   dump captures the full instruction stream.
3. Each call to `zstep()` retires one instruction.

This means instructions can execute in any order, at any address, regardless
of what resides in memory — the PC advances naturally according to the RISC-V
architectural rules (branches, jumps, traps, `mret`, etc.).

---

## 8. Running from an Instruction File (`-f`)

This is the simplest RVFI DII entry point — no socket or client needed.

```bash
# Run the RV32 RVFI simulator with an instruction file
./c_emulator/cheri_riscv_rvfi_RV32 -f c_emulator/test_exc1.txt

# Enable RVFI packet tracing to see per-instruction execution details
./c_emulator/cheri_riscv_rvfi_RV32 -f c_emulator/test_exc1.txt -v rvfi

# Enable full tracing (registers, memory accesses, instructions)
./c_emulator/cheri_riscv_rvfi_RV32 -f c_emulator/test_exc1.txt -v all

# Set RAM size to 64 MB (default 4 MB)
./c_emulator/cheri_riscv_rvfi_RV32 -f c_emulator/test_exc1.txt -z 64

# Limit to 100 instructions (useful for debugging infinite loops)
./c_emulator/cheri_riscv_rvfi_RV32 -f c_emulator/test_exc1.txt -l 100

# Write trace to a file
./c_emulator/cheri_riscv_rvfi_RV32 -f c_emulator/test_exc1.txt \
    --trace-output execution.log -v all

# RV64 variant
./c_emulator/cheri_riscv_rvfi_RV64 -f my_test.txt
```

### Execution flow in file mode

```
1. Simulator starts, hart initialised at PC = 0x80000000
2. Instruction file is parsed into an in-memory buffer
3. For each instruction in the buffer:
   a. Write instruction bytes to memory at current PC
   b. Inject instruction into decode stage
   c. Execute one step (zstep)
   d. PC advances per architectural rules
      (may jump to 0x0 on trap, etc.)
4. Buffer exhausted → post-execution memory dump written:
      memdump_000000.elf
5. Simulator exits
```

### Expected output (example with `test_exc1.txt`)

```
mem_dump: wrote ELF32 with 2 PT_LOAD segment(s) to 'memdump_000000.elf' \
(entry=0x80000000, tohost=0x80001000)
```

The simulator is silent by default.  Add `-v instr` or `-v all` to see
per-instruction output.

---

## 9. Running in Socket Mode (`-r`)

In socket mode a DII client connects over TCP and sends instruction packets.
The simulator responds with an RVFI execution-trace packet after each
instruction.

```bash
# Start the simulator listening on port 8000
./c_emulator/cheri_riscv_rvfi_RV32 -r 8000

# With tracing enabled
./c_emulator/cheri_riscv_rvfi_RV32 -r 8000 -v rvfi

# RV64 on port 9000
./c_emulator/cheri_riscv_rvfi_RV64 -r 9000
```

The socket protocol:

1. **Client → Simulator:** 8-byte instruction packet
   ```
   Bits [63:56]  padding
   Bits [55:48]  rvfi_cmd   (0 = EndOfTrace / reset,  1 = Instruction,
                              'v' = set trace format version)
   Bits [47:32]  rvfi_time  (instruction counter)
   Bits [31: 0]  rvfi_insn  (32-bit instruction encoding; lower 16 bits
                              for RVC compressed instructions)
   ```

2. **Simulator → Client (v1):** 88-byte execution packet (V1 format)

3. **Simulator → Client (v2):** Variable-length execution packet with
   optional integer-data and memory-data extensions.

### Version negotiation

Send an `EndOfTrace` packet with `rvfi_insn = 0x56455253` ("VERS") to
trigger version negotiation.  The simulator replies with an 8-byte
`"version="` + `uint64_t version_number` response.  Then send a `'v'`
command packet with the desired version (1 or 2) in `rvfi_insn`.

---

## 10. Instruction File Format

The instruction file is a **plain-text** file.  The parser is intentionally
lenient:

- Each line is scanned for the **first occurrence of `0x`** (case-sensitive).
- Lines with no `0x` token are **silently ignored** (blank lines, comments,
  labels, assembler directives — all fine).
- The value after `0x` is read as a 32-bit hex integer (the raw instruction
  encoding).
- Anything after the hex value on the same line is ignored (inline comments
  after `#` or `//` are safe).

### Parsing rules

```
Line                              Parsed as
────────────────────────────────  ──────────────────────────────────────
0x00100073                        0x00100073  ✓
0x00100073   # ebreak             0x00100073  ✓  (comment ignored)
.4byte 0x47018113 # comment       0x47018113  ✓  (leading text ignored)
# This is a comment               (skipped)
                                  (skipped — blank line)
LABEL:                            (skipped — no 0x token)
addi x1, x0, 1                   (skipped — no 0x token)
```

### Instruction width

The parser reads every instruction as a 32-bit value.  At execution time the
simulator detects the width from the encoding:

```
bits[1:0] == 0b11  →  32-bit standard instruction  (4 bytes written to memory)
bits[1:0] != 0b11  →  16-bit compressed (RVC)       (2 bytes written to memory)
```

### Order of execution

Instructions are injected **in file order**.  The simulator does not care about
PC values — the PC advances according to the architectural rules (sequential
`+4`/`+2`, branches, traps, `mret`, etc.).  You are responsible for providing
instructions in the order you want them executed, including exception handler
instructions that will run when a trap fires.

---

## 11. Example Instruction Files

The repository ships three example files in `c_emulator/`.

---

### `c_emulator/test_exc1.txt` — Exception handler with `mret`

Demonstrates a trap to address `0x0` and return via `mret`.

```
# test_exc1.txt – Exception handler at address 0x0 with mret
#
# Scenario:
#   1. Normal code at 0x80000000: ebreak → M-mode trap → PC = 0x0
#   2. Exception handler at 0x0: fix mepc, mret → resume at 0x80000004
#   3. One more instruction, then falls into zero memory → clean stop
#
# DII injection order (instructions sent in this sequence):
#   [0] PC=0x80000000  ebreak           → trap fires, PC → 0x0
#   [1] PC=0x00000000  csrr x1, mepc    → handler: read faulting PC
#   [2] PC=0x00000004  addi x1, x1, 4  → advance past ebreak
#   [3] PC=0x00000008  csrw mepc, x1   → write updated mepc
#   [4] PC=0x0000000c  mret             → return, PC → 0x80000004
#   [5] PC=0x80000004  addi x2, x0, 42 → x2 = 42 (observable result)
#
# Memory layout captured in dump ELF:
#   [0x00000000..0x0000000f]  exception handler (csrr / addi / csrw / mret)
#   [0x80000000..0x80000007]  main code (ebreak / addi x2,x0,42)

# ── Main code at 0x80000000 ──────────────────────────────────────────────
0x00100073   # ebreak                   → trap to 0x0

# ── Exception handler at 0x0 ─────────────────────────────────────────────
0x341020F3   # csrr  x1, mepc           load faulting PC
0x00408093   # addi  x1, x1, 4         advance past ebreak
0x34109073   # csrw  mepc, x1          write updated return address
0x30200073   # mret                    return to 0x80000004

# ── Resumed at 0x80000004 ────────────────────────────────────────────────
0x02A00113   # addi  x2, x0, 42        x2 = 42
```

Run it:

```bash
./c_emulator/cheri_riscv_rvfi_RV32 -f c_emulator/test_exc1.txt -v instr
```

---

### `c_emulator/test_exc_overwrite.txt` — Handler overwrite

Demonstrates that a second trap can **overwrite** the exception handler
written by the first trap.  The dump ELF captures only the **final** memory
state.

```
# test_exc_overwrite.txt – Second exception overwrites handler at 0x0
#
# DII injection order:
#   [0]  PC=0x80000000  ebreak           → trap #1 → PC = 0x0
#   [1]  PC=0x00000000  addi x10,x0,100  handler #1: x10 = 100
#   [2]  PC=0x00000004  csrr x1, mepc
#   [3]  PC=0x00000008  addi x1, x1, 4
#   [4]  PC=0x0000000c  csrw mepc, x1
#   [5]  PC=0x00000010  mret             → return to 0x80000004
#   [6]  PC=0x80000004  ebreak           → trap #2 → PC = 0x0
#   [7]  PC=0x00000000  addi x10,x0,200  handler #2 OVERWRITES 0x0: x10 = 200
#   [8]  PC=0x00000004  csrr x1, mepc
#   [9]  PC=0x00000008  addi x1, x1, 4
#   [10] PC=0x0000000c  csrw mepc, x1
#   [11] PC=0x00000010  mret             → return to 0x80000008
#   [12] PC=0x80000008  addi x3, x0, 3  x3 = 3
#
# Dump ELF contains handler #2 (x10=200), NOT handler #1 (x10=100).
# Re-execution from dump: both ebreaks trigger handler #2.

# ── Main code ────────────────────────────────────────────────────────────
0x00100073   # ebreak  → trap #1

# ── Handler #1 at 0x0 ────────────────────────────────────────────────────
0x06400513   # addi x10, x0, 100       marker: first handler
0x341020F3   # csrr x1, mepc
0x00408093   # addi x1, x1, 4
0x34109073   # csrw mepc, x1
0x30200073   # mret

# ── Back at 0x80000004 ───────────────────────────────────────────────────
0x00100073   # ebreak  → trap #2

# ── Handler #2 at 0x0 (OVERWRITES handler #1) ────────────────────────────
0x0C800513   # addi x10, x0, 200       marker: second handler
0x341020F3   # csrr x1, mepc
0x00408093   # addi x1, x1, 4
0x34109073   # csrw mepc, x1
0x30200073   # mret

# ── Final instruction at 0x80000008 ──────────────────────────────────────
0x00300193   # addi x3, x0, 3          x3 = 3
```

---

### `c_emulator/back1.txt` — Backward branch (loop)

Tests that a backward branch correctly revisits earlier instructions.

---

### Writing your own instruction file

1. Assemble your program with a RISC-V assembler (e.g. `riscv64-unknown-elf-as`)
   and extract the `.text` section, **or** write encodings by hand using a
   RISC-V instruction reference.

2. Format the file as one instruction per line, `0x<hex_encoding>`, with
   optional comments:

   ```
   # Simple test: load immediate, add, store
   0x00500093   # addi x1, x0, 5       x1 = 5
   0x00A00113   # addi x2, x0, 10      x2 = 10
   0x002081B3   # add  x3, x1, x2      x3 = 15
   ```

3. Remember: instructions are injected **in file order**.  If your program
   uses a trap handler, the handler instructions must appear in the file at
   the point where the trap fires (i.e. immediately after the trapping
   instruction), not at the physical address where the handler lives.

---

## 12. Memory Dump Output

After all instructions in an instruction file have been executed (or when an
`EndOfTrace` packet is received in socket mode), the simulator writes a
post-execution ELF memory dump:

```
memdump_000000.elf   ← first run
memdump_000001.elf   ← second run (RVFI DII loops for multiple test traces)
memdump_000002.elf
...
```

The dump is written to the **current working directory**.

### What the dump contains

| ELF field | Value |
|---|---|
| ELF class | `ELFCLASS32` for RV32, `ELFCLASS64` for RV64 |
| Machine | `EM_RISCV` (243) |
| Entry point | `rv_ram_base` = `0x80000000` |
| Segments | One `PT_LOAD` per contiguous non-zero memory span |
| `.symtab` | Contains `tohost` symbol (HTIF exit address) |

The dump reflects **only the bytes that were actually written** during
execution.  Zero-filled pages that were never touched are omitted, keeping
the file compact.

Key point — the dump captures the **settled final state** including:
- Self-modifications by store instructions (e.g. a handler overwriting itself)
- Instruction bytes that were injected by DII (written at their PC locations)

### Diagnostic message

```
mem_dump: wrote ELF32 with 2 PT_LOAD segment(s) to 'memdump_000000.elf' \
(entry=0x80000000, tohost=0x80001000)
```

---

## 13. Re-executing from a Dumped ELF

The dump ELF is designed to be re-loaded and re-executed by the **standard**
simulator (no RVFI DII needed):

```bash
# Re-execute the dump using the standard simulator
./c_emulator/cheriot_sim c_emulator/memdump_000000.elf

# With instruction tracing
./c_emulator/cheriot_sim -v instr c_emulator/memdump_000000.elf
```

Re-execution will follow the exact same path as the original DII run because:
- The instruction bytes are physically present in memory at the correct
  addresses.
- The entry point is set to `0x80000000`.
- The `tohost` symbol lets the simulator detect program exit.

If the program had self-modifying code, re-execution reflects the **final**
(post-modification) memory state, not the original DII sequence — this is
expected and documented in `test_exc_overwrite.txt`.

---

## 14. Full Command-Line Reference

All flags apply to both the standard (`cheri_riscv_sim_*`) and RVFI DII
(`cheri_riscv_rvfi_*`) simulators unless marked **[RVFI only]**.

```
Usage: cheri_riscv_sim_RV32   [options] <elf_file> [<elf_file> ...]
       cheri_riscv_rvfi_RV32  [options] <elf_file> [<elf_file> ...]
       cheri_riscv_rvfi_RV32  [options] -r <port>           [RVFI only]
       cheri_riscv_rvfi_RV32  [options] -f <instr_file>     [RVFI only]
```

### Memory and hardware

| Short | Long | Argument | Default | Description |
|---|---|---|---|---|
| `-z` | `--ram-size` | `<MB>` | 4 | RAM size in megabytes |
| `-m` | `--enable-misaligned` | — | off | Allow misaligned memory accesses |
| `-M` | `--disable-misaligned` | — | off | Disallow misaligned memory accesses |
| `-d` | `--enable-dirty-update` | — | off | Enable hardware PTE dirty-bit updates |
| | `--pmp-count` | `0\|16\|64` | 0 | Number of PMP entries |
| | `--pmp-grain` | `<n>` | 0 | PMP grain size (G, where G < 64) |
| `-b` | `--device-tree-blob` | `<path>` | — | Load DTB file |

### ISA configuration

| Short | Long | Description |
|---|---|---|
| `-C` | `--disable-compressed` | Disable RVC compressed instructions |
| `-I` | `--disable-writable-misa` | Make the MISA CSR read-only |
| `-F` | `--disable-fdext` | Disable F and D floating-point extensions |
| `-N` | `--enable-next` | Enable the N user-interrupt extension |
| `-W` | — | Disable RVV vector instructions |
| `-x` | `--enable-zfinx` | Enable Zfinx (float ops use integer registers) |
| `-i` | `--mtval-has-illegal-inst-bits` | Write illegal instruction encoding to MTVAL |
| | `--boot-rom` | Enable boot ROM (default) |
| | `--no-boot-rom` | Disable boot ROM; execution starts directly at ELF entry |
| | `--enable-writable-fiom` | Enable writable FIOM bit in `menvcfg` |

### Execution control

| Short | Long | Argument | Description |
|---|---|---|---|
| `-l` | `--inst-limit` | `<n>` | Stop after `n` instructions |
| `-a` | `--report-arch` | — | Print `RV32` or `RV64` and exit |

### RVFI DII (requires `cheri_riscv_rvfi_*`)

| Short | Long | Argument | Description |
|---|---|---|---|
| `-f` | `--instr-file` | `<path>` | Run instruction file (file mode) |
| `-r` | `--rvfi-dii` | `<port>` | Listen on TCP port (socket mode) |

### Tracing and logging

| Short | Long | Argument | Description |
|---|---|---|---|
| `-v` | `--trace` | `[category]` | Enable trace output.  Categories: `instr`, `reg`, `mem`, `exception`, `platform`, `rvfi`, `all` |
| `-V` | `--no-trace` | `[category]` | Disable trace output (same categories) |
| | `--trace-output` | `<path>` | Write trace to file instead of stderr |
| `-t` | `--terminal-log` | `<path>` | Redirect UART/HTIF console output to file |
| `-p` | `--show-times` | — | Print initialisation and run-time statistics |

### Test infrastructure

| Short | Long | Argument | Description |
|---|---|---|---|
| `-T` | `--test-signature` | `<path>` | Write RISC-V test signature to file |
| `-g` | `--signature-granularity` | `<bytes>` | Signature word width (default: 4) |

### Getting help

```bash
./c_emulator/cheri_riscv_rvfi_RV32 --help
./c_emulator/cheriot_sim --help
```

---

## Quick-start Cheat Sheet

```bash
# ── Setup ────────────────────────────────────────────────────────────────
eval $(opam env)

# ── Checkout ─────────────────────────────────────────────────────────────
git clone --branch dii-read-from-file --recurse-submodules \
    https://github.com/CHERIoT-Platform/cheriot-sail.git
cd cheriot-sail

# ── Build ─────────────────────────────────────────────────────────────────
make csim                                  # standard simulator (ELF)
make ELFIO_DIR=/usr/include rvfi           # RVFI DII simulator

# ── Run ELF ───────────────────────────────────────────────────────────────
./c_emulator/cheriot_sim path/to/program.elf

# ── Run instruction file ──────────────────────────────────────────────────
./c_emulator/cheri_riscv_rvfi_RV32 -f c_emulator/test_exc1.txt

# ── Re-run from dump ──────────────────────────────────────────────────────
./c_emulator/cheriot_sim memdump_000000.elf

# ── Socket mode ───────────────────────────────────────────────────────────
./c_emulator/cheri_riscv_rvfi_RV32 -r 8000
```
