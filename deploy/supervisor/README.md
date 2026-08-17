# Supervisor 部署

这个部署方式面向已经有宿主机环境的服务器，直接在主机上运行 Django、Gunicorn 和采集调度进程，不依赖容器编排。

当前 Supervisor 方案会托管两个进程：

- `djangoblog-web`：执行前端构建检查、数据库迁移、静态资源收集、压缩，然后启动 Gunicorn
- `djangoblog-scheduler`：执行数据库迁移，然后循环运行技术文章和 AI 快讯采集任务

适合场景：

- 服务器已经安装 MySQL
- 想直接占用宿主机端口
- 想把 Web 和定时任务分开托管
- 希望通过 `.env` 控制运行参数

## 运行特征

当前服务按公开只读站点运行，建议保留：

- `PUBLIC_READ_ONLY_MODE=True`
- `PUBLIC_RATE_LIMIT_PER_MINUTE=180`

这样公开访客只能浏览，不能登录、注册、提交、上传或访问后台。

## 依赖准备

先在宿主机 Python 环境里安装依赖：

```bash
pip install -r requirements.txt
```

如果需要本机构建前端资源，还需要 Node.js 和 npm。

## 环境变量

建议从项目根目录的 `.env.example` 复制为 `.env`，至少配置这些字段：

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

DJANGOBLOG_PROJECT_DIR=/root/project/djangoblog
DJANGOBLOG_ENV_FILE=/root/project/djangoblog/.env
DJANGOBLOG_PYTHON=/root/miniconda3/envs/djangoblog/bin/python
DJANGOBLOG_GUNICORN=/root/miniconda3/envs/djangoblog/bin/gunicorn

BUILD_FRONTEND=True
NPM_REGISTRY=https://registry.npmmirror.com/

OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=change-me
BLOG_LLM_MODEL=glm-5.1

TECH_ARTICLE_LIMIT=5
AIHOT_NEWS_LIMIT=30
COLLECTOR_INTERVAL=1800
COLLECTOR_PROXY_URL=http://127.0.0.1:7890
COLLECTOR_LOG_TRACEBACKS=False
PLUGIN_HOOK_LOG_TRACEBACKS=False

GUNICORN_WORKERS=2
GUNICORN_THREADS=4
```

说明：

- `DJANGOBLOG_PROJECT_DIR`：项目根目录
- `DJANGOBLOG_ENV_FILE`：Supervisor 启动时加载的 `.env`
- `DJANGOBLOG_PYTHON`、`DJANGOBLOG_GUNICORN`：宿主机 Python / Gunicorn 路径
- `BUILD_FRONTEND=True`：首次部署或前端有变更时推荐开启
- `OPENAI_*`：控制技术文章的 LLM 改写
- `COLLECTOR_INTERVAL=1800`：每 1800 秒跑一轮采集
- `COLLECTOR_PROXY_URL`：采集直连失败后的代理 fallback；设为空可禁用
- `COLLECTOR_LOG_TRACEBACKS`：生产默认不输出采集/LLM 完整 traceback；排查采集问题时可临时设为 `True`
- `PLUGIN_HOOK_LOG_TRACEBACKS`：生产默认不输出插件 hook 完整 traceback；排查插件问题时可临时设为 `True`

## 启动脚本

Supervisor 实际调用的是两个脚本：

- [scripts/start_web.sh](../../scripts/start_web.sh)
- [scripts/start_scheduler.sh](../../scripts/start_scheduler.sh)

`start_web.sh` 会做这些事：

1. 加载 `.env`
2. 必要时执行 `npm ci` 和 `npm run build`
3. 执行 `python manage.py migrate`
4. 执行 `collectstatic`
5. 执行 `compress --force`
6. 启动 Gunicorn

`start_scheduler.sh` 会做这些事：

1. 加载 `.env`
2. 执行 `python manage.py migrate`
3. 启动 `python manage.py run_collectors --interval ...`

## 安装 Supervisor 配置

项目内配置文件：

- [deploy/supervisor/djangoblog.conf](djangoblog.conf)

安装方式：

```bash
ln -sf /root/project/djangoblog/deploy/supervisor/djangoblog.conf /etc/supervisor/conf.d/djangoblog.conf
supervisorctl reread
supervisorctl update
supervisorctl status djangoblog:
```

重启：

```bash
supervisorctl restart djangoblog:
```

查看状态：

```bash
supervisorctl status djangoblog:
```

## 日志查看

默认日志位置：

```bash
tail -f /var/log/supervisor/djangoblog-web.log
tail -f /var/log/supervisor/djangoblog-web.err.log
tail -f /var/log/supervisor/djangoblog-scheduler.log
tail -f /var/log/supervisor/djangoblog-scheduler.err.log
```

重点关注：

- `djangoblog-web.err.log`：Gunicorn 启动、静态资源、数据库连接问题
- `djangoblog-scheduler.err.log`：采集失败、RSS 解析失败、LLM 改写失败、MySQL 连接异常

## 采集任务说明

调度进程当前会循环执行两类任务：

### 技术文章

- 来源：内置 RSS / Atom 技术源，或环境变量 `TECH_BLOG_FEEDS`
- 默认每轮最多发布 `TECH_ARTICLE_LIMIT=5` 篇
- 如果配置了 `OPENAI_API_KEY`，会调用兼容 OpenAI 的接口完成中文改写

### AI 快讯

- 来源：`https://aihot.virxact.com/feed/full.xml`
- 默认每轮最多抓取 `AIHOT_NEWS_LIMIT=30` 条
- 摘要、可用正文、原文链接和 AI HOT permalink 写入 `NewsItem`；有正文走站内详情，无正文保持外部跳转

## 常见问题

### 1. 页面能打开，但静态资源 404

优先检查：

- 是否执行过 `npm run build`
- 是否执行过 `collectstatic`
- `BUILD_FRONTEND` 是否被关闭
- Gunicorn 进程运行目录是否正确

### 2. Web 正常，调度没数据

优先检查：

- `.env` 里的 MySQL 是否可连通
- `OPENAI_API_KEY` 是否已配置
- 目标 RSS / Atom 源是否可访问
- `djangoblog-scheduler.err.log` 是否有超时或解析报错

### 3. 想减少采集频率或抓取数量

直接调整：

```env
COLLECTOR_INTERVAL=3600
TECH_ARTICLE_LIMIT=3
AIHOT_NEWS_LIMIT=20
```

### 4. 想跳过前端构建

如果静态资源已经构建完成，可以设置：

```env
BUILD_FRONTEND=False
```

但只适用于你确认 `frontend` 构建产物和静态文件都已经完整存在的场景。
