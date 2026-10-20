# Releasing StreamFetch

Every user-visible StreamFetch update gets visual release notes. The goal is a
changelog that explains the outcome in seconds and still records the details a
returning user needs.

## Release documentation contract

1. Copy `docs/releases/TEMPLATE.md` to `docs/releases/vX.Y.Z.md`.
2. Capture the real application with neutral local demo data. Do not include
   personal paths, accounts, cookies, copyrighted media, credentials, or tokens.
3. Put version-specific images in `docs/assets/releases/vX.Y.Z/`. Reuse a shared
   asset only when it still represents the released interface exactly.
4. Include one visual overview and no more than three focused screenshots.
5. Add the release to the top of `CHANGELOG.md`, linking the full visual notes.
6. If the update changes the primary product story, refresh the README tour too.
7. Run the full validation suite before tagging the release.

## Capture guidelines

- Use a desktop viewport around 1440 × 900 and one narrow viewport around
  390 × 844 when responsive behavior changed.
- Prefer PNG for static UI and an optimized GIF or WebP for a short interaction.
- Keep a GIF below roughly 5 MB and under 15 seconds.
- Show finished states rather than loading spinners or open developer tools.
- Use descriptive, lowercase filenames such as `queue-reorder.png`.
- Write alt text that names both the view and the feature being demonstrated.

## Changelog format

Keep the headings from the template in this order:

1. In one sentence
2. Visual tour
3. What changed: Added, Improved, Fixed as applicable
4. Upgrade notes
5. Verified with
6. Links

Write for users, not commit history. “Added queue reordering” is useful;
“refactored `render_player()`” belongs in a pull request.

## Final checklist

- [ ] Package and module versions match the release tag
- [ ] Visual release file exists at `docs/releases/vX.Y.Z.md`
- [ ] Changelog entry links the visual release file
- [ ] Screenshots use neutral, non-sensitive demo data
- [ ] README screenshots still match the current product
- [ ] `ruff check .` passes
- [ ] `pytest` passes on all supported Python versions
- [ ] GitHub release notes link the changelog or visual release file
