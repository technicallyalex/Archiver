# Media Pool import concurrency

As of 0.3-preview.99, parallel import defaults to Auto (up to 16), with adaptive admission and a persistent local metadata cache. Fixed 4, 8 and 16 options remain; disabling parallel import uses one. Omitted API worker options select Auto, while explicit numeric values select fixed concurrency. See [Metadata cache and importing](METADATA_CACHE.md) for the current behavior and validation. Encoding concurrency is unchanged.

A previous read-only benchmark on 64 existing NAS videos ran each worker count three times in shuffled order. Median FFprobe metadata times were 2.475 seconds (4), 1.399 (8), 0.698 (16), and 0.679 (32). Every source path, duration, codec, dimensions, and file size matched. Sixteen workers reduced this metadata stage by about 72% versus four; 32 offered only about 3% more. A preliminary 32-file run also favored 16 over 4 and 8.

These timings include FFprobe process startup and metadata parsing, but exclude directory discovery and UI thumbnail creation. Repeated rounds benefit from filesystem and NAS caching, so these are not cold-storage or full end-to-end import guarantees. Slower drives or competing workloads may favor 4 or 8. Stop scanning still cancels active probes and preserves successfully imported files.
