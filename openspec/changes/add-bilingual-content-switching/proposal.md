## Why

The site currently stores and renders article content primarily in Chinese, which creates a mismatch for English-language visitors arriving from Google Search, especially US traffic with low click-through or engagement. Adding first-class English content and language-aware URLs gives readers a readable experience while giving search engines distinct Chinese and English pages to index.

## What Changes

- Store English article title, body, and SEO summary alongside the existing Chinese article fields.
- Render article lists, detail pages, navigation labels, metadata, RSS/search snippets, and related article links using the active language, with Chinese as the default fallback.
- Add a header language switcher that lets visitors manually choose Chinese or English using Django's existing locale infrastructure.
- Generate or backfill English content for collected articles through management commands and the existing LLM-based collection pipeline.
- Expose language-specific SEO metadata, canonical URLs, and `hreflang` alternates so Google can discover the English version independently.
- Keep existing Chinese URLs and content behavior compatible for current users.

## Capabilities

### New Capabilities
- `bilingual-article-content`: Stores and retrieves Chinese and English article content with safe fallback behavior.
- `language-aware-presentation`: Presents public site UI and article content in the active language, including manual switching.
- `bilingual-seo-discovery`: Publishes language-specific SEO, sitemap, feed, and search indexing signals for Chinese and English pages.

### Modified Capabilities

None.

## Impact

- Affected Django models and migrations: `blog.models.Article`, generated migration files, admin forms/list display.
- Affected rendering: article detail/list templates, article template tags, navigation/header templates, SEO head metadata.
- Affected routing and locale behavior: existing `i18n_patterns`, `/i18n/setlang/`, sitemap URL generation, canonical and alternate link tags.
- Affected content pipeline: `blog/services/collectors.py`, rewrite/backfill management commands, search index documents/templates, RSS feed content selection.
- External dependency impact: no new hard runtime dependency is required; LLM generation reuses the existing OpenAI-compatible client and environment variables.
