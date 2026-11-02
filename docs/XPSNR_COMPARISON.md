# XPSNR versus VMAF: aligned Battlefield 3 samples

Local experiment, 2026-10-30. This is one 1440p gameplay recording, not a cross-resolution validation or a subjective viewing study. The default remains VMAF NEG target 97. No original media or saved NAS report was modified.

## Alignment correction

FFmpeg’s default encoder time base rounded variable-rate frame timestamps to an average-rate grid. On the retained sample starting at 113 seconds, 14 of 598 encoded timestamps selected a different reference frame under nearest-timestamp synchronization. Identical frame counts alone did not prevent this.

Auto sample encodes now pass `--enc enc_time_base=demux` to ab-av1. Final Auto output uses the matching `-enc_time_base demux`; both retain passthrough frame timing. This preserves the copied reference timestamps instead of replacing them with a fixed frame-rate sequence. Older recommendations are invalidated by sampling fingerprint version 3.

Every one of the 12 retained-sample encodes below has exactly 598 decoded frames and zero normalized timestamp error against its reference at FFprobe’s reported precision. The three sample starts are 51, 113, and 175 seconds. Their compressed H.264 reference files are unchanged. Additional automated output checks cover fractional and variable timing with x264, x265, and SVT-AV1.

## Matched-encode scoring comparison

Environment: RTX 5080 / NVIDIA driver 621.01, FFmpeg 9.0.1, ab-av1 0.11.7. AV1 NVENC p5, GOP 598, yuv420p, native 2560×1440 and source frame timing. VMAF uses vmaf_v0.6.1neg without scaling and 8 metric threads. XPSNR uses the minimum of its per-plane averages, matching ab-av1. Each metric processes the exact same encoded file. XPSNR must take the reference first because its error weighting is asymmetric; VMAF takes the distorted input first.

An initial standalone XPSNR pass used reversed inputs and was discarded. Corrected XPSNR scores/times below were collected in a separate reference-first batch after the native searches, which already used the correct order. VMAF scores/times come from the initial sequential benchmark batch. No search and scoring benchmark ran concurrently.

Times are wall time for a separate FFmpeg scoring process, including software decoding of reference and encoded sample. They exclude encoding and diagnostic FFprobe checks. No performance claim about other hardware, resolutions, codecs, or in-memory implementations follows from this measurement.

| CQ | Mean VMAF | Mean XPSNR, dB | Encoded sample bytes / reference bytes |
|---:|---:|---:|---:|
| 21 | 99.399 | 44.075 | 148.69% |
| 22 | 99.260 | 43.595 | 134.88% |
| 23 | 94.959 | 40.015 | 60.39% |
| 30 | 94.833 | 39.838 | 55.59% |

The means above average the three per-sample scores. Percentages are ratios of retained sample file sizes, not measured full-file results. Both metrics retain the CQ 22–23 cliff after alignment is corrected.

| Metric | Total scoring time, 12 clips | Median per clip |
|---|---:|---:|
| VMAF | 70.86 s | 5.83 s |
| XPSNR | 65.35 s | 5.38 s |

The timed 12-clip comparison covers CQ 21, 22, 23, and 30 on each of the three retained samples. VMAF was multithreaded; these are actual pipeline timings, not isolated algorithm-complexity measurements. Corrected XPSNR scoring used about 8% less wall time in this pass. Separate timing batches and a single pass limit the precision of that comparison.

## Individual sample scores

| Start | CQ | VMAF | XPSNR, dB |
|---:|---:|---:|---:|
| 51 s | 21 | 99.731 | 44.944 |
| 51 s | 22 | 99.659 | 44.457 |
| 51 s | 23 | 97.530 | 41.067 |
| 51 s | 30 | 97.481 | 40.879 |
| 113 s | 21 | 99.125 | 43.519 |
| 113 s | 22 | 98.978 | 43.076 |
| 113 s | 23 | 93.986 | 39.697 |
| 113 s | 30 | 93.669 | 39.426 |
| 175 s | 21 | 99.340 | 43.763 |
| 175 s | 22 | 99.142 | 43.252 |
| 175 s | 23 | 93.360 | 39.280 |
| 175 s | 30 | 93.349 | 39.209 |

## Adaptive search comparison

Diagnostic searches use the original input and the same three copied windows, corrected encoder time base, no global cache, native metric frame timing (`--vmaf-fps 0 --xpsnr-fps 0`), a high 10000% size ceiling, and `--thorough` for both metrics. Production search tolerance is unchanged. XPSNR targets 40 and 42 dB are exploratory thresholds, not validated equivalents of VMAF 95 or 97. Search time includes sampling, repeated encoding, and scoring; searches run sequentially after the matched-file benchmark.

| Search target | CQ | VMAF at that CQ | XPSNR at that CQ, dB | Predicted output / source | Attempts | Search wall time |
|---|---:|---:|---:|---:|---:|---:|
| VMAF 97 | 22 | 99.260 | 43.595 | 134.88% | 6 | 152.60 s |
| XPSNR 40 | 26 | 94.968 | 40.007 | 59.62% | 6 | 152.42 s |
| XPSNR 42 | 22 | 99.260 | 43.595 | 134.88% | 5 | 130.86 s |
| VMAF 95 | 22 | 99.260 | 43.595 | 134.88% | 10 | 241.02 s |

Cross-metric scores in this search table are measured adaptive-search events at the same CQ/encoder/preset on the same three source windows. They come from separate native search runs. The matched-file table above compares both metrics on the exact same retained output files.

## Interpretation

The alignment correction removes the observed DTS warnings in all 12 corrected encode logs. A decoded-frame MD5 comparison of the old and corrected CQ 23 output at 113 seconds confirms identical pixels and frame order across all 598 frames. The improved VMAF score therefore reflects corrected frame correspondence, not an improved encode. All 75 automated tests pass, including the new real-FFmpeg timing regression.

At the tested targets, VMAF 95/97 and XPSNR 42 all recommend CQ 22 with approximately 35% predicted enlargement. XPSNR 40 recommends CQ 26 with approximately 40% predicted reduction; that configuration measures VMAF 94.968. The XPSNR 40 and VMAF 97 searches both took approximately 153 seconds. VMAF 95 took longer because the smaller CQ 23–30 candidates sit just below the target and the thorough search checks more neighboring settings. Search duration depends on the quality curve and stopping behavior as well as metric cost.

Scores are not quality-retention percentages, and XPSNR and VMAF thresholds are not interchangeable. These measurements establish numerical behavior on one source, not perceived transparency across resolutions. The default metric and target remain unchanged pending broader and subjective validation.

Raw local data: `.test-temp/aligned-benchmark/results.json`, `.test-temp/aligned-searches/results.json`, their adjacent command/event/log files, and retained diagnostic media.

References: [FFmpeg encoder time base](https://ffmpeg.org/ffmpeg.html), [FFmpeg XPSNR](https://ffmpeg.org/ffmpeg-filters.html#xpsnr), [ab-av1 XPSNR search](https://github.com/alexheretic/ab-av1/tree/v0.11.7#command-crf-search).
