# PocketVRX provenance

PocketVRX is a research fork of [C5VRX](https://github.com/Twotoz/C5VRX)
by Twotoz and the C5VRX contributors. It inherits firmware (`main/`), tests
(`test/`), research (`research/`), documentation (`docs/`), tools (`tools/`),
archives (`legacy/`), hardware/assets and web code.

Source revision: `78ff43ae551e48ad21e7f4c7da09491a900df8a5`.
Source: https://github.com/Twotoz/C5VRX/tree/78ff43ae551e48ad21e7f4c7da09491a900df8a5

Visit the [official C5VRX website](https://twotoz.github.io/C5VRX/) for the
original project and its Discord invite. PocketVRX is not an official C5VRX
release and is not endorsed by its authors.

## Fork preparation changes

Local changes add README attribution, this record, `tools/pocket_probe.py`,
`test/test_pocket_probe.py` and `docs/POCKET_PROBE.md`. The offline P64 strip
decoder adapts `test/test_p64.py` and reads the unchanged `main/p64_tables.h`;
the console parser is reused from `tools/capture_iq_snapshot.py`. All source
paths refer to the revision above. Modifications add bounded recording CRCs,
source/context labels, an unknown-initial-state mask and host-only reporting.
No firmware files were modified. No firmware or hardware validation has been
performed for PocketVRX. Outputs are offline IQ diagnostic strips only;
moving live 160x120 grayscale at >=10 fps remains unmet.
Inherited findings belong to the original project, not independent PocketVRX results.

## License and branding

The inherited software remains GPL-3.0-only. Preserve `LICENSE`, copyright,
author, SPDX and third-party notices. Attribution alone does not satisfy GPL
requirements; distribution must meet the applicable license requirements,
including corresponding-source obligations.

The separate terms in `assets/BRANDING.md` apply. Inherited C5VRX branding
assets remain as source/history, not as PocketVRX branding. Before publishing
a derivative website, firmware or product, review inherited names, logos and
visual identity and replace derivative-facing branding or obtain permission.
Keep accurate source attribution and original notices. No release or website
deployment is prepared by this documentation change.
