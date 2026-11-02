# Filename parts

The template supports {original}, {archiver}, {resolution}, {framerate}, {codec}, {quality} and {sequence}. Archiver renders as the literal lowercase text archiver. Buttons add parts in click order and show their order numbers; manually entered custom suffixes also remain supported.

Keep originals starts with {original}_{archiver}. Original name remains locked. Archiver is locked until another part (or non-separator custom text) is added, then it can be deselected. Removing the last replacement part restores Archiver. Reset restores the two default parts. Template input is normalized immediately, including the literal _archiver suffix saved by older versions. Under Save to another folder, both filename parts are optional. Proxy and Replace originals keep their existing naming workflows.

The backend recognizes the Archiver token for both naming previews and queue outputs. For legacy direct template requests containing only Original name/separators under Keep originals, it appends the Archiver tag. Original-name requirements, filename validation and automatic collision numbering remain in place. No source files are renamed by editing a template.

Validation includes rendered names, custom suffix alternatives, legacy requests, directory outputs and browser button guards. Preset status updates when filename parts change and clears if the settings return to the saved baseline.
