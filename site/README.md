# Layernetes site

The Layernetes marketing site + docs + blog, built with [Astro](https://astro.build/)
and [Starlight](https://starlight.astro.build/) (a "readthedocs-style" docs theme)
plus the [`starlight-blog`](https://starlight-blog-docs.vercel.app/) plugin.
Deployed to [Cloudflare Pages](https://developers.cloudflare.com/pages/).

## Content lives here

All content is Markdown under `src/content/docs/` — this is the single source
of truth (the old repo-root `docs/` folder was moved here):

```
src/content/docs/
├── index.mdx                     # landing page (splash)
├── ONBOARDING.md                 # → /onboarding
├── QA.md                         # → /qa
├── REMOTE-ACCESS.md              # → /remote-access
└── blog/
    └── introducing-layernetes.md # → /blog/introducing-layernetes
```

- **Docs** are any Markdown file outside `blog/`. Each needs `title` frontmatter.
  Add a page to the left nav by editing the `sidebar` in `astro.config.mjs`.
- **Blog posts** go in `blog/`. They need `title` and a `date`; `authors`,
  `excerpt`, and `tags` are optional (see the schema in `src/content.config.ts`).
  New posts appear on `/blog` and in `/blog/rss.xml` automatically.

## Local development

```sh
npm install
npm run dev        # http://localhost:4321  (live reload)
npm run build      # production build → dist/
npm run preview    # serve the built dist/ locally
```

Node 22.12+ is required (CI pins Node 22; Astro 7 no longer supports Node 20).

## Deployment

Pushes to `main` that touch `site/**` trigger `.github/workflows/site.yml`,
which builds the site and runs `wrangler pages deploy dist`. Pull requests only
build (they don't deploy).

### One-time Cloudflare setup

The deploy step is **inert until these exist** — CI will build on every push,
but the deploy won't succeed until:

1. **Create the Pages project** (once). Either:
   - In the Cloudflare dashboard: *Workers & Pages → Create → Pages → Direct
     upload*, name it `layernetes`; or
   - locally: `cd site && npx wrangler pages project create layernetes --production-branch main`
2. **Create an API token** at *My Profile → API Tokens* with the
   **Cloudflare Pages: Edit** permission.
3. **Add two GitHub repo secrets** (*Settings → Secrets and variables → Actions*):
   - `CLOUDFLARE_API_TOKEN` — the token from step 2
   - `CLOUDFLARE_ACCOUNT_ID` — your account ID (dashboard URL, or `wrangler whoami`)

After that, the next push to `main` publishes to `https://layernetes.pages.dev`.

### Manual deploy

To publish without waiting on CI (e.g. to test a Cloudflare config change, or
to redeploy the last build), build locally and push straight to Pages:

```sh
cd site
npm run build
npx wrangler pages deploy dist --project-name=layernetes --branch=main
```

Requires being logged in (`npx wrangler login`) or having
`CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` set in your shell. `--branch=main`
forces a production deploy — omitting it lands on a preview URL instead.

### Custom domain (optional follow-up)

To serve at e.g. `layernetes.learninglayer.ai`: in the Pages project → *Custom
domains*, add the hostname and follow the DNS prompt. Then update `site` in
`astro.config.mjs` to that URL so canonical links, sitemap, and RSS are correct.

> Note: Cloudflare now steers new static sites toward **Workers static assets**
> rather than Pages. Pages remains fully supported and is the simplest path for
> a static Astro build; migrating to Workers later is straightforward if desired.
