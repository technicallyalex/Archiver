# Recursive Media Pool import filters

With Include subfolders enabled, an adjacent Exclusions button opens a compact flyout. Enabling subfolders opens it immediately; closing it leaves exclusions active. The flyout supports Escape, outside click and narrow windows without expanding the import panel.

Proxy folders is one checkbox covering these case-insensitive exact folder names at any descendant level: Proxy, Proxies, Proxy Media and Final Cut Proxy Media. The tooltip describes their common editor associations. [DaVinci Resolve Proxy Generator](https://documents.blackmagicdesign.com/UserManuals/CloudStoreManual.pdf?_v=1743836410000) uses a proxy subfolder; [Premiere Pro](https://helpx.adobe.com/ca/premiere/desktop/organize-media/ingest-proxy-workflow/create-proxies.html) offers Proxies beside originals. Final Cut Pro supports managed and external media locations ([Apple media-management guide](https://www.apple.com/final-cut-pro/docs/Media_Management.pdf)); these rules cover Proxy Media and the optional Final Cut Proxy Media layout supported by [MHL's proxy generator](https://github.com/macvfx/MHL). They do not discover arbitrary proxy locations. Users can add other named checkbox entries and save their enabled states across restarts. Original Media, Final Cut Original Media and High Quality Media are not proxy exclusions.

Archiver test folders remains a separate checkbox, matching names beginning with Archiver-test-. Excluded folders and their contents are not traversed or probed. An explicitly selected root remains eligible even if its name matches an exclusion. Folder names cannot be paths or wildcard patterns. Version 106 combines the old Proxy and Proxies preferences using either enabled choice; existing custom entries matching the new proxy names are folded into the combined checkbox, and unrelated custom entries are retained.

As of 0.3-preview.105, matching source filenames are always retained. The parent-name heuristic and its UI have been removed; older saved skipParentCopies preferences and skip_parent_copies request flags cannot reactivate it. Distinct files can contain different footage despite identical basenames. There is no content hashing or deduplication during import.

Output naming handles conflicts instead. The first available name is retained; existing files, directories and queued/running outputs are checked, then _002, _003 and subsequent suffixes are appended before the extension. A folder is enumerated once per naming batch, avoiding repeated network checks for thousands of duplicate names. Queue admission and filename previews use the same allocator. Preview names are not reservations until queued, so filesystem changes can still change the final choice.

If a collision appears during encoding, publication chooses another name without rerunning the encoder. Exclusive file creation prevents overwriting another process's output. Explicit Replace originals continues to use the selected replacement workflow instead of renaming its target. Automatic suffixes can shorten the end of a very long stem to keep the filename within 255 characters.

Proxy collisions also receive suffixes. Renamed proxies may need to be attached individually if an editor cannot automatically match their names. Source paths remain attached to each queue job.

Folder exclusions, stop/cancel behavior and parallel import still apply. Sources and excluded files are never deleted by importing. Test folder identifiers remain random 20-character hexadecimal job IDs, not file hashes, timestamps or quality scores.


Validation includes recursive editor proxy layouts, preservation of original-media folders, legacy preference migration, saved custom exclusions, and browser flyout checks in both themes at six viewport sizes, including the non-popover fallback.

New test folders use the local start time, for example `Archiver-test-2026-11-02_10-45-30`. Tests starting in the same second receive `_2`, `_3`, and so on. The Archiver test folders exclusion recognizes both dated folders and earlier random-suffix names. Existing test folders are not renamed.
