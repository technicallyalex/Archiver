# Changelog

## 0.2 — 2026-10-20

- Live scan discovery, current-file details, recent activity, and cancellation.
- Optional four-file parallel metadata scanning and a large-directory notice.
- Queue pause, stop, resume, and clear-waiting controls.
- Completed encode size comparisons and output-directory shortcuts.
- Performance tab with CPU, RAM, storage/network throughput, NVIDIA GPU utilization, video encode/decode activity, and history graphs.
- DPI-aware native Windows directory picker.
- UI refinements and updated dependency documentation.

Performance monitoring uses psutil; GPU telemetry requires NVIDIA's installed nvidia-smi. Other GPUs show unavailable. Pause lets the active job finish; Stop cancels it and holds waiting jobs. No FFmpeg or FFprobe binaries are bundled.

## 0.1 — 2026-10-20

Initial release of Archiver, a local FFmpeg video library and transcoding queue.

- Directory scanning with FFprobe metadata and scrubbable thumbnails.
- Separate library and queue panes, light/dark themes, and native folder pickers.
- Software and hardware encoder selection, resolution and frame-rate controls.
- Source-based automatic bitrate, manual CRF/CQP, and custom bitrate controls.
- Multiple audio codecs and bitrates with all source audio tracks mapped.
- Output filename presets, custom suffixes, and numbered batch names.
- Manual or automatic queue starting and three progress display modes.
- Original-file preservation, replacement with Recycle Bin handling, and confirmed permanent deletion.

FFmpeg and FFprobe are supplied separately by users. See README.md for requirements and limitations.
