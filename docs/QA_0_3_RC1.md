# Archiver 0.3 Release Candidate 1 — QA report

Date: 2026-11-02. Build: 0.3.0-rc.1. Platform: Windows 11 x64, Microsoft Edge.

## Results

No release-blocking failures were found in the checks below.

- **285 Python regression tests passed.** Coverage includes import/cache/exclusions, codecs and proxies, output naming and collisions, estimates, metadata/audio preservation, tool setup, storage checks, recoverable queues, reports, watch folders, presets, notification history, timestamp alignment, motion selection, adaptive searches and comparison preparation.
- **All nine JavaScript suites passed.** Coverage includes multi-select filters, queue rendering, dropdown labels, sample playback recovery, terminal formatting, grouped notifications, sample-result selection and comparison playback.
- **36 browser layout cases passed:** all three workspaces in both themes at six viewport widths, with no horizontal overflow. Sidebar placement, compact import controls and dropdown persistence across refreshes passed.
- Browser interaction checks passed for Watch folders placement, active import toast, repeated pointer/keyboard notification toggles and the version-prefilled Feedback link. No uncaught JavaScript exceptions were observed in these runs.
- Packaged test-queue checks passed: default enqueue waits, manual start runs, opt-in auto-start runs, explicit pause is respected, and held tests do not block encodes.
- Packaged runtime self-test passed: bundled Python, native terminal capture, folder picker runtime, SQLite cache, web assets and ab-av1 0.11.7.
- Packaged windowless application encoded a generated source, verified full decoding and produced a report. After restart, completed output was retained and pending work was offered for recovery and restored paused.
- Packaged AV1 NVENC quality search completed. All nine validation clips exceeded the 38 dB target (38.58–39.82 dB); all nine had motion values. Nine comparison attempts were retained. Comparison preparation used the actual encoded video without re-encoding.
- Distribution checks confirm third-party notices are included and FFmpeg/FFprobe executables are excluded. Existing builds remain available for rollback.

The first build self-check timed out inside the restricted execution environment. Repeating the build and runtime checks with normal local process permissions passed. This was not reproduced in the packaged application.

## Limits and follow-up testing

This is a release candidate, not a certification of every hardware or media combination. Intel Quick Sync and AMD AMF hardware, physical network disconnects, truly full disks, Linux and Docker were not exercised on this workstation. Related error-handling paths have automated tests. Browser-native comparison playback depends on browser codec support; comparison media is never replaced by a lower-quality proxy.

Quality-search duration depends strongly on resolution, frame rate, encoder and source complexity. The generated-fixture pass does not establish a maximum runtime or guarantee quality for every full recording. Independent sample validation reduces sampling risk but cannot examine every frame outside the selected clips.

The Python suite emitted pywinpty socket ResourceWarnings during terminal tests; all tests completed. Longer-running handle/resource monitoring remains useful during RC testing. Windows may warn about the unsigned executable.

## Reporting feedback

Use **Feedback** in the header. It opens the repository issue form with version and browser details. Describe the workflow, expected result and actual result; attach relevant logs or screenshots after reviewing them for personal paths. No report is submitted automatically.
