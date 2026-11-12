# Package the local candidate for transfer review

The candidate at /root/orion-export-review-BYY7Km/candidate passed export preparation. Its report retains three conversations, 652 transcript events and 70 memory chunks. Four identity files match the recovered source. Fourteen transcript events and one memory chunk have credential redactions. The report explicitly lists the excluded populated tables and derived memory revision update.

pack_reviewed_candidate_v1.py reads the candidate and creates a local archive in its parent directory. It requires exactly the reviewed three database files, four identity files and manifest.json. It checks every payload file against the manifest and checks the identity hashes against export-review.json. It rejects extra files and symlinks.

Before packing, a read-only SQLite comparison checks source-versus-candidate transcript session/sequence identity and memory chunk identity. It classifies changed logical JSON fields and memory text as credential-marker redactions, preserving surrounding text. The changed-record totals must equal the export report. Only counts and fixed diagnostic codes are emitted.

The archive contains eight regular files with relative paths and normalized ownership/mode metadata. After writing, the script reads every archived member back and verifies its SHA-256. The private fingerprint key, private original baseline, diagnostics, working databases and report-parent directory are outside the archive.

Success prints PACKAGED_REVIEW_REQUIRED, archive size, SHA-256, manifest SHA-256 and the redaction review. upload_ready remains false. This is the transfer-review receipt. It also reports whether GitHub CLI is installed, without reading authentication credentials.

Any mismatched file, unexpected content change, record-identity change, extra file or packaging failure produces STOP. Keep the local candidate and diagnostic output. The archive uses exclusive creation, so an existing archive is not overwritten.

Next review the receipt and authorize the sanitized input transfer. The migration job input will be pinned to this exact archive SHA-256. The GitHub migration run and production deployment are later stages.
