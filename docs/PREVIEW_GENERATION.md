# Preview generation and motion selection

Preview.26 removes a shared-lock bottleneck between timeline stills and active sample video previews. The 18-frame filmstrip and sample-card stills share two thumbnail worker slots; loop previews have a separate single worker slot. Each FFmpeg job retains its existing single-thread settings. Loop previews retain below-normal process priority on Windows.

Cached JPEGs and MP4s are served immediately without acquiring generation worker slots. Concurrent requests for the same uncached file are deduplicated with fixed-size striped locks, and cache files are published atomically. This allows at most three background FFmpeg preview jobs at once. Main quality-search/encoding queue scheduling is unchanged. Speed gains depend on decoding, storage, network seeking, and browser request scheduling; no universal multiplier is promised.

Loop previews remain silent source-timed H.264 proxies up to 10 seconds long and 320 pixels wide. No direct-source playback implementation is added. Direct browser playback could avoid proxy encoding for supported container/codec combinations, but it would still need byte-range delivery, subclip looping, and a fallback for unsupported sources. High-bitrate source playback and repeated network-file seeking also have costs. See [browser media format guidance](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats).

## Current motion behavior

Auto uses ab-av1's deterministic three distributed windows, or its full-pass behavior for short inputs. Before search, Archiver measures native-resolution/native-frame-timing vmafmotion on those windows. It reports mean, 95th percentile, peak, and comparisons within that set. The scores do not influence sample locations.

Random motion probes, a whole-file motion average, selection nearest that average, and replacement of low/high-motion windows have not been implemented. Motion-aware sample selection would require a separate preparation/integration change because the current native ab-av1 search selects its own distributed windows.

A possible future approach is bounded random probes spread across the recording, followed by selection covering typical and more demanding footage. The result would estimate motion distribution from probes, not establish a whole-file average. Selecting every window nearest the mean can miss difficult material. vmafmotion measures temporal changes rather than encoding difficulty, so it should not be the sole selection criterion.


## Preview priority (0.3-preview.32)
Timeline JPEG thumbnails are prepared first using two bounded workers and shared cache locks. Short motion probes must identify the final sample positions next; sample stills and looping proxies are then completed before the lossless search reference and CRF search. This preserves motion-aware sampling without generating unused provisional sample loops. Early timeline images stay attached across UI refreshes.

Loop proxies try H.264 NVENC, Quick Sync, then AMF when FFmpeg lists them. Runtime failures disable that hardware candidate for subsequent proxies in the session and fall back to software x264. Proxy commands preserve frame timing and use explicit standard input for console-free Windows launches. JPEG stills use software image encoding; hardware proxy encoding never changes the lossless quality-test reference. Cancellation remains available during preparation.


## Assessment activity and bounded probing (0.3-preview.33)
Preview playback is driven by explicit active sample indices. ab-av1's XPSNR start message activates the selected group and its measurement event clears it; preparation and candidate encoding leave it still. Because native search processes a joined reference, all selected clips belong to that assessment; Archiver does not invent a per-clip playback cursor. The UI identifies grouped scoring. Cancellation, errors, and final completion stop animation.

Motion probes use at most two independent single-threaded FFmpeg workers, each with its own cancellable Analyzer. CRF attempts remain adaptive and sequential. The native-resolution vmafmotion filter also runs in each reference input chain, so selected-clip motion statistics reuse the reference decode instead of requiring a separate 24-second pass. A retained 1440p sample benchmark measured nine probes at 12.95/12.82 seconds with one worker and 6.94/6.77 seconds with two, with identical scores; performance depends on hardware and storage.
