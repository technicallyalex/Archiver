# Dependency license audit — 2026-10-31

Reviewed the actual Windows 0.3-preview.50 folder, pinned dependency metadata and licenses, pywinpty's shipped CycloneDX manifest, and upstream documentation. This is an engineering distribution recommendation, not legal clearance for every binary, jurisdiction, or codec patent. The accompanying JSON records native libraries and current notices. No application build or distribution policy was changed.

## Recommended distribution policy

Keep Python, the UI runtime components, terminal support, and ab-av1 bundled. Asking users to install Python, Rust, or compile tools would undo the portable-executable improvement. Include repository/release URLs in third-party notices for transparency, not as a replacement for notices that must accompany distributed binaries.

For the next public preview, keep FFmpeg and FFprobe externally installed through a short prebuilt-download workflow. For a later turnkey distribution, bundling a pinned, tested FFmpeg build is feasible once matching source, build information and third-party notices are prepared. That extra distribution work buys a much simpler user experience. A Docker image containing FFmpeg still distributes it and needs the same planning.

## Components

| Component | Finding | Recommendation |
|---|---|---|
| Python 3.14.6 | PSF licensing plus incorporated-library terms. The bundle includes Python's LICENSE.txt. | Bundle the interpreter; preserve its notices and account for the native libraries actually collected. [Python license](https://docs.python.org/3.14/license.html) |
| Tk/Tcl, libffi, zlib, OpenSSL and Windows runtimes | These are runtime components, not additional user-facing installations. OpenSSL 3 uses Apache-2.0; Tcl/Tk and other components have their own terms. The local runtime reports OpenSSL 3.5.7. | Keep required components bundled after collecting version-matched notices. Check Microsoft redistribution terms separately for the copied UCRT/API-set/VC runtime DLLs. [OpenSSL](https://openssl-library.org/source/license/index.html), [Microsoft](https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files) |
| pywinpty 3.1.2 | MIT top-level license. Its manifest declares 43 Rust components, including MIT/Apache alternatives and additional Unicode/LLVM-exception terms. The manifest alone does not establish which build-time components require binary notices. | Bundle; generate applicable transitive notices. The current package includes its license and manifest. [Upstream](https://github.com/andfoy/pywinpty) |
| winpty, OpenConsole, conpty helpers | Upstream winpty and Microsoft Terminal use MIT licenses. Exact origin/release mapping for the DLLs and EXEs copied from the wheel still needs recording. | Bundle the required helpers, with their own notices and verified provenance. [winpty license](https://github.com/rprichard/winpty/blob/master/LICENSE), [Microsoft Terminal license](https://github.com/microsoft/terminal/blob/main/LICENSE) |
| ab-av1 0.11.7 | MIT. Its license accompanies the bundled executable. Binary SHA-256: a3a9534d2adecabc4861acf632d0f64741f56e2050d52032a5307bebb4fbdcc9. Its statically linked Rust dependencies still need a version-matched notice inventory. | Bundle the tested binary, license and applicable third-party notices. [Pinned license](https://github.com/alexheretic/ab-av1/blob/v0.11.7/LICENSE), [releases](https://github.com/alexheretic/ab-av1/releases) |
| PyInstaller 6.21.0 | GPL-2.0-or-later with a bootloader exception; embedded runtime hooks also have Apache-2.0 terms. The exception permits bundled applications to use their own compatible licensing choices. | Build dependency only: users do not install it. Review embedded-hook notices. [Pinned terms](https://github.com/pyinstaller/pyinstaller/blob/v6.21.0/COPYING.txt), [official summary](https://pyinstaller.org/en/stable/license.html) |
| FFmpeg / FFprobe | External, not included in build 50. The installed 9.0.1 Gyan build reports GPLv3-or-later, with --enable-gpl, --enable-version3 and static linking. Its enabled x264/x265 and other libraries make a blanket LGPL description wrong. No --enable-nonfree flag was found. | External install for the immediate preview; optional future full bundle with a corresponding-source distribution plan. [Pinned FFmpeg licensing](https://github.com/FFmpeg/FFmpeg/blob/n9.0.1/LICENSE.md) |
| XPSNR, vmafmotion, codecs | These are features/libraries in the selected FFmpeg build, not separate Python dependencies to ask users to install. | Validate filters and selected encoders. GPU drivers remain the user's vendor installation. |
| Web UI | Local HTML/CSS/JavaScript; the current page has no external framework, web font, or CDN dependency. | Ship the local assets as today. |

## What FFmpeg bundling would require

For an online GPLv3 binary distribution, a practical plan is to offer the exact corresponding source beside the binary under an applicable GPLv3 section 6 method. Keep configuration, patches, required build scripts, and the corresponding enabled-library sources/notices together. An arbitrary repository URL or a link to the latest FFmpeg source is not a dependable corresponding-source plan for a particular third-party static build. Builds using --enable-nonfree can be unredistributable. [GPLv3](https://github.com/FFmpeg/FFmpeg/blob/master/COPYING.GPLv3), [FFmpeg legal guidance](https://ffmpeg.org/legal.html).

Archiver invokes FFmpeg as a separate executable; it does not link libavcodec into Python. That separation is useful, but does not itself establish a legal conclusion about aggregation/combined-work boundaries. FFmpeg copyright compliance and codec patent questions are distinct; obtain release-specific advice if distributing commercially.

## Current package gaps

The inspected folder has Python LICENSE.txt, pywinpty LICENSE.txt and its manifest, ab-av1 LICENSE, and Tk license.terms. Explicit OpenSSL, original winpty, and Microsoft Terminal notices were not found in that inventory. Tcl's separate notice and the Windows runtime redistribution route need verification. Do not treat the current package as a completed public-release notice set.

A single `_internal/licenses` directory and THIRD_PARTY_NOTICES file can carry this information without cluttering the launch folder. Generate a dependency/version/hash manifest at build time. Do not claim all 43 manifest entries are runtime dependencies or all notices are already satisfied.

Archiver itself has no top-level LICENSE file. Choose a project license before a public source release; dependency permissions do not select one for the project owner.

## Simple external FFmpeg setup

1. Send Windows users to [FFmpeg's download page](https://ffmpeg.org/download.html) or the [Gyan prebuilt releases](https://www.gyan.dev/ffmpeg/builds/). Recommend a tested Full build with the required XPSNR filter and encoders, rather than a source-code repository.
2. Extract the tools into a stable folder. Users do not need to compile them or change PATH.
3. Open Archiver's FFmpeg settings and select `bin/ffmpeg.exe` and `bin/ffprobe.exe`. Verify connection and required filters/encoders before offering Auto or the chosen hardware method.

A future guided Download video tools action could fetch a pinned upstream build directly, verify its checksum, and configure it. It should be a deliberate download with a clear source; it is not implemented here and does not automatically remove distribution obligations when binaries are mirrored or included in an installer/container.
