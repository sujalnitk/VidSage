# Issue tracker: Local Markdown

Specifications and tickets live in `.scratch/` and are tracked in Git.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`.
- Specification: `.scratch/<feature-slug>/spec.md`.
- One file per ticket: `.scratch/<feature-slug>/issues/<NN>-<slug>.md`,
  numbered from `01`; never combine tickets into one file.
- Record state in a `Status:` line near the top of each ticket.
- Append discussion under `## Comments`.
- Keep credentials, private conversations, and real evaluation data
  out of these files; existing repository privacy rules still apply.

## Skill operations

When asked to publish a specification or ticket, create the appropriate
file above. When asked to fetch a ticket, read its referenced path.
Resolve bare ticket numbers within the feature directory; ask when ambiguous.

## Wayfinding operations

- Map: `.scratch/<feature-slug>/map.md`, with Notes,
  Decisions-so-far, and Fog sections.
- Child tickets use the same numbered issue files.
- `Type:` is research, prototype, grilling, or task.
- `Status:` is open, claimed, or resolved.
- Record dependencies as `Blocked by: NN, NN`.
- Select the lowest-numbered open, unclaimed ticket whose dependencies
  are all resolved.
- Set `Status: claimed` before working.
- To resolve, append `## Answer`, set `Status: resolved`, and add
  a summary and ticket link to the map's Decisions-so-far section.
