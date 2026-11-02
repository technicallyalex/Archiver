# Native previews and adaptive hardware encoding

Implemented in 0.3-preview.94; boundary/session hardening in 0.3-preview.95. No encoding quality target or codec defaults changed.

## Test previews

The browser plays each selected time range directly from the original recording through an authenticated, range-enabled endpoint. Native preview playback requires no sample re-encode or copy. The browser checks the container/codec type and attempts playback. An unsupported codec/container, decoding error or stalled native playback switches to the existing small H.264 proxy. Required fallbacks are warmed one at a time when the browser cannot use the source codec, then cached in the test folder's thumbnails directory;  it retains source frame timing. Unsupported-source proxy generation no longer blocks motion selection or the quality search.

Native playback uses explicit seek boundaries without temporal media fragments. Frame progress is monitored; stalled or excessively slow native playback switches to a proxy, and stalled proxy playback is reloaded with bounded backoff. Only the currently assessed sample may animate. Inactive, off-screen, completed and hidden-page previews pause and keep a still image. Inactive full-resolution native media is unloaded to release decoder resources; video elements remain stable across state polling. Recovery is bounded; a failed proxy leaves the poster available. A browser may advertise support but fail to decode a particular profile; actual playback failure therefore also triggers fallback.

Timeline JPEGs remain as before. Native playback still reads/decodes source frames on demand; zero preview-generation work does not mean zero playback cost. Slow native playback can fall back to a proxy.

## Encoding thumbnails

The main FFmpeg process maps its already-decoded source video to a second, tiny JPEG output at one frame per two source seconds. The primary output's encoding filters and parameters are unchanged. Files update atomically. The UI loads a new image before replacing the previous thumbnail and displays the current encoding position. No separate full decoder or repeated seek process is launched for these updates. Hidden/off-screen queue entries do not request refreshed images. The snapshot is a source-frame progress preview, not a preview of output compression artifacts or an exact representation of the encoder's internal buffered frame.

## Hardware parallelism

Automatic hardware parallelism is enabled by default and can be disabled in the Encoding Queue. Each comparable workload begins with one encode and a ten-second throughput baseline. If resources and sessions allow, admission increases by one. Further increases require at least an 8% aggregate throughput gain over the prior measured level. Workloads are grouped by encoder, dimensions, frame rates, rate-control mode and preset. A no-gain probe stops further parallel admission for that workload; active jobs finish rather than being killed and restarted. Consequently, adaptive probing cannot guarantee that every individual encode stays equally fast or that every temporary concurrency level improves performance.

On NVIDIA, optional nvidia-smi queries track encoder sessions, encoder/decoder/GPU utilization, free video memory and driver/model information. Conservative app ceilings are 12 for recognized current consumer RTX drivers, 8 for older recognized modern RTX drivers, and 2 when unknown. Existing sessions in other applications consume admission capacity. The driver remains authoritative: session/allocation failures back off to sequential retries, without publishing failed partial output. Intel/AMD have no equivalent portable session-count query in this implementation, so probing is bounded to two jobs and driver backoff is retained. These are application safety ceilings, not a universal hardware-capability claim.

Software encodes, copying/archival operations and jobs that still need a quality search remain serial. Hardware jobs with an already-bound test result may overlap their encode stages; final quality verifications are serialized. A waiting quality test drains the active encode batch before taking the exclusive media slot. Pausing prevents new admissions; stopping cancels active encodes; individual cancellation targets only that job's process. Output publication has a noncancelable commit point, so a completed output cannot be discarded mid-save. Slow output publication does not hold the global UI/progress lock.

## Validation

- 135 automated tests pass, plus JavaScript rendering/codec checks.
- Real browser: repeated native loops inside sample boundaries, one active preview, stable video elements, proxy fallback, and pause on hidden/completed states.
- Real queue: all individual thumbnails load, preserve DOM state across polling and stop refreshing when the queue is hidden. Parallelism control works in both themes and mobile layouts.
- Added JPEG branch: decoded primary output pixels match the baseline for a 90-frame software encode.
- NVIDIA H.264 benchmark on this workstation, 45 seconds of 1080p30 source, three runs per mode: median 4.565 seconds without snapshots and 4.570 seconds with snapshots (0.1%, within timing noise). This is not a universal performance estimate.
- Read-throttled integration fixture: adaptive scheduler reached three concurrent hardware jobs and completed all three. Separate real-process tests confirmed individual cancellation does not cancel its peer, thumbnails change, source files remain, and processes clean up.
- Bound test-result fixture: two hardware jobs reused results without repeating search; final verification did not overlap.

## References

- [NVIDIA support matrix](https://developer.nvidia.com/video-encode-decode-support-matrix), checked 2026-10-31. Its current consumer-session values differ from some older SDK documentation; do not hardcode an old session count as universal.
- [NVIDIA NVENC application note](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvenc-application-note/index.html): session capacity and aggregate encoder throughput are different limits.
- [HTML media specification](https://html.spec.whatwg.org/multipage/media.html): browser support checks are advisory and media loading can fail at runtime.
