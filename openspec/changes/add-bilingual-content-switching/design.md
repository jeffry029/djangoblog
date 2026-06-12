## Context

DjangoBlog already enables Django locale middleware, `LANGUAGES`, and `i18n_patterns`, so the routing and request-language foundation exists. The missing layer is content localization: `Article.title` and `Article.body` are single-language fields, templates render them directly, and the collector currently rewrites feed entries into Chinese Markdown only.

The target experience is Chinese-first compatibility plus a readable English version for visitors and crawlers. Existing Chinese URLs and behavior must remain stable. English content must be stored, not generated at request time, because search crawlers need deterministic pages and users should not wait on LLM calls during page load.

## Goals / Non-Goals

**Goals:**

- Add first-class English storage for article title, body, and SEO summary.
- Render list/detail/search/feed content from the active Django language with Chinese fallback.
- Provide a visible header language switcher using the existing Django locale mechanism.
- Generate bilingual content for newly collected articles and backfill existing published articles.
- Publish SEO signals that let Google discover Chinese and English versions as distinct language alternatives.
- Keep the implementation incremental and compatible with existing public content.

**Non-Goals:**

- Translating user comments, admin-only screens, historical logs, analytics data, or OAuth/account flows beyond existing gettext coverage.
- Replacing Django i18n infrastructure with a custom locale system.
- Geolocating users by IP for language selection.
- Translating images, attachments, code blocks, or third-party source pages.
- Making English mandatory before an article can be published.

## Decisions

1. Store English fields directly on `Article`.

   Add nullable/blank fields such as `title_en`, `body_en`, and `seo_description_en` to the existing model. This keeps reads simple, avoids a join on every article list/detail page, and matches the current single-row article workflow. A separate translation table was considered, but it adds complexity that is not justified while the supported language set is limited to Chinese and English.

2. Keep Chinese as the canonical fallback content.

   Existing `title` and `body` remain the Chinese source fields. Helper methods or template filters expose language-aware values, returning English only when the active language starts with `en` and the English field is populated. This avoids blank English pages during rollout and keeps old articles readable.

3. Use Django's active language rather than IP geolocation.

   `LocaleMiddleware`, URL prefixes, `Accept-Language`, and `/i18n/setlang/` already cover automatic and manual selection. IP-based language inference was considered but rejected because crawlers, VPNs, and multilingual users make it unreliable.

4. Generate English content offline through collectors and commands.

   The collector should request structured bilingual output from the existing OpenAI-compatible client and store both languages during `publish_rewritten_article`. A separate management command should backfill missing English content for existing articles in batches. Request-time generation was rejected because it is slow, costly, and poor for SEO consistency.

5. Add language-aware SEO helpers.

   Article detail pages should output language-specific title/description and `link rel="alternate" hreflang="..."` tags. Existing canonical behavior needs special handling: when an article has a source URL, the page can still expose source attribution, but site-owned bilingual pages need self-referencing canonical URLs if they are intended to rank as summaries.

6. Reuse existing gettext for interface text.

   Hard-coded Chinese labels in public templates should move behind `{% trans %}` where they are part of navigation, buttons, metadata labels, empty states, or article boilerplate. Article content remains stored data rather than gettext strings.

## Risks / Trade-offs

- [Risk] Database storage for article body text grows roughly with the English content size. -> Mitigation: only article text fields grow significantly; keep fields nullable/blank and monitor table/index size after backfill.
- [Risk] LLM output may produce invalid structure or weak translations. -> Mitigation: validate structured output, require fallback to Chinese on parse failure, and log failed article IDs for retry.
- [Risk] Existing cached template fragments may show the wrong language. -> Mitigation: include active language in cache keys for article fragments, breadcrumbs, and any rendered content cache.
- [Risk] Search indexes may return mixed-language snippets. -> Mitigation: index English fields explicitly and update search templates/documents to choose language-aware title/body.
- [Risk] Changing canonical tags can affect Google indexing. -> Mitigation: make canonical strategy explicit, add `hreflang`, and verify sitemap/head output before deployment.
- [Risk] Backfilling all historical articles can create LLM cost spikes. -> Mitigation: provide batch size, dry-run, article ID range, and resume behavior in the command.

## Migration Plan

1. Add article English fields with nullable/blank defaults and generate a Django migration.
2. Add model/helper methods for language-aware title, body, summary, SEO description, and full URL alternates.
3. Update templates and template tags to use helpers, add language-specific cache keys, and add the header language switcher.
4. Update collector output parsing to store bilingual content for new articles.
5. Add a backfill command for existing articles with dry-run and batching controls.
6. Update sitemap/feed/search indexing and page head metadata.
7. Run focused Django tests for models, views, template tags, collector parsing, sitemap/head output, and fallback behavior.
8. Deploy schema first, then code, then run backfill gradually.

Rollback strategy: keep the added fields but disable English rendering by removing/turning off the language switcher and falling back to Chinese helpers. Because the migration is additive, rollback does not require destructive data changes.

## Open Questions

- Should Chinese pages keep canonical links pointing to source URLs, or should site-owned summary pages self-canonicalize to improve search acquisition?
- Should English tags/categories be separate stored fields, or should public English pages initially reuse current category/tag names?
- Should RSS expose language-specific feeds at both `/feed/` and `/en/feed/`, or should feed content remain Chinese until later?
