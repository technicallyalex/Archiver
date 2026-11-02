# Metadata cache and importing

Media Pool imports use a persistent local SQLite index. It stores metadata only, not video, thumbnails, queue state or tested-quality results. Sources are never modified.

Windows default: `%LOCALAPPDATA%\Archiver\cache\metadata.sqlite`.

Linux: `$XDG_CACHE_HOME/archiver/metadata.sqlite`, falling back to `~/.cache/archiver/metadata.sqlite`. `ARCHIVER_CACHE_DIR` overrides the directory for tests or container deployment. SQLite may also create `-wal` and `-shm` companion files.

## Reuse and validity

Entries must match the normalized absolute source path, size, nanosecond modification time, FFprobe executable identity (path/size/modification time) and metadata schema revision. The database survives application restarts and versioned builds. Parser contract changes must increment `metadata_cache.SCHEMA`.

A cache hit still requests current filesystem information; deleted or inaccessible files are not served as online. Fresh reads recheck the source after inspection. Failed, interrupted or changing-file reads are not cached. Missing bitrate or quality metadata is never guessed. The complete current metadata contract includes audio streams, reported frame-rate string, timecode, orientation, aspect ratio, color transfer and recorded quality settings. UI identifiers are regenerated.

Corrupt, busy or unwritable cache storage does not prevent importing. Archiver inspects files directly and reports the cache problem in Import details. Close Archiver before deleting its cache folder; the next import rebuilds it. The index is bounded to approximately 50,000 entries, pruning older entries every 256 writes. Different path aliases can have separate entries. Content changes deliberately preserving size and modification time cannot be detected; no full-file hashing is performed.

## Inspection and concurrency

MP4, MOV, M4V, MKV and WebM first use normal FFprobe analysis bounded to a 1 MiB probe size and one second of media analysis. Required metadata is checked and incomplete or failed reads fall back to normal inspection. Other containers use normal inspection directly. This is not a one-second wall-clock limit or a header-only guarantee: container indexes can still require slow network seeks. The fast pass has eight seconds; elapsed time is subtracted from the existing 90-second import budget before fallback. Quality testing and final verification remain direct normal probes, bypassing this cache and the smaller analysis limits.

**Auto · Up to 16 at once** starts with four readers. It measures fresh-read throughput, tries eight and sixteen, and returns to a lower limit when an increase adds less than 10%. Timeouts and sustained stalls reduce admission. In-flight reads finish; no duplicate benchmark reads or throughput-driven cancellations occur. Cache hits do not inflate the fresh-probe score. Fixed 4/8/16 settings and serial import remain available. Media Pool thumbnails now share the existing two-worker thumbnail lane instead of starting unbounded competing FFmpeg reads.

The toast distinguishes cache hits, fresh inspections, slow reads, current reader limits and failed timeouts. Only two active filenames are shown, followed by a remaining count. Import details contain the cache path, fallback count and recent activity. Dismiss/background and completion fade behavior are preserved.

## Validation

All 162 tests pass. Dedicated checks cover persistence, size/time/tool/schema invalidation, concurrent writes, corrupt cache, deleted sources, cancellation, changing files, fallback and timeout budgets. Real bounded/full FFprobe comparisons preserve fields for multitrack H.264, HEVC HDR, AV1 and ProRes. Browser checks confirm repeat HTTP imports invoke no FFprobe calls, compact progress, and both themes across six viewport widths.

A local 48-file run measured 0.776 seconds cold (48 probes), 0.052 seconds warm (48 hits, zero probes), and 0.082 seconds after changing one timestamp (47 hits, one probe). This is a small local filesystem-cached benchmark, not a NAS throughput claim, and excludes remote-tree discovery and complete thumbnail loading. First imports still depend on storage/network performance.

Sources: [FFmpeg options](https://ffmpeg.org/ffmpeg-formats.html), [SQLite source](https://sqlite.org/src), [SQLite public-domain dedication](https://sqlite.org/copyright.html).
