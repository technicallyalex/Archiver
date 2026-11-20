# Replacement working folder

Under Replace originals, set Working folder (optional) by typing an existing full path or using Browse. Leave blank for the previous behavior of encoding beside the source. The setting is saved with each queued job and local output presets. Portable preset import/export removes the machine-specific path.

With a working folder, Archiver encodes and verifies there. Before removing the source file, it copies the original to a uniquely named .archiver-replacement folder in the working directory and verifies its SHA-256. It checks that the final output can fit after the original is removed, frees that space, then copies the encoded output back with exclusive creation and checksum verification. The original backup follows the selected Recycle Bin or permanent deletion action only after success. The encoded staging file is then removed.

The working disk needs room for both the encoded output and the original backup. The source disk must ultimately fit the final encoded file plus a small free-space margin. This handles cross-volume moves with verified copies rather than relying on an atomic rename across disks.

Failures during transfer attempt to restore the original when the destination is still owned by Archiver or absent. Recovery files and a recovery.json manifest are retained on failure or interruption; the queue item reports their location. Restart recovery marks such jobs as needing attention and does not delete their staging/recovery files or automatically retry the destructive step. Inspect the manifest and preserved files before manually restoring the original or finished output. This does not guarantee automatic recovery from physical disk failure.
