#!/usr/bin/env python3
"""
compare_rvfi.py — Parse and compare binary RVFI V1 trace files.

Each RVFI V1 packet is 88 bytes (704 bits) laid out as follows
(little-endian, matching the Sail / TestRIG wire format):

  Offset  Size  Field
  ------  ----  -----
     0      1   rvfi_valid        (1 = valid instruction, 0 = halt)
     1      1   rvfi_order_lo     \  8-byte instruction order counter
     2      6   (order bytes 2-7)  /  (rvfi_order, little-endian uint64)
     8      4   rvfi_insn          32-bit instruction encoding
    12      1   rvfi_trap          trap flag
    13      1   rvfi_halt          halt flag
    14      1   rvfi_intr          interrupt flag
    15      1   (pad / mode)
    16      1   rvfi_rs1_addr
    17      1   rvfi_rs2_addr
    18      1   (pad)
    19      1   rvfi_rd_addr
    20      4   (pad)
    24      8   rvfi_rs1_rdata
    32      8   rvfi_rs2_rdata
    40      8   rvfi_rd_wdata
    48      8   rvfi_pc_rdata      PC before execution
    56      8   rvfi_pc_wdata      PC after  execution
    64      8   rvfi_mem_addr
    72      1   rvfi_mem_rmask
    73      1   rvfi_mem_wmask
    74      2   (pad)
    76      4   (pad)
    80      8   rvfi_mem_rdata
    (total: 88 bytes — remainder from rvfi_mem_wdata is appended by some
     implementations; we accept both 88- and 96-byte packets)

Usage (single file pair):
    python3 scripts/compare_rvfi.py \\
        --sail sail_outputs/test_01/rvfi.bin \\
        --rtl  rtl_outputs/test_01/rvfi.bin

Usage (directory pair — match by stem):
    python3 scripts/compare_rvfi.py \\
        --sail-dir sail_outputs/ \\
        --rtl-dir  rtl_outputs/
    # Compares sail_outputs/X/rvfi.bin against rtl_outputs/X/rvfi.bin
    # for every X that exists in both directories.

Options:
    --fields <f1,f2,...>   Only compare these fields (comma-separated).
    --ignore <f1,f2,...>   Skip these fields.
    --halt                 Include halt packets in comparison (default: skip).
    --summary              Print one pass/fail line per test, no per-packet detail.
    --json <file>          Write full diff report as JSON.
    --max-diffs <n>        Stop after n mismatches per file (default: 20).
"""

import argparse
import json
import os
import struct
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

# ---------------------------------------------------------------------------
# RVFI V1 packet layout (88-byte variant)
# ---------------------------------------------------------------------------
PACKET_SIZE_V1 = 88
PACKET_SIZE_V1_EXT = 96  # some implementations append rvfi_mem_wdata

RVFI_V1_FMT = "<"  # little-endian
RVFI_V1_FIELDS = [
    # (name,         offset, size, struct_char)
    ("valid",         0,  1, "B"),
    ("order",         1,  8, "Q"),   # overlaps valid byte — packed together
    ("insn",          8,  4, "I"),
    ("trap",         12,  1, "B"),
    ("halt",         13,  1, "B"),
    ("intr",         14,  1, "B"),
    ("mode",         15,  1, "B"),
    ("rs1_addr",     16,  1, "B"),
    ("rs2_addr",     17,  1, "B"),
    ("pad18",        18,  1, "B"),
    ("rd_addr",      19,  1, "B"),
    ("pad20",        20,  4, "I"),
    ("rs1_rdata",    24,  8, "Q"),
    ("rs2_rdata",    32,  8, "Q"),
    ("rd_wdata",     40,  8, "Q"),
    ("pc_rdata",     48,  8, "Q"),
    ("pc_wdata",     56,  8, "Q"),
    ("mem_addr",     64,  8, "Q"),
    ("mem_rmask",    72,  1, "B"),
    ("mem_wmask",    73,  1, "B"),
    ("pad74",        74,  2, "H"),
    ("pad76",        76,  4, "I"),
    ("mem_rdata",    80,  8, "Q"),
]
# Extended packet (96 bytes) appends:
RVFI_V1_FIELDS_EXT = [
    ("mem_wdata",    88,  8, "Q"),
]

