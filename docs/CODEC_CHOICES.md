# Output settings

1. Choose H.264/AVC, H.265/HEVC, AV1, or ProRes 422 HQ.
2. Choose software or hardware encoding and the GPU backend where applicable.
3. Choose Auto, Quick estimate, or Manual controls. Auto reveals a test button.

Auto now runs one search, not a suite of different quality levels. It asks ab-av1 to find the compression setting meeting --min-xpsnr 38 with --max-encoded-percent 10000 during analysis for the selected codec and method. There is no lossy quality-level selector. A successful test supplies one configuration. A target-quality configuration can be measured even when it is larger; output size does not block encoding. AMD uses Quick estimate or Manual, or software Auto; the ab-av1 integration does not support AMF.

The goal is XPSNR 38 dB without a minimum savings requirement. This numerical target does not guarantee visually lossless output. The existing final-output sampled quality checks, source-change detection, duration checks still apply. Other files are analyzed individually; the reference result does not bypass their validation.

Testing uses short distributed samples with no time cutoff. The filmstrip, active sample animation, estimated progress bar and open terminal output remain available. ProRes retains its separate lossy editing-intermediate workflow and does not run quality searches.
