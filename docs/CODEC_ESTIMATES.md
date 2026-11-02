# Source-preset codec estimates, version 1

Source-based presets estimate bitrate from codec efficiency. They do not measure quality and cannot promise identical appearance. Codec specifications describe bitstreams; they do not prescribe a universal bitrate exchange rate between encoders.

## Formula

`target video bitrate = source video bitrate × output codec cost / input codec cost × preset budget × output/source pixel count × output/source frame rate`

100% uses a budget of 1.0, 75% uses 0.75, and 50% uses 0.50. These are estimated quality tiers implemented as bitrate budgets, not percentages of a perceptual score or retained detail. The codec adjustment is applied first. Optimized chooses the most efficient available codec for the selected method/container, with budget 1.0. It refuses a codec less efficient than the source instead of presenting an increase as optimization.

| Codec | Relative bitrate cost used by Archiver |
|---|---:|
| H.264 | 1.00 |
| HEVC | 0.65 |
| VP9 | 0.65 |
| AV1 | 0.50 |

These **application priors are engineering estimates**, not figures guaranteed by the linked sources. HEVC and VP9 are grouped as an approximate generation; no exact equivalence is asserted. Their 0.65 cost gives 35% savings against H.264 rather than assuming the best-case 50% discussed by publishers. Applying the AV1 overview's approximately 30% gain to this baseline would produce about 0.455; Archiver rounds upward to 0.50 to leave additional bitrate headroom. This yields approximately 23% saving from HEVC/VP9 to AV1. These deliberately simple priors need calibration against actual encoder/preset/content combinations.

Examples for a 40 Mbps H.264 source with AV1 selected: 100% estimates 20 Mbps; 75% estimates 15 Mbps; 50% estimates 10 Mbps. Keeping H.264 gives 40/30/20 Mbps. HEVC at 100% estimates 26 Mbps. Converting a 40 Mbps AV1 source back to H.264 estimates 80 Mbps at 100%, because a less efficient output codec needs a larger budget under this model. In general, if a pair's assumed *bitrate saving* is 25%, the multiplier is 0.75 and a 40 Mbps source becomes 30 Mbps. This differs from describing a compression ratio as 25% larger, which would imply division by 1.25.

## Primary evidence

- [ITU JCT-VC](https://www.itu.int/en/ITU-T/studygroups/2022-2024/16/video/Pages/jctvc.aspx): HEVC's development objective was approximately 50% less bitrate than the then-current AVC state of the art. This is a design/comparison context, not a promise for every source.
- [Google VP9 overview](https://developers.google.com/media/vp9): describes bitrate reductions as large as 50% compared with other known codecs. This is an upper-range claim, not a typical guaranteed saving.
- [AV1 authors' technical overview](https://arxiv.org/abs/2008.06091): reports more than 30% bitrate reduction compared with VP9 for the same decoded quality in its comparison context.
- [NTIA's HEVC comparison study](https://its.ntia.gov/publications/details?pub=2818): subjective comparisons support large HEVC gains in many, but not all, situations.
- [Meta's real-time AV1 deployment report](https://engineering.fb.com/2026/06/22/video-engineering/adopting-av1-for-real-time-communication-rtc-meta/): reports at least 20% savings against AVC under its specific product/device settings, illustrating why a universal conversion factor would be misleading.

## Limits and implementation

Hardware generation, encoder implementation, preset, source encoder efficiency, bitrate, resolution, grain, noise, animation, and motion can materially change the required bitrate. Re-encoding an already compressed source introduces additional loss. Archiver does not invent hardware-specific gains from a generic codec claim. CRF/CQP values cannot be derived reliably from a bitrate ratio and are not fabricated by this feature. Use Auto's measured search when those distinctions matter.

The server is the single source of truth: preview and queued jobs use the same estimator. Each job stores its estimator version, codec factor, preset budget, final bitrate ratio, and an explicit unmeasured flag. It uses each file's video-stream bitrate, preserves frame rate and resolution, checks encoder/container support, and rejects unknown codec pairs rather than assuming equivalence. The UI displays the estimated output bitrate and its percentage of input bitrate.


## Source support and file-size reporting (0.3-preview.101)

Automated (Estimate) has its own source validation, separate from measured quality tests. It accepts 8-bit SDR YUV 4:2:0 sources in both limited range (`yuv420p`) and full range (`yuvj420p`). Full-range samples are explicitly converted to limited-range output in this workflow, with output range signaling. A real encode regression checks that black and white appearance is preserved. This does not broaden the quality-test pipeline or enable unimplemented HDR/10-bit conversion.

The estimate must have a reported video bitrate, valid timing/dimensions and an available encoder. Missing source bitrate is not inferred from file size or a quality setting. Unsupported sources and target rates outside 0.1–1000 Mbps remain excluded. These limitations now have specific reason codes instead of a broad UI match on the word “test”.

The full output-size estimate uses the same resolved per-file target bitrate as queue construction, plus the chosen audio size estimate. For mixed selections, the API retains `bytes: null` and `reduction: null` for the unavailable complete total, and returns `partialBytes`, `estimatedCount` and per-file `issues`. The UI presents the known subset with “Partial · X of Y files”, suppresses a misleading complete-batch reduction percentage, and lists affected filenames and reasons in the tooltip. An incomplete estimate is not a license to encode unsupported files; queue validation still checks each input.

Validation: 166 Python tests, JavaScript regressions, full-range encode/range checks, and real browser complete/partial/missing-bitrate/unsupported-format cases across both themes and six viewport widths.
