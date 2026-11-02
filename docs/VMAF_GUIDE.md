# Reading VMAF scores

VMAF estimates visual similarity to a reference video, normally on a 0–100 scale with higher values closer to the reference. It is not a percentage of preserved quality or quality loss. These are rough engineering interpretations, not official pass/fail categories:

| Approximate score | Practical interpretation |
|---|---|
| 98–100 | Extremely close to the reference; a high score does not prove pixel-perfect or lossless encoding. |
| 95–98 | Very high quality; differences can still be visible in difficult scenes or close inspection. |
| 90–95 | High quality, with a greater chance of noticeable differences. |
| 80–90 | More substantial visible degradation becomes increasingly likely. |
| Below 80 | Increasingly strong degradation relative to the reference. |

No score universally guarantees perceptual equivalence. Results depend on model, content, viewing distance, resolution, display, and observer. Average scores can hide poor individual scenes. Samples can miss difficult content. VMAF 95 does not mean 5% quality loss. Even 100 does not establish byte identity or lossless preservation.

Current Archiver Auto uses XPSNR 38 dB with no minimum savings requirement. This guide describes the earlier VMAF NEG target of 97. This is a conservative application target, not a Netflix guarantee. It measures added degradation relative to the existing compressed source, not the uncompressed original master. Preview proxies are for viewing context only: they are not inputs to quality scoring.

References: [Netflix model documentation](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v0.md), [Netflix VMAF FAQ](https://github.com/Netflix/vmaf/blob/master/resource/doc/faq.md).