# Fields skipped when comparing (padding / implementation-detail)
DEFAULT_IGNORE = {"pad18", "pad20", "pad74", "pad76", "mode"}

# Fields that carry meaningful architectural state (default comparison set)
ARCH_FIELDS = {
    "valid", "order", "insn", "trap", "halt", "intr",
    "rs1_addr", "rs2_addr", "rd_addr",
    "rs1_rdata", "rs2_rdata", "rd_wdata",
    "pc_rdata", "pc_wdata",
    "mem_addr", "mem_rmask", "mem_wmask", "mem_rdata",
}


@dataclass
class RvfiPacket:
    raw: bytes
    fields: Dict[str, int]
    index: int  # 0-based position in the trace file


def parse_packet(raw: bytes, index: int) -> RvfiPacket:
    """Decode one RVFI packet into a dict of field values."""
    fdict: Dict[str, int] = {}

    # The `valid` byte (offset 0) and the `order` uint64 (offset 1) overlap
    # in the 88-byte layout — the order counter occupies bytes 1-7 of the
    # packet and the valid flag is byte 0.
    fdict["valid"] = raw[0]
    # order: read 8 bytes starting at offset 0, mask off the valid byte
    order_bytes = bytes([0]) + raw[1:8]
    fdict["order"] = struct.unpack_from("<Q", order_bytes)[0]

    all_fields = RVFI_V1_FIELDS[2:]  # skip valid and order (handled above)
    if len(raw) >= PACKET_SIZE_V1_EXT:
        all_fields = all_fields + RVFI_V1_FIELDS_EXT

    for name, offset, size, fmt in all_fields:
        fdict[name] = struct.unpack_from("<" + fmt, raw, offset)[0]

    return RvfiPacket(raw=raw, fields=fdict, index=index)


def read_packets(path: Path) -> List[RvfiPacket]:
    """Read all RVFI packets from a binary trace file."""
    data = path.read_bytes()
    total = len(data)
    packets: List[RvfiPacket] = []
    i = 0
    idx = 0
    while i + PACKET_SIZE_V1 <= total:
        chunk_size = PACKET_SIZE_V1_EXT if i + PACKET_SIZE_V1_EXT <= total else PACKET_SIZE_V1
        raw = data[i:i + chunk_size]
        # Normalise to PACKET_SIZE_V1 if extended
        packets.append(parse_packet(raw, idx))
        i += chunk_size
        idx += 1
    if i != total:
        print(f"  WARN: {total - i} trailing bytes in {path} (ignored)")
    return packets


@dataclass
class FieldDiff:
    field: str
    sail_val: int
    rtl_val: int


@dataclass
class PacketDiff:
    packet_index: int
    sail_packet: Optional[Dict[str, int]]
    rtl_packet: Optional[Dict[str, int]]
    field_diffs: List[FieldDiff] = field(default_factory=list)
    missing_in_sail: bool = False
    missing_in_rtl: bool = False


