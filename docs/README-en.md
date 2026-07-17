# Developer Radar

Developer Radar is a public, read-only developer content site built on top of DjangoBlog and reshaped for curated tech writing and AI news aggregation.

It focuses on two content streams:

- `Technical Summaries`: RSS/Atom tech articles rewritten into Chinese with an LLM
- `AI News`: summaries and available detail content collected from the AI HOT selected RSS feed and displayed on local detail pages

## What this fork is for

This repository is no longer positioned as a generic multi-user blog platform. It is now optimized for:

- personal branding sites
- resume-ready showcase projects
- curated developer content portals
- public browsing with private maintenance

## Current highlights

- Public read-only mode with `GET/HEAD` only
- `404` on `/admin/`, `/login/`, `/register/`, `/upload` and other write-oriented routes
- Scheduled collectors for tech articles and AI news
- LLM-based rewriting through an OpenAI-compatible API
- MySQL-backed storage
- `robots.txt`, `sitemap.xml`, rate limiting, and canonical handling
- Host deployment with Supervisor, plus optional Docker Compose packaging

## Upstream attribution

This project is a secondary development based on the upstream DjangoBlog project:

- `https://github.com/liangliangyy/DjangoBlog`

The upstream codebase provides the Django content foundation. This fork adds product-level changes around public read-only access, article/news collection, LLM rewriting, deployment, and frontend presentation.

## Runtime configuration

Environment variables are documented in `.env.example`. The main ones are:

```env
PUBLIC_READ_ONLY_MODE=True
PUBLIC_RATE_LIMIT_PER_MINUTE=180

DJANGO_MYSQL_DATABASE=djangoblog
DJANGO_MYSQL_USER=djangoblog
DJANGO_MYSQL_PASSWORD=change-me
DJANGO_MYSQL_HOST=127.0.0.1
DJANGO_MYSQL_PORT=3306

OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=change-me
BLOG_LLM_MODEL=glm-5.1

TECH_ARTICLE_LIMIT=5
AIHOT_NEWS_LIMIT=30
COLLECTOR_INTERVAL=1800
```

## Deployment

- Supervisor deployment: [deploy/supervisor/README.md](../deploy/supervisor/README.md)
- Docker Compose: [docker-compose.yaml](../docker-compose.yaml)

## License note

The repository keeps the upstream license file. For a derivative work based on an MIT-licensed upstream project, preserving the license notice and clear attribution is the practical default.
