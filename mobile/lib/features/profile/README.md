# profile feature

Reserved. This feature's domain/data/presentation layers are populated in
its dedicated build phase (see project root docs/phase-notes/), not in
Phase 2. The folder structure below is created now so later phases drop
files into an already-agreed layout:

- `domain/` - entities, repository interfaces, use cases (no Flutter/HTTP imports)
- `data/` - repository implementations, API DTOs
- `presentation/` - screens, widgets, Riverpod providers
