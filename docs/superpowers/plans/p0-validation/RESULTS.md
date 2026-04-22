# P0 Validation Results

*Fill this out after running the P0 scripts on your VPS. This is the closeout artifact for Phase 0.*

**Date run:** _(YYYY-MM-DD)_
**VPS:** _(provider, region, kernel — e.g. Hetzner CX32, Helsinki, Ubuntu 22.04 kernel 5.15.0-xx)_
**Proxy vendor / type:** _(e.g. Bright Data residential SOCKS5 — don't record credentials here)_

## Success criteria (from design spec §17)

- [ ] One Redroid + sidecar pair spawned via `spawn-pair.sh`
- [ ] In-Android `nc`-over-HTTP to ifconfig.me returns the configured proxy's exit IP
- [ ] Stopping redsocks results in zero egress (test-no-leak.sh green)
- [ ] Desktop scrcpy connects and displays Android 11 home screen

## Recorded IPs

- Host public IP:   `_______________`
- Android-seen IP:  `_______________`  (should equal proxy exit IP, NOT host IP)

## Timings

- `prepare-vps.sh` runtime: `___ s`
- Sidecar reached healthy: `___ s` after spawn
- Android `boot_completed`: `___ s` after Redroid spawn

## Issues encountered

*(note any deviations, workarounds, proxy quirks — or "none")*

## Artifacts

*(drop screenshots in this directory: scrcpy-home.png, ip-mismatch-terminal.png)*

## Ready for P1?

- [ ] Yes, proceed to writing P1 plan
- [ ] No — blockers need addressing first (list them above)
