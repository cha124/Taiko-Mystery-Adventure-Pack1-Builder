# Architecture through Milestone 2

```text
CLI
 ├─ CIA diagnostic job
 │   ├─ CIA/TMD/content reader
 │   ├─ optional unencrypted NCCH/RomFS inspection
 │   ├─ profile-backed SongCatalog
 │   └─ independent validation → atomic JSON report
 └─ TJA check
     └─ strict decode → lexer → parser/typed AST → validator → normalizer
```

Both paths are read-only. No writer, transcoder, allocator, GUI, or packaging path exists in these milestones.

The Pack1 profile deliberately contains no guessed title IDs, slot offsets, or SongInfo schema. Diagnostic evidence must be collected before those values become verified profile data.

