# ProRes profiles

Output codec ProRes exposes a separate profile selector: Automatic (default), 422 Proxy, 422 LT, 422, 422 HQ, 4444, and 4444 XQ. Automatic is metadata-guided per file: 8-bit 4:2:0/4:2:2 selects 422, 10-bit 4:2:0/4:2:2 selects 422 HQ, and 4:4:4, RGB or alpha sources select 4444. Prefer higher fidelity changes ordinary 8-bit Automatic selections to HQ; it does not override explicit selections or silently choose XQ.

The UI aggregates mixed selections and explains up to three examples. Estimates use Apple's reference profile data rates scaled by pixel count and frame rate, times source duration. They are rough video-only planning estimates, not predicted measurements; PCM audio adds space. Resolution alone never upgrades a profile. Higher profiles cannot recover color information missing from a 4:2:0 source.

Each queued file resolves its own profile. Output is MOV through FFmpeg prores_ks, original geometry/timing, PCM24 audio, and 10-bit 4:2:2 or 4:4:4 pixels. Alpha sources require 4444 or XQ; incompatible manual choices fail before queueing. RGB conversion explicitly uses full-range input, limited-range YUV output and a BT.709 matrix for HD or BT.601 for SD; it is a color conversion, not a pixel-lossless operation. HDR, 12-bit and unknown source formats remain rejected. The installed encoder accepts 10-bit color input formats, so selecting 4444 does not promise 12-bit source precision preservation.

All mapped streams are retained or the mux fails; originals remain preserved. Verification checks actual profile, chroma family, alpha presence, geometry/duration, and decode success. Native tests cover every profile, RGB conversion, and non-opaque alpha output. Recommendations are application defaults rather than measured perceptual-quality guarantees.

References: [Apple ProRes white paper](https://www.apple.com/final-cut-pro/docs/Apple_ProRes.pdf), [FFmpeg codec documentation](https://ffmpeg.org/ffmpeg-codecs.html).
