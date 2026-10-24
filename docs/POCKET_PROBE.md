# PocketVRX offline snapshot probe

**Offline IQ diagnostic strips only, not live USB video. Moving live 160x120
grayscale at >=10 fps remains unmet.** The tool does not produce pixels or
frames. No board test was performed. Firmware and receiver defaults are unchanged.

## Record and inspect

The existing `tools/capture_iq_snapshot.py PORT capture.bin` owns the serial
port and requests one uppercase `I` snapshot. Do not run another console or
flight-log reader on that port. The existing command produces raw IQ and JSON,
not the console transcript expected by this offline tool. Alternatively save
the complete `IQSNAP_BEGIN/DATA/END` console response to `capture.txt`, using
one serial reader. Do not poll snapshots to construct a frame.

Run from the repository root. `capture.txt` must already contain exactly one
complete capture. The output directory must not exist; its parent must exist.
The probe uses the Python standard library and the inherited local parser.

```sh
python3 tools/pocket_probe.py capture.txt new-recording --sequence 0
python3 -m unittest discover -s test -p test_pocket_probe.py
```

`--sequence` defaults to 0 and accepts uint32 values. The probe does not open
a serial port. It writes these files and prints the JSON report:

| File | Content |
| --- | --- |
| `snapshot.pkiq` | One CRC-protected REPLAY IQ record |
| `dac6.bin` | 4095 nominal DAC6 codes, one byte per input pair |
| `known-mask.bin` | 4095 bytes marking agreement across initial states |
| `report.json` | Context, host timing, uncertainty and zero frame count |

The input limit is 1 MiB. The inherited capture parser checks format, sample
rate, exact 8190-byte length, contiguous offsets and FNV checksum. Context
includes firmware, frequency, gain and lane. Firmware does not supply an exact
capture timestamp, pair alignment, initial decoder state or context epoch.
Those properties cannot be recovered from a host arrival timestamp.

Each snapshot covers 204.75 us (about three horizontal lines), not a field.
`dac6.bin` contains one nominal DAC code per input pair, not grayscale pixels.
`known-mask.bin` is 255 only where all 64 possible starting P64 states produce
the same code; zero codes in that mask remain uncertain. Pair alignment is
still hypothetical even where the states agree. The strip has no line lock,
vertical lock, blanking removal, colour rejection or electrical DAC calibration.
No unrelated snapshots are stitched together. Host processing time in the
report is not USB bandwidth, device load or video frame rate.

## Experimental recording protocol (not a firmware wire protocol)

`snapshot.pkiq` is exactly one record. Little-endian header `<8sBBHIIQ32s>`:
magic `50 4b 49 51 00 a5 5a 01`, version 1, source byte, header size including
CRC (64), sequence uint32, payload size uint32 (8190 only), HOST receive/import
timestamp ns uint64, SHA256 of canonical sorted JSON context (default Python
JSON spacing). Header CRC32 follows, then IQ bytes, then payload CRC32. CRCs
use Python zlib/CRC-32. No device timestamp is implied. Source values are
1 TEST_PATTERN, 2 REPLAY, 3 LIVE_IQ_PROBE. Offline console imports always use
REPLAY. No LIVE_IQ_PROBE producer exists. Synthetic tests use TEST_PATTERN.
Parsers reject unknown versions/sources, extra bytes, truncation and damage.
Records are independent; callers must compare sequence and context to detect
gaps or changes. Sequence is caller-assigned, not a device drop counter.

## Deferred hardware work

No periodic firmware probe was added: the active TX-attached P64 demodulator
has no demodulated RAM stream. Reusing its validated finite snapshot command
avoids extra USB readers, buffering, task scheduling and live pacing changes.
Board work must measure snapshot refusal rate, console/flightlog ownership,
USB transfer time, observer/ISR load, RF continuity and impact on DAC output.
Continuous frame acquisition needs a separately proven source and bandwidth
budget; it cannot be inferred from a finite snapshot or synthetic fixture.

Before claiming the target, pass these gates in order:

1. Capture real moving-video IQ with exact acquisition context, device timing,
   pair alignment and discontinuity evidence. Prove a continuous source without
   pacing RF with USB or the CPU. Independent snapshots are not that source.
2. Prove sustained transfer, buffering and processing under receiver load.
   160x120 8-bit pixels at 10 fps require at least 192,000 payload bytes/s,
   before framing overhead. Raw IQ40 requires 40,000,000 bytes/s; a pixel-rate
   budget does not establish a raw-IQ USB path.
3. Establish line/field timing, active-image extraction and grayscale recovery.
   Measure delivered moving frames, drops, latency and receiver/DAC impact on
   the board. Host strip processing time is not delivered frame rate.

## Host validation scope

The prototype has seven tests in `test/test_pocket_probe.py`. Run the command
above and record its result separately from lint, format and security review.
The upstream `test/test_p64.py` check is blocked by missing `numba` in the
validation environment; it is not a passing check. No host check establishes
board behavior or the live-video target.

P64 decoding extends C5VRX by Twotoz and contributors' `test/test_p64.py`,
`research/p64_model.py` and `main/p64_tables.h`. The archived USB preview
protocol is a reference only: it consumes predecoded CVBS and is not this
receiver's RAM path. See [provenance](../PROVENANCE.md), the
[canonical source](https://github.com/Twotoz/C5VRX) and
[official website](https://twotoz.github.io/C5VRX/) (also hosts its Discord invite).
