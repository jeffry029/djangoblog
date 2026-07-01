# 开发者雷达

面向公开访问的技术内容站点，聚合技术博客与 AI 快讯，并用 LLM 生成中文摘要与可落地的实践文章。

当前版本已经从通用博客系统，收敛为一个更适合个人简历展示和长期运营的只读内容站点：

- 技术文章自动抓取、去重、改写、发布
- AI 快讯自动抓取并写入 MySQL
- 公开访客仅支持浏览，管理、登录、注册、上传等入口默认封禁
- 支持 `robots.txt`、`sitemap.xml`、详情页 canonical、访问频率限制
- 支持 Supervisor 宿主机部署，也支持 Docker 镜像构建与 `docker compose` 部署

[English](docs/README-en.md)

## 项目定位

这个仓库现在承载的是一个公开只读的内容产品，而不是原始形态的全功能博客后台。

站点内容主要分两类：

- `技术摘要`：从技术博客、工程团队博客、云厂商、AI 框架等 RSS/Atom 源抓取，再通过 LLM 生成中文文章
- `AI 快讯`：从 `https://aihot.virxact.com/` 抓取快讯列表，直接展示到新闻页

适合的使用场景：

- 个人品牌网站
- 简历项目展示
- 技术内容聚合站
- 公开可读、后台私有维护的博客站

## 当前亮点

- **公开只读**：访客只能 `GET/HEAD` 浏览，`/admin/`、`/login/`、`/register/`、`/upload` 等写接口默认返回 `404`
- **自动化采集**：定时抓取技术文章与 AI 快讯，按来源链接去重，避免重复入库
- **LLM 技术改写**：文章改写支持通过 `OPENAI_BASE_URL` 接入兼容接口，当前默认适配 DashScope OpenAI 兼容模式
- **更适合阅读的详情页**：展示来源、AI 摘要、原文链接，并附带免责声明，避免把 AI 摘要伪装成原文
- **SEO 基础设施**：内置 `robots.txt`、`sitemap.xml`、canonical，适合搜索引擎收录
- **宿主机部署友好**：Supervisor 可直接管理 `web` 和 `scheduler` 两个进程，适合已有 MySQL 的云服务器
- **容器部署可选**：支持多阶段 Docker 构建，前端静态资源和 Django 服务可一起打包

## 二次开发说明

本项目基于上游开源项目 `DjangoBlog` 二次开发，保留了上游成熟的 Django 内容管理基础，并围绕以下方向做了产品化调整：

- 首页 / 新闻页重构
- 公开只读安全模式
- MySQL 环境变量化
- 技术文章抓取与 AI 改写
- AI 快讯抓取与展示
- Supervisor / Docker 部署补充

上游项目地址：

- `https://github.com/liangliangyy/DjangoBlog`

## 技术栈

- 后端：Python 3.11、Django
- 数据库：MySQL
- 前端：Tailwind CSS、Alpine.js、HTMX、Vite
- 内容处理：Markdown、BeautifulSoup、RSS / Atom 解析
- AI 改写：OpenAI 兼容接口
- 部署：Gunicorn、Supervisor、Docker Compose

## 内容采集与改写

## 数据库选择：MySQL 或 SQLite

默认仍使用 MySQL。低内存单机部署可以切换到 SQLite，减少 MySQL 服务的常驻内存占用：

```env
DJANGO_DATABASE_ENGINE=sqlite
DJANGO_SQLITE_PATH=/root/project/djangoblog/db.sqlite3
DJANGO_SQLITE_TIMEOUT=30
```

保留 MySQL 时继续使用：

```env
DJANGO_DATABASE_ENGINE=mysql
DJANGO_MYSQL_DATABASE=djangoblog
DJANGO_MYSQL_USER=djangoblog
DJANGO_MYSQL_PASSWORD=change-me
DJANGO_MYSQL_HOST=127.0.0.1
DJANGO_MYSQL_PORT=3306
```

从当前 MySQL 导出 SQLite 文件：

```bash
python scripts/export_mysql_to_sqlite.py --sqlite-path /root/project/djangoblog/db.sqlite3
```

如果目标文件已存在，脚本会拒绝覆盖；确认替换时加 `--overwrite`。导出完成后，把 `.env` 切到 `DJANGO_DATABASE_ENGINE=sqlite` 并重启 Django 服务。

### 1. 技术文章

技术文章抓取逻辑位于：

- [blog/services/collectors.py](blog/services/collectors.py)

当前内置源覆盖：

- Python / Django
- Kubernetes / Docker / CNCF
- Cloudflare / AWS / Google Cloud / Microsoft
- GitHub Engineering / Netflix / Meta / Slack / Dropbox / Airbnb
- Hugging Face / PyTorch / TensorFlow / OpenAI
- InfoQ / OSChina / 美团技术团队 / 阮一峰

