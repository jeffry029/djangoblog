## 1. Data Model And Helpers

- [x] 1.1 Add optional English article fields for title, body, and SEO description to `Article`.
- [x] 1.2 Generate and review the Django migration for the new article fields.
- [x] 1.3 Add language-aware article helper methods for title, body, summary, SEO description, and fallback behavior.
- [x] 1.4 Update Django admin form/list/search configuration so English fields can be edited without disrupting existing Chinese publishing.
- [x] 1.5 Add focused model tests for English selection, Chinese fallback, and missing-English compatibility.

## 2. Public Language Presentation

- [x] 2.1 Update article template tags to render language-aware title, body, summary, source notice, and table of contents content.
- [x] 2.2 Update article list/detail templates to use language-aware values for headings, excerpts, previous/next links, read-more links, and metadata labels.
- [x] 2.3 Add a compact header language switcher using Django's `/i18n/setlang/` endpoint.
- [x] 2.4 Move public hard-coded Chinese labels in shared navigation, article list, article detail, empty states, and source notices behind `{% trans %}`.
- [x] 2.5 Include active language in cache keys for cached public article fragments.
- [x] 2.6 Add template/view tests for English rendering, manual language switching, and fallback to Chinese content.
- [x] 2.7 Add language-aware site title/slogan configuration, old-data defaults, and public rendering tests.

## 3. Bilingual SEO And Discovery

- [x] 3.1 Make base HTML `lang` reflect Django's active language instead of a hard-coded Chinese value.
- [x] 3.2 Add article detail head metadata that prefers English title and SEO description under English locale.
- [x] 3.3 Add `hreflang` alternate links for Chinese and English article URLs.
- [x] 3.4 Decide and implement canonical behavior for site-owned bilingual article summary pages versus source attribution links.
- [x] 3.5 Update sitemap generation to expose English article URLs or alternates only when English content exists.
- [x] 3.6 Update feed and search indexing/snippet output to prefer active-language article fields.
- [x] 3.7 Add tests for head metadata, `hreflang`, sitemap English inclusion/exclusion, feed output, and search indexing field selection.

## 4. Collection And Backfill Pipeline

- [x] 4.1 Update the article rewrite prompt/output contract to request structured bilingual Markdown content.
- [x] 4.2 Add parser and validation logic for generated bilingual article output.
- [x] 4.3 Update `publish_rewritten_article` to store Chinese content in existing fields and English content in new fields.
- [x] 4.4 Update `rewrite_latest_article` or add a companion command so manual rewrites can refresh English fields.
- [x] 4.5 Add a batchable dry-run-capable management command to backfill English content for published articles missing English fields.
- [x] 4.6 Add collector and command tests covering valid bilingual output, invalid output, skip behavior, dry-run, and batch limits.

## 5. Verification And Release

- [x] 5.1 Run targeted Django tests for models, views, template tags, sitemap, feed, search, collectors, and management commands.
- [x] 5.2 Run the full Django test suite or document any environment blocker.
- [x] 5.3 Verify representative Chinese and English pages in a browser, including header switcher, article detail, article list, and page head tags.
- [x] 5.4 Document deployment order: migrate schema, deploy code, run limited backfill, inspect Search Console indexing behavior, then continue backfill.