def compare_traces(
    sail_packets: List[RvfiPacket],
    rtl_packets: List[RvfiPacket],
    compare_fields: Optional[List[str]] = None,
    ignore_fields: Optional[set] = None,
    include_halt: bool = False,
    max_diffs: int = 20,
) -> List[PacketDiff]:
    """
    Align and compare two RVFI packet streams.

    Returns a list of PacketDiff objects for every mismatch found.
    """
    if ignore_fields is None:
        ignore_fields = DEFAULT_IGNORE
    if compare_fields is None:
        compare_fields = sorted(ARCH_FIELDS - ignore_fields)
    else:
        compare_fields = [f for f in compare_fields if f not in ignore_fields]

    # Filter halt packets unless requested
    def keep(pkt: RvfiPacket) -> bool:
        if pkt.fields.get("halt") or not pkt.fields.get("valid"):
            return include_halt
        return True

    sail_kept = [p for p in sail_packets if keep(p)]
    rtl_kept  = [p for p in rtl_packets  if keep(p)]

    diffs: List[PacketDiff] = []
    n = max(len(sail_kept), len(rtl_kept))

    for i in range(n):
        if len(diffs) >= max_diffs:
            break

        sail_pkt = sail_kept[i] if i < len(sail_kept) else None
        rtl_pkt  = rtl_kept[i]  if i < len(rtl_kept)  else None

        if sail_pkt is None:
            diffs.append(PacketDiff(
                packet_index=i,
                sail_packet=None,
                rtl_packet=rtl_pkt.fields if rtl_pkt else None,
                missing_in_sail=True,
            ))
            continue
        if rtl_pkt is None:
            diffs.append(PacketDiff(
                packet_index=i,
                sail_packet=sail_pkt.fields,
                rtl_packet=None,
                missing_in_rtl=True,
            ))
            continue

        field_diffs = []
        for fname in compare_fields:
            sv = sail_pkt.fields.get(fname, 0)
            rv = rtl_pkt.fields.get(fname, 0)
            if sv != rv:
                field_diffs.append(FieldDiff(field=fname, sail_val=sv, rtl_val=rv))

        if field_diffs:
            diffs.append(PacketDiff(
                packet_index=i,
                sail_packet=sail_pkt.fields,
                rtl_packet=rtl_pkt.fields,
                field_diffs=field_diffs,
            ))

    return diffs


def format_val(name: str, val: int) -> str:
    """Pretty-print a field value (hex for addresses/data, decimal for small)."""
    wide = {"order", "rs1_rdata", "rs2_rdata", "rd_wdata",
            "pc_rdata", "pc_wdata", "mem_addr", "mem_rdata", "mem_wdata", "insn"}
    if name in wide:
        width = 16 if val > 0xFFFFFFFF else 8
        return f"0x{val:0{width}x}"
    return str(val)


