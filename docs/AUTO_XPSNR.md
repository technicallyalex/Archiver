# Auto encoding: adjustable XPSNR target

Auto uses the bundled ab-av1 0.11.7 adaptive search with `--min-xpsnr` set to the user's target. The default is 38 dB; preview.25 adds a 30–50 dB slider and numeric entry. See [target guidance and research](XPSNR_TARGET_GUIDE.md). FFmpeg supplies encoding and its built-in XPSNR filter. FFprobe reads metadata. Python coordinates jobs, progress, result storage, and original-file protection; it does not implement a second CRF-search algorithm.

## User flow

1. Choose H.264, HEVC, or AV1.
2. Choose software or supported hardware encoding.
3. Choose Auto, set the target or leave it at 38 dB, then run a quality test.
4. ab-av1 finds a CRF/CQ configuration meeting the selected mean sample XPSNR target. Intermediate measurements and native CLI progress remain visible.
5. Apply the tested configuration. Each final output is checked for duration, aligned-frame sampled XPSNR, unchanged source identity before publication or replacement. Otherwise retain the original.

38 dB is a selected numerical quality target, not a percentage or a guarantee of visually lossless output. Auto no longer uses a VMAF target or advertises perceptual losslessness. XPSNR uses signal-error calculations with spatial/temporal perceptual weighting; it does not require selecting a trained 1080p or 4K VMAF model.

## Built-in search

Representative invocation:

```
ab-av1 crf-search -i input.mp4 --encoder av1_nvenc --preset p5 --min-xpsnr 38 --samples 3 --sample-duration 10s --cache false --crf-increment 1 --max-crf 51 --max-encoded-percent 10000 --pix-format yuv420p --xpsnr-fps 0 --xpsnr-pix-format yuv420p --enc enc_time_base=demux --keyint 10s --stdout-format json
```

Encoder/preset/quality bounds follow the selected method. Software uses CRF, NVIDIA uses CQ, and Intel uses its quality control. Values are not comparable across encoders.

FFmpeg has no `crf-search` command. Its `-crf`/`-cq` options control a single encode; its `xpsnr` filter measures a pair of streams. ab-av1 performs the adaptive encode/measure/search loop and returns the recommended setting and size/time estimates. `auto-encode` is not used, because analysis and full-file encoding are separate in Archiver.

Three distributed 10-second reference windows are reused within a search. Short sources covering the upstream 85% threshold use a full pass. No arbitrary time cutoff is introduced. Sample previews and optional FFmpeg vmafmotion analysis remain unchanged.

The high size ceiling permits a valid quality recommendation larger than the source. There is no minimum savings requirement. A quality-passing output can be smaller, the same size, or larger than the source. Predicted size changes remain informational; neither predicted nor actual savings block encoding.

## Timing and verification

`enc_time_base=demux` and passthrough frame timing preserve source timestamp precision in both test and final encodes. XPSNR analysis uses `--xpsnr-fps 0`, preventing ab-av1's default frame-rate override. Final verification checks matching dimensions, frame counts, and timestamps before measuring.

FFmpeg's XPSNR filter receives the reference first and the encoded stream second. Its minimum across color-plane average scores is used for each sampled region. Final verification uses the same distributed-window plan and requires the arithmetic mean of those region scores to meet the target saved in the recommendation, consistent with the mean-sample target used during search. It does not substitute a VMAF policy or require libvmaf. Motion analysis may still use vmafmotion if that optional filter is present.

## Compatibility and cache

Auto supports x264, x265, SVT-AV1, NVIDIA NVENC, and Intel Quick Sync when available. AMD Auto has no silent VMAF fallback; use software Auto, Quick estimate, or Manual for AMD configurations. ProRes retains its dedicated archival/editing flow.

Old VMAF recommendations are invalidated by the adapter/target fingerprint. Run a new test in preview.23. Historical reports retain their metric labels. Reports now identify `metric: xpsnr`, unit `dB`, and `targetScore: 38`, and record the native `xpsnr` measurements.

The bundled FFmpeg configuration must include the XPSNR filter. No model downloads or new external service are required. All analysis and reports remain local and source-side test directories retain their established behavior.

References: [ab-av1 XPSNR search](https://github.com/alexheretic/ab-av1/tree/v0.11.7#command-crf-search), [FFmpeg XPSNR filter](https://ffmpeg.org/ffmpeg-filters.html#xpsnr).


As of 0.3-preview.56, the legacy VMAF engine/scoring path and UI fallbacks have been removed. Auto search and final sampled output verification require XPSNR. FFmpeg vmafmotion remains an independent source-motion filter, not a perceptual quality score. About and FFmpeg settings explicitly describe startup PATH detection and optional executable-path overrides.


## Test depth

The Test Queue offers Fast, Balanced (default), and Extensive. These change coverage, not the XPSNR target, codec or encoder preset.

| Depth | Motion probes, depending on duration | Initial 8-second clips | Independent clips | Optional extra coverage passes |
| --- | --- | --- | --- | --- |
| Fast | 8–24 | 3 | 1 | 0 |
| Balanced | 12–48 | 6–8 | 3–4 | 1 |
| Extensive | 18–72 | 10–12 | 4 | 2 |

Very short files use the whole file; other short files use fewer nonoverlapping clips. All depths retain difficult-clip refinement and strict per-clip validation. A holdout used in a refinement search is replaced before final independent validation. Round budgets are 3, 4 and 5 respectively; there is no wall-clock timeout. Counts are engineering defaults, not validated confidence levels or runtime promises.

For similar recordings, test a representative file, review the result, then apply its settings to the group. For mixed footage, test each selected file; successful results receive their own settings and are added to the Encoding Queue. The in-app guide explains these choices and sample limitations. Each job retains its selected depth through queue recovery, and cache identities distinguish test depths.

Tests wait in the queue until Start tests is selected. Start tests when files are queued is off by default, independently of the Encoding Queue setting. Enabling it applies to future additions; it does not override an explicit pause or restart recovery. An already-running queue continues through newly added files. Watch-folder tests use the rule’s explicit automatic-start setting.


## Sample comparisons

After an individual sample evaluation finishes, the Test Queue can show the original source against that actual encoded clip. The first measured attempt meeting the target is retained for each sample. When the overall test finishes, the viewer selects the final recommended setting; the Result selector returns to each sample’s earlier target result.

Comparison playback does not resize or re-encode video. The original file is read directly, seeking to the sample’s first presentation timestamp. The encoded test clip is stream-copied into MP4 for browser playback. If the browser cannot decode either original codec, the comparison reports that limitation instead of substituting re-encoded video. Browser playback remains subject to codec and display support; XPSNR uses the exact validation pair.

The comparison is a directly draggable split view with a compact playback bar. Muted playback starts and loops when the comparison is visible. Manual pause survives polling, and offscreen/background playback is held. Sample and result selectors retain access to first target-meeting and final recommendation clips.

For a representative-file test, the picker uses selected Media Pool files when available, otherwise all loaded pool files. It defaults to the longest supported candidate and preserves a manual choice while that file remains available. Choosing a test file does not change the Media Pool selection. Per-file testing still requires an explicit pool selection.
