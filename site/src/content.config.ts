import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';
import { blogSchema } from 'starlight-blog/schema';

// Content lives in `src/content/docs/` (docs) and `src/content/docs/blog/`
// (blog posts, discovered by starlight-blog). The blog schema is merged into
// the docs schema so post frontmatter (date, authors, excerpt, tags…) validates.
export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({ extend: (context) => blogSchema(context) }),
  }),
};