def print_diff_report(
    diffs: List[PacketDiff],
    sail_total: int,
    rtl_total: int,
    label: str = "",
    summary: bool = False,
) -> bool:
    """Print a human-readable diff report.  Returns True if traces match."""
    prefix = f"[{label}] " if label else ""
    match = len(diffs) == 0

    if summary:
        status = "PASS" if match else f"FAIL ({len(diffs)} mismatch(es))"
        print(f"  {prefix}{status}  sail={sail_total} pkts  rtl={rtl_total} pkts")
        return match

    if match:
        print(f"  {prefix}PASS — {sail_total} packets compared, all match.")
        return True

    print(f"  {prefix}FAIL — {len(diffs)} mismatch(es)  "
          f"(sail={sail_total} pkts, rtl={rtl_total} pkts)")
    for d in diffs:
        print(f"\n  Packet #{d.packet_index}:")
        if d.missing_in_sail:
            print("    (no Sail packet — RTL has extra)")
            continue
        if d.missing_in_rtl:
            print("    (no RTL packet  — Sail has extra)")
            continue
        for fd in d.field_diffs:
            sv = format_val(fd.field, fd.sail_val)
            rv = format_val(fd.field, fd.rtl_val)
            print(f"    {fd.field:<18}  sail={sv}  rtl={rv}")
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def compare_pair(
    sail_path: Path,
    rtl_path: Path,
    args: argparse.Namespace,
    label: str = "",
) -> bool:
    """Compare one Sail/RTL trace pair.  Returns True on match."""
    if not sail_path.exists():
        print(f"  SKIP: sail trace not found: {sail_path}")
        return False
    if not rtl_path.exists():
        print(f"  SKIP: rtl trace not found:  {rtl_path}")
        return False

    sail_pkts = read_packets(sail_path)
    rtl_pkts  = read_packets(rtl_path)

    ignore = DEFAULT_IGNORE.copy()
    if args.ignore:
        ignore |= set(args.ignore.split(","))

    compare_fields = None
    if args.fields:
        compare_fields = args.fields.split(",")

    diffs = compare_traces(
        sail_pkts, rtl_pkts,
        compare_fields=compare_fields,
        ignore_fields=ignore,
        include_halt=args.halt,
        max_diffs=args.max_diffs,
    )

    ok = print_diff_report(diffs, len(sail_pkts), len(rtl_pkts),
                            label=label, summary=args.summary)

    if args.json_out:
        report = {
            "label": label,
            "sail_packets": len(sail_pkts),
            "rtl_packets": len(rtl_pkts),
            "pass": ok,
            "diffs": [
                {
                    "packet_index": d.packet_index,
                    "missing_in_sail": d.missing_in_sail,
                    "missing_in_rtl": d.missing_in_rtl,
                    "field_diffs": [
                        {"field": fd.field,
                         "sail": fd.sail_val,
                         "rtl": fd.rtl_val}
                        for fd in d.field_diffs
                    ],
                }
                for d in diffs
            ],
        }
        args.json_out.append(report)

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare binary RVFI V1 traces from Sail and RTL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Single-file mode
    parser.add_argument("--sail", type=Path, help="Sail RVFI trace file")
    parser.add_argument("--rtl",  type=Path, help="RTL  RVFI trace file")
    # Directory mode
    parser.add_argument("--sail-dir", type=Path,
                        help="Directory of Sail results (each sub-dir has rvfi.bin)")
    parser.add_argument("--rtl-dir",  type=Path,
                        help="Directory of RTL  results (each sub-dir has rvfi.bin)")
    # Filters
    parser.add_argument("--fields",  default="",
                        help="Comma-separated list of fields to compare")
    parser.add_argument("--ignore",  default="",
                        help="Comma-separated list of fields to ignore")
    parser.add_argument("--halt", action="store_true",
                        help="Include halt packets in comparison")
    # Output
    parser.add_argument("--summary", action="store_true",
                        help="One pass/fail line per test")
    parser.add_argument("--json",  dest="json_path", type=Path,
                        help="Write JSON diff report to this file")
    parser.add_argument("--max-diffs", type=int, default=20,
                        help="Stop after this many mismatches per trace (default 20)")

    args = parser.parse_args()
    args.json_out: Optional[List] = [] if args.json_path else None

    all_pass = True

    if args.sail and args.rtl:
        # Single-pair mode
        ok = compare_pair(args.sail, args.rtl, args,
                          label=args.sail.stem)
        all_pass = all_pass and ok

    elif args.sail_dir and args.rtl_dir:
        # Directory mode: walk sail-dir, match against rtl-dir
        sail_traces = sorted(args.sail_dir.glob("*/rvfi.bin"))
        if not sail_traces:
            print(f"No rvfi.bin files found under {args.sail_dir}")
            return 1
        print(f"==> Comparing {len(sail_traces)} trace(s)\n")
        for sail_trace in sail_traces:
            stem = sail_trace.parent.name
            rtl_trace = args.rtl_dir / stem / "rvfi.bin"
            ok = compare_pair(sail_trace, rtl_trace, args, label=stem)
            all_pass = all_pass and ok

    else:
        parser.print_help()
        return 1

    if args.json_path and args.json_out is not None:
        with open(args.json_path, "w") as f:
            json.dump(args.json_out, f, indent=2)
        print(f"\nJSON report written to {args.json_path}")

    print()
    if all_pass:
        print("==> All traces MATCH.")
        return 0
    else:
        print("==> MISMATCH detected — see details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
