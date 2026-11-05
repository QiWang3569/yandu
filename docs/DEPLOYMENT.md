# 公开部署准备与操作

当前仓库提供 PostgreSQL、应用和 Caddy 的容器配置。它需要一台可从互联网访问的 Linux 服务器，以及已经指向该服务器的域名。取得服务器和域名后再执行本页的公开部署步骤；本机执行 `docker compose -f compose.production.yaml config` 或构建镜像不会公开网站。

## 上线前准备

1. 在服务器安装 Docker 与 Compose，开放入站 80、443 端口，让域名的 DNS 记录指向服务器。Caddy 会按域名自动申请和续期 HTTPS 证书，并将 HTTP 请求重定向到 HTTPS。参见 [Caddy 自动 HTTPS 文档](https://caddyserver.com/docs/automatic-https)。
2. 复制 `.env.example` 为服务器本机 `.env`。填写 `SITE_DOMAIN`（仅域名，不带 `https://`）、长度足够的随机 `POSTGRES_PASSWORD`、`AUTH_CODE_SECRET` 和真实 SMTP 参数。数据库密码需使用 URL 安全字符（字母、数字、`-`、`_`），因为 Compose 会用它生成容器间连接地址。不要提交 `.env`，也不要把凭据放入 Dockerfile。
3. `APP_ENV=production` 由生产 Compose 设置，并强制使用 PostgreSQL、`DEMO_MODE=false`、安全 Cookie、可用邮件验证和单个 HTTPS 来源。应用容器不会向公网发布 8000 端口，PostgreSQL 也不会向公网发布 5432 端口。
4. 确认至少有一个已通过北大邮箱验证的真实账号。部署后可通过服务器命令 `docker compose -f compose.production.yaml exec app python -m app.admin_cli grant 你的北大邮箱` 授予管理员权限；不要把演示管理员账号用于公开服务。

## 部署

在服务器项目根目录执行：

```sh
docker compose -f compose.production.yaml config --quiet
docker compose -f compose.production.yaml build app
docker compose -f compose.production.yaml up -d
docker compose -f compose.production.yaml ps
```

检查 `https://你的域名/api/v1/health`、首页、邮箱验证码注册登录、商品浏览和图片上传。确认 HTTP 自动跳转到 HTTPS，登录响应的 Cookie 带 `Secure`、`HttpOnly`、`SameSite=Strict`。生产容器只运行一个应用进程；当前匹配任务队列还不支持多进程扩容。

若要把本机已有用户、商品、聊天迁移到新服务器，在启动 `app` 之前先将本机 PostgreSQL 自定义格式备份安全地传到服务器，只启动 `postgres`，再恢复到空库：

```sh
docker compose -f compose.production.yaml up -d postgres
docker compose -f compose.production.yaml exec -T postgres pg_restore --exit-on-error --no-owner --no-privileges -U yandu -d yandu < 已传入服务器的备份.dump
docker compose -f compose.production.yaml up -d
```

上传图片保存在应用数据卷中；如果旧项目有 `data/uploads` 文件，也要在停机窗口迁移这些文件。本机 SQLite 到 PostgreSQL 的首次迁移步骤见 [PostgreSQL 说明](POSTGRESQL.md)。

## 授予管理员权限

生产环境不使用演示管理员账号。先用真实北大邮箱完成验证码注册并登录一次，然后在服务器项目根目录执行：

```sh
docker compose -f compose.production.yaml exec app python -m app.admin_cli grant 你的北大邮箱
```

取消管理员：

```sh
docker compose -f compose.production.yaml exec app python -m app.admin_cli revoke 你的北大邮箱
```

说明：被授权的邮箱必须先完成注册，否则命令会提示“该邮箱尚未完成注册”。授权后该用户需要重新登录，权限才会生效。

## 备份、恢复与回退

`backup` 服务在启动时生成首份 `pg_dump` 自定义格式归档，此后每 24 小时备份一次。备份位于服务器 `data/backups/postgres`，默认保留 14 天；可以通过 `BACKUP_RETENTION_DAYS` 调整。用下面的命令把最新归档恢复到临时数据库并验证用户表、商品表和 pgvector，再自动删除临时库：

```sh
python3 scripts/verify_postgres_restore.py --compose-file compose.production.yaml
```

备份与原数据库若放在同一服务器，无法抵御整机故障；公开发布前应把备份定期复制到独立存储，并验证该副本可恢复。发布新版本前保留可回退的镜像和数据库备份。回退应用代码时，如果数据库结构已经升级，应先确认旧版本兼容；当前项目的结构升级仍采用增量加列，尚未建立完整的版本化迁移体系。

本页配置通过容器构建与 Caddy 配置验证后才可视为“可部署”；只有域名、证书、真实邮件收件、备份异机保存和线上业务冒烟测试全部完成，才能称为“已公开上线”。
