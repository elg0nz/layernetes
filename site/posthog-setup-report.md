# PostHog post-wizard report

The wizard has completed a full PostHog analytics integration for the Layernetes marketing site. A new `src/components/posthog.astro` component was created using the PostHog JS snippet with the `is:inline` directive, and it was imported into `src/layouts/Base.astro` so it loads on every page. Environment variables were written to `.env` and referenced in the component. Eight custom events were instrumented across the hero CTA, CLI tool selector, copy buttons, nav links, blog index, and the intro blog post — covering the key conversion and engagement signals for the site.

| Event name | Description | File |
|---|---|---|
| `cta_ship_agent_clicked` | User clicked a 'Ship your first agent' CTA button anywhere on the site | `src/pages/index.astro`, `src/components/Nav.astro` |
| `cli_tool_selected` | User switched the CLI tool shown in the hero command selector dropdown | `src/scripts/cli-selector.js` |
| `command_copied` | User copied a command or code snippet via any copy button on the site | `src/scripts/copy.js` |
| `blog_post_clicked` | User clicked a link to open a blog post from the blog index or homepage | `src/pages/blog/index.astro`, `src/pages/index.astro` |
| `rss_subscribe_clicked` | User clicked the 'Subscribe via RSS' button on the blog index page | `src/pages/blog/index.astro` |
| `github_link_clicked` | User clicked the GitHub link in the navigation bar or blog subscribe section | `src/components/Nav.astro`, `src/pages/blog/index.astro` |
| `get_access_clicked` | User clicked the 'Get access' card on the homepage learn section | `src/pages/index.astro` |
| `blog_article_end_cta_clicked` | User clicked the 'Ship your first agent' CTA at the end of a blog article | `src/pages/blog/introducing-layernetes/index.astro` |

## Next steps

We've built a dashboard and five insights to track user behavior based on the events instrumented above:

- **Dashboard**: [Analytics basics (wizard)](https://us.posthog.com/project/231006/dashboard/1842352)
- **Insight**: [Ship Agent CTA clicks by location](https://us.posthog.com/project/231006/insights/9jIW0Wxw)
- **Insight**: [CLI tool selections](https://us.posthog.com/project/231006/insights/Y1EFaBsm)
- **Insight**: [Commands copied over time](https://us.posthog.com/project/231006/insights/QedxcjqH)
- **Insight**: [Blog-to-access conversion funnel](https://us.posthog.com/project/231006/insights/X9i3eI8w)
- **Insight**: [GitHub link clicks](https://us.posthog.com/project/231006/insights/DWniSBn3)

## Verify before merging

- [ ] Run a full production build (the wizard only verified the files it touched) and fix any lint or type errors introduced by the generated code.
- [ ] Run the test suite — call sites that were rewritten or instrumented may need updated mocks or fixtures.
- [ ] Add `PUBLIC_POSTHOG_PROJECT_TOKEN` and `PUBLIC_POSTHOG_HOST` to `.env.example` and any monorepo/bootstrap scripts so collaborators know what to set.
- [ ] Wire source-map upload (`posthog-cli sourcemap` or your bundler's upload step) into CI so production stack traces de-minify.

### Agent skill

We've left an agent skill folder in your project at `.claude/skills/integration-astro-static/`. You can use this context for further agent development when using Claude Code. This will help ensure the model provides the most up-to-date approaches for integrating PostHog.
