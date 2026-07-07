// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightBlog from 'starlight-blog';

// https://astro.build/config
export default defineConfig({
  // Public URL of the deployed site. Update to the custom domain once it is
  // wired up in Cloudflare Pages (e.g. https://layernetes.learninglayer.ai).
  site: 'https://layernetes.pages.dev',
  integrations: [
    starlight({
      title: 'Layernetes',
      description:
        'Build, ship, and host CrewAI-powered AI agents on the Learning Layer cloud.',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/elg0nz/layernetes',
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
      sidebar: [
        {
          label: 'Docs',
          items: [
            { label: 'Onboarding', slug: 'onboarding' },
            { label: 'QA guide', slug: 'qa' },
            { label: 'Remote access', slug: 'remote-access' },
          ],
        },
      ],
    }),
  ],
});