抓取后会执行：

1. 拉取 RSS / Atom
2. 提取标题、摘要、发布时间、来源
3. 基于来源链接去重
4. 调用 LLM 生成中文技术文章
5. 自动追加原文链接并发布到文章列表

### 2. AI 快讯

AI 快讯当前抓取：

- `https://aihot.virxact.com/`

流程更轻量：

1. 抓取页面卡片
2. 提取标题、摘要、标签、来源链接
3. 写入 `NewsItem`
4. 展示到 `AI 快讯` 页签

## 环境变量

建议从 `.env.example` 复制为 `.env`，至少配置以下项目：

```env
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
PUBLIC_READ_ONLY_MODE=True
PUBLIC_RATE_LIMIT_PER_MINUTE=180

DJANGO_MYSQL_DATABASE=djangoblog
DJANGO_MYSQL_USER=djangoblog
DJANGO_MYSQL_PASSWORD=change-me
DJANGO_MYSQL_HOST=127.0.0.1
DJANGO_MYSQL_PORT=3306

WEB_HOST=0.0.0.0
WEB_PORT=8000

OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=change-me
BLOG_LLM_MODEL=glm-5.1

TECH_ARTICLE_LIMIT=5
AIHOT_NEWS_LIMIT=30
COLLECTOR_INTERVAL=1800
COLLECTOR_PROXY_URL=http://127.0.0.1:7890
COLLECTOR_LOG_TRACEBACKS=False
PLUGIN_HOOK_LOG_TRACEBACKS=False
```

关键配置说明：

- `PUBLIC_READ_ONLY_MODE=True`：开启公开只读模式
- `PUBLIC_RATE_LIMIT_PER_MINUTE=180`：同一 IP 每分钟访问限制
- `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`BLOG_LLM_MODEL`：控制技术文章改写
- `TECH_ARTICLE_LIMIT`：每轮最多发布多少篇技术文章
- `AIHOT_NEWS_LIMIT`：每轮最多抓取多少条 AI 快讯
- `COLLECTOR_INTERVAL`：定时任务循环间隔，单位秒
- `COLLECTOR_PROXY_URL`：RSS / AI 快讯直连失败后的代理 fallback，设为空可禁用
- `COLLECTOR_LOG_TRACEBACKS`：生产默认不输出采集/LLM 完整 traceback；排查采集问题时可临时设为 `True`
- `PLUGIN_HOOK_LOG_TRACEBACKS`：生产默认不输出插件 hook 完整 traceback；排查插件问题时可临时设为 `True`

## 本地运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
python manage.py migrate
```

### 3. 构建前端资源

```bash
cd frontend
npm ci
npm run build
cd ..
```

### 4. 启动 Web

```bash
python manage.py collectstatic --noinput
python manage.py compress --force
python manage.py runserver 0.0.0.0:8000
```

### 5. 启动采集调度

```bash
python manage.py run_collectors --interval 1800
```

## 部署方式

### Supervisor 宿主机部署

适合：

- 服务器上已经有 MySQL
- 希望直接占用宿主机端口
- 希望把 Web 和定时采集进程交给 Supervisor 托管

部署说明见：

- [deploy/supervisor/README.md](deploy/supervisor/README.md)

### Docker Compose

适合：

- 希望把前端构建和 Django 运行环境一起封装
- 希望环境在多台服务器之间可重复
- 服务器 MySQL 已独立部署，仅把应用容器化

项目根目录已提供：

- [docker-compose.yaml](docker-compose.yaml)
- [Dockerfile](Dockerfile)

## 安全与公开访问

当前站点按“公开只读内容站”设计，重点不是用户互动，而是安全地对外展示内容：

- 默认屏蔽管理与账号入口
- 默认拒绝写操作方法
- 启用基础访问频率限制
- 允许搜索引擎通过 `robots.txt` 和 `sitemap.xml` 抓取公开内容
- 文章详情页优先把 canonical 指向原文来源，减少重复内容风险

如果你后续要恢复后台写作、评论、注册、OAuth 登录，不建议直接在当前公开实例上打开，而应该分离管理入口或增加内网 / VPN 保护。

## 文档索引

- 中文说明：[README.md](README.md)
- 英文说明：[docs/README-en.md](docs/README-en.md)
- Supervisor 部署：[deploy/supervisor/README.md](deploy/supervisor/README.md)
- Docker 部署：[docs/docker.md](docs/docker.md)

## 许可说明

仓库保留上游项目的许可证文件。

如果你继续公开分发这个二次开发版本，建议保留上游版权与许可证声明，同时在 README 中明确“基于上游项目二次开发”的事实。对这个场景来说，这是最稳妥的做法。
