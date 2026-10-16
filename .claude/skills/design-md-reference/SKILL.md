---
name: design-md-reference
description: Reference library of 84 brand DESIGN.md files (colours, type scales, spacing, components) from VoltAgent/awesome-design-md, stored in design/awesome-design-md/. Use when comparing visual directions, borrowing a pattern (a token scale, a table or card treatment, a dark palette), or writing or extending this project's own design system. Not a source of truth for AWS-MMS; docs/DBD.md is.
---

# DESIGN.md reference library

The collection lives in `design/awesome-design-md/design-md/<brand>/DESIGN.md` (84 brands, MIT licensed, copied 2026-10-16 from https://github.com/voltagent/awesome-design-md). Each file is one brand's design system written for coding agents: YAML front matter with colour, type and spacing tokens, then prose on components and usage.

## Rules

1. **docs/DBD.md (Design Brief) decides.** AWS-MMS uses Vuetify 4 (brand themes and global defaults) and Tailwind CSS 4 with Horizon blue `#22569A`, slate neutrals, reserved status colours, Inter and JetBrains Mono. A reference file can inform a choice, never override one already made there. If a reference suggests a change to a DBD decision, propose it to the user; do not apply it.
2. **Never copy a brand's DESIGN.md into the project root** or adopt a brand's palette, logo, type or name wholesale. AWS-MMS must not look like another company's product. Borrow structure and patterns, not identity.
3. **Read only the files you need.** List `design/awesome-design-md/design-md/` and open the two or three brands that fit the question; do not load the whole library.
4. Name the brand you drew from when you suggest a pattern, so the user can check it.

## Where to look first

AWS-MMS is an operations app (tables, forms, status, dashboards, a field phone mode), not a marketing site. Brands whose systems are built for dense product UI are the likely fits, for example `ibm` (Carbon), `linear.app`, `sentry`, `posthog`, `supabase`, `hashicorp` and `mongodb`. Open the file to confirm before relying on it. Each folder's README.md only points to getdesign.md; the DESIGN.md beside it is the content.
