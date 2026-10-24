#!/usr/bin/env python3
"""PocketVRX bounded offline IQ probe, not a frame or live USB video stream.

SPDX-License-Identifier: GPL-3.0-only
P64 reference adapted from C5VRX by Twotoz and contributors, test/test_p64.py.
See ../PROVENANCE.md for source revision and links.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import struct
import time
import zlib
from pathlib import Path

from capture_iq_snapshot import decode, record_line

MAGIC = b"PKIQ\x00\xa5\x5a\x01"
HEADER = struct.Struct("<8sBBHIIQ32s")
MAX_PAYLOAD = 8190
SOURCES = {"TEST_PATTERN": 1, "REPLAY": 2, "LIVE_IQ_PROBE": 3}
MAX_LOG = 1024 * 1024


def read_log(path):
    """Open once, reject special files without blocking, and bound the read."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("console log must be a regular file")
        data = stream.read(MAX_LOG + 1)
    if len(data) > MAX_LOG:
        raise ValueError("console log exceeds 1 MiB")
    return data.decode("ascii").splitlines()


def parse_context(header):
    """Keep complete whitespace-delimited values; never accept partial tokens."""
    context = {}
    for token in header.split()[1:]:
        match = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*)=([!-~]+)", token)
        if not match or "=" in match[2] or match[1] in context:
            raise ValueError("malformed or duplicate context")
        context[match[1]] = match[2]
    for key in ("gain", "lane", "freq_mhz", "fw", "fnv1a"):
        if key not in context:
            raise ValueError("missing context: " + key)
    for key in ("gain", "freq_mhz"):
        if not re.fullmatch(r"[0-9]+", context[key]):
            raise ValueError("invalid numeric context: " + key)
    if context["lane"] != "2":
        raise ValueError("unsupported lane")
    return context


def pack(raw, source, sequence, timestamp_ns, context):
    """Encode one complete finite snapshot; timestamp is HOST receive time."""
    if len(raw) != MAX_PAYLOAD or source not in SOURCES or len(context) != 32:
        raise ValueError("invalid snapshot/source/context")
    header = HEADER.pack(
        MAGIC,
        1,
        SOURCES[source],
        HEADER.size + 4,
        sequence,
        len(raw),
        timestamp_ns,
        context,
    )
    return (
        header
        + struct.pack("<I", zlib.crc32(header))
        + raw
        + struct.pack("<I", zlib.crc32(raw))
    )


def unpack(packet):
    """Strict bounded single-record parser. No magic-based payload scanning."""
    if len(packet) < HEADER.size + 8:
        raise ValueError("truncated header")
    header = packet[: HEADER.size]
    magic, version, source, size, seq, length, stamp, context = HEADER.unpack(header)
    if (
        magic != MAGIC
        or version != 1
        or source not in SOURCES.values()
        or size != HEADER.size + 4
        or length != MAX_PAYLOAD
    ):
        raise ValueError("unsupported header")
    if zlib.crc32(header) != struct.unpack_from("<I", packet, HEADER.size)[0]:
        raise ValueError("header CRC")
    if len(packet) != size + length + 4:
        raise ValueError("record length")
    raw = packet[size : size + length]
    if zlib.crc32(raw) != struct.unpack_from("<I", packet, size + length)[0]:
        raise ValueError("payload CRC")
    return raw, {
        "source": next(k for k, v in SOURCES.items() if v == source),
        "sequence": seq,
        "host_timestamp_ns": stamp,
        "context_sha256": context.hex(),
    }


def table_words():
    """Read and verify the inherited pinned P64 table without numpy."""
    text = (Path(__file__).resolve().parents[1] / "main/p64_tables.h").read_text()
    body = text.split("p64_table[1024] = {", 1)[1].split("}", 1)[0]
    table = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", body)]
    digest = hashlib.sha256(struct.pack("<1024H", *table)).hexdigest()
    if digest != "8027b82680c202738038435ce68eefb0145f58a112da773aefadefca0792482c":
        raise ValueError("P64 model changed; review probe")
    return table


def strip(raw):
    """Return nominal DAC6 and a mask where ALL 64 initial states agree.

    Pair alignment is a host hypothesis, not captured TX alignment. No
    convergence time is assumed. No sync/line/frame lock is inferred.
    """
    if len(raw) != MAX_PAYLOAD:
        raise ValueError("expected 8190 IQ bytes")
    table = table_words()
    states = list(range(64))
    codes, valid = bytearray(), bytearray()
    positions = (4, 5, 6, 7, 0, 1, 2, 3, 15, 11)
    for offset in range(0, len(raw), 2):
        word = raw[offset] | raw[offset + 1] << 8
        address = sum(
            ((word >> bit) & 1) << index for index, bit in enumerate(positions)
        )
        token = table[address] >> 12
        values = [table[state * 16 + token] for state in states]
        codes.append(values[0] & 63)
        valid.append(255 if len({value & 63 for value in values}) == 1 else 0)
        states = [(value >> 6) & 63 for value in values]
    return bytes(codes), bytes(valid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("console_log", type=Path)
    parser.add_argument("output", type=Path, help="new directory")
    parser.add_argument("--sequence", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.sequence <= 0xFFFFFFFF:
        parser.error("sequence outside uint32")
    # Console acquisition remains the existing single-owner uppercase I tool.
    start = time.perf_counter()
    lines = read_log(args.console_log)
    records = [record_line(line) for line in lines if "IQSNAP_" in line]
    if (
        not records
        or not records[0].startswith("IQSNAP_BEGIN ")
        or not records[-1].startswith("IQSNAP_END ")
        or sum(line.startswith("IQSNAP_BEGIN ") for line in records) != 1
        or sum(line.startswith("IQSNAP_END ") for line in records) != 1
        or any(not line.startswith("IQSNAP_DATA ") for line in records[1:-1])
    ):
        raise ValueError("expected exactly one complete capture")
    context = parse_context(records[0])
    raw, _ = decode(records)
    encoded = json.dumps(context, sort_keys=True).encode()
    packet = pack(
        raw, "REPLAY", args.sequence, time.time_ns(), hashlib.sha256(encoded).digest()
    )
    unpack(packet)
    codes, valid = strip(raw)
    elapsed = time.perf_counter() - start
    args.output.mkdir()  # Refuse overwrite of recordings.
    (args.output / "snapshot.pkiq").write_bytes(packet)
    (args.output / "dac6.bin").write_bytes(codes)
    (args.output / "known-mask.bin").write_bytes(valid)
    report = {
        "context": context,
        "source": "REPLAY",
        "iq_samples": len(raw),
        "contiguous_us": len(raw) / 40,
        "decode_seconds": elapsed,
        "initial_state_known": False,
        "pair_alignment_known": False,
        "state_independent_codes": valid.count(255),
        "frame_count": 0,
        "device_timestamp": None,
        "device_drop_count": None,
        "scope": "Offline DAC6 strip only; not pixels, frames or measured USB throughput",
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
