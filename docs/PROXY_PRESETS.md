# Proxy generation

Select **Quality mode → Proxy**. The dedicated panel places Quality mode first, then Video codec, proxy resolution and encoding method. It supports ProRes 422 Proxy, H.264, H.265 and AV1. Returning to another quality mode restores the normal output controls.

## Output settings

- Half: divides width and height by two; UHD 3840 × 2160 becomes 1920 × 1080.
- Quarter: divides both dimensions by four; UHD becomes 960 × 540.
- ProRes uses profile-controlled variable bitrate, approximately 45 Mbps at 1080p/29.97, scaled by output pixel count and FPS.
- H.264/H.265/AV1 use a target of 8 Mbps at 1080p/29.97, scaled by output pixel count and FPS, with a 0.5 Mbps minimum. This is an application preset, not a measured quality guarantee or an editor-mandated bitrate.
- H.264/H.265 use short GOPs, no B-frames and fast encoder presets. SVT-AV1 uses low-delay prediction, preset 8 and its required CBR mode; very small outputs fall back to libaom-AV1 when available. Hardware encoding uses the selected compatible encoder.
- ProRes, H.264 and H.265 use MOV. AV1 uses MP4 because FFmpeg does not support it in MOV. Audio remains 24-bit PCM with original channels/sample rates; modern FFmpeg is needed for PCM in MP4.
- These codecs do not have identical NLE support. ProRes and H.264 are safer starting points for editing; check editor/hardware support before choosing H.265 or AV1.

## Save locations

- **In subfolder**: `Proxies/Half` or `Proxies/Quarter` beside each source, with `H264`, `HEVC` or `AV1` beneath it for those codecs. Retains the source basename.
- **Next to originals**: saves `{original}_proxy.mov` (AV1: `.mp4`) beside the source.
- **Custom folder**: type an existing folder or browse to it; saves `{original}_proxy` directly in that folder.

Duplicate names receive sequence numbers. Proxy generation cannot replace, move or delete originals. Location and codec choices are included in saved presets. Portable preset exports clear custom paths and reset the location to In subfolder. Watch-folder output rules use their configured custom output folder.

Source frame rate, timestamps, timecode, display orientation and audio layout are verified. Current scope is known SDR progressive footage; alpha, HDR, 12-bit and interlaced input remain unsupported. No automatic full quality search is run for proxies. NLE relinking/playback still depends on the editor and has not been certified across all applications.

Background references used for the original half/quarter and ProRes choices: [Adobe proxy workflow](https://helpx.adobe.com/premiere/desktop/organize-media/ingest-proxy-workflow/create-proxies.html), [Blackmagic proxy workflow](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_17_New_Features_Guide.pdf), and [Apple ProRes white paper](https://www.apple.com/final-cut-pro/docs/Apple_ProRes_White_Paper.pdf). These links are kept in project documentation rather than the output panel.
