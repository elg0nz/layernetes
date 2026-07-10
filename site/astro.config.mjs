// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightBlog from 'starlight-blog';

// https://astro.build/config
export default defineConfig({
  // Public URL of the deployed site — the layernetes.wtp.io custom domain,
  // provisioned in the private sanscourier-infra repo (see
  // docs/cloudflare-setup.md).
  site: 'https://layernetes.wtp.io',
  integrations: [
    starlight({
      title: 'Layernetes',
      description:
        "Learning Layer's cloud for AI agents. Write your agent, run llnate push, and it goes live at a public URL any human or any AI can call. Exclusive to the AI floor.",
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/elg0nz/layernetes',
        },
      ],
      // Site-wide head additions for Starlight-rendered pages (docs, blog
      // plugin routes). The custom pages under src/pages get the equivalent
      // tags from src/layouts/Base.astro. Starlight already emits canonical,
      // og:title/description, and twitter:card on its own.
      head: [
        { tag: 'meta', attrs: { property: 'og:image', content: 'https://layernetes.wtp.io/og.png' } },
        { tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
        { tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
        { tag: 'meta', attrs: { property: 'og:site_name', content: 'Layernetes' } },
        { tag: 'meta', attrs: { name: 'twitter:image', content: 'https://layernetes.wtp.io/og.png' } },
        { tag: 'meta', attrs: { name: 'twitter:site', content: '@sanscourier' } },
        {
          tag: 'link',
          attrs: {
            rel: 'alternate',
            type: 'text/plain',
            title: 'llms.txt — agent quickstart',
            href: 'https://layernetes.wtp.io/llms.txt',
          },
        },
        {
          tag: 'link',
          attrs: {
            rel: 'alternate',
            type: 'text/plain',
            title: 'llms-full.txt — deep agent reference',
            href: 'https://layernetes.wtp.io/llms-full.txt',
          },
        },
      ],
      plugins: [
        starlightBlog({
          title: 'Blog',
          authors: {
            layernetes: {
              name: 'The Layernetes Team',
              url: 'https://www.learninglayer.ai/',
            },
          },
        }),
      ],
      sidebar: [{ label: 'Overview', slug: 'overview' }],
    }),
  ],
});
