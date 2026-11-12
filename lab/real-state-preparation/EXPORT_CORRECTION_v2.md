# Export candidate corrective attempt v2

The phone's v1 candidate stopped at the memory_index_state fingerprint check. Source revision was 5029 and candidate revision was 5030. Both reported 70 memory chunks, 652 transcript events and nine session nodes. The source definitions show that each memory_index_chunks or memory_index_sources update increments the singleton memory revision by one.

The v1 verifier expected the original revision even when sanitizing a memory row had correctly fired that trigger. v2 calculates the expected revision from the number of its actual memory-table UPDATE operations. Each such UPDATE must match exactly one row, and its source revision trigger must match the reviewed definition.

The candidate must contain exactly the original singleton state row with revision equal to original revision plus those counted updates. Any other revision produces STOP. The resulting memory_index_state fingerprint is checked against that exact expected row. An increment is recorded in the change ledger with its original value, resulting value and originating table update counts.

All other retained record fingerprints, transcript sequence identities, counts, credential checks, identity-file checks and source/WAL checks retain their v1 requirements. This correction preserves the native trigger-generated revision. The export scope is the same as EXPORT_SCOPE_v1.md.

Run the new pinned script once against the verified restore. It creates a fresh candidate and retains the failed /root/orion-export-review-tb723i directory for diagnosis. Expected completion is EXPORT_CANDIDATE_REVIEW_REQUIRED with upload_ready=false. Any STOP ends this corrective attempt for review.

Real phone execution is pending. Local regression tests cover the reviewed trigger behavior, exact expected increments and rejection of unexpected revision changes.
