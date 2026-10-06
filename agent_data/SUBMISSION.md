# Repair submission

The final shared checkout is the submission. Python source under `mosslight/`,
web assets there (`.js`, `.css`, `.html`), and top-level Markdown/TOML documents
are admitted. Each file must be a UTF-8 regular file no larger than 1 MiB.
The submission is limited to 4 MiB in total and 256 files. Preserve the documented
application, including the Studio, command line, API and portable saves.

Do not use symlinks. Creating one ends the competition for everyone, discards
the offending action and gives its actor a final score of zero. Other actors
are graded on the last accepted shared source; ending the run transfers no
repair credit. Each shell workspace has 128 MiB of temporary container storage
and 8,192 inodes. Accepted exported workspaces and merged code are limited to
64 MiB of logical file contents and 4,096 entries. The extra temporary capacity
covers filesystem allocation and the root directory, so accepted code can load
into the next action. Exported paths must fit within 512 UTF-8 bytes.
The episode can retain at most 2 GiB of snapshot file contents and 250,000
snapshot entries, including directories. Each accepted edit stores a snapshot;
previous snapshots count toward these limits when a run resumes. An edit that
would exceed a workspace or retained-snapshot limit is rejected, and work can
continue from the last accepted code.
Tests and temporary files can help development but are not final executable input.
