# 受邀云端演示

本配置面向少量可信体验者，使用共享账号 `demo` 和统一访问口令。所有人共享模拟项目、预测、助手对话和修改记录；没有个人空间、租户权限或实名审批。不要输入真实经营资料或个人敏感信息。

云端配置独立于本地 `compose.yaml`，不要合并使用。入口采用 Caddy 自动 HTTPS 与 HTTP Basic Authentication，浏览器弹出原生账号/口令框；不是应用账号系统。认证覆盖页面、静态资源和全部 API。云服务器/域名/公开证书签发仍需在实际环境验收，仓库中的配置不代表已经上线。

## 1. 准备服务器

- 单台 Linux、Docker Engine 和 Compose v2、Python 3、Git；小规模演示可从 2 核 4GB 起步，容量尚未压测。
- 准备域名，A 记录指向服务器；仅在正确配置 IPv6 时添加 AAAA。
- 安全组开放 TCP 80/443，SSH 仅允许管理员来源。不要开放 8000、8080、18088 或 Caddy 管理端口。
- 服务器须能拉取镜像、申请证书、访问 DeepSeek 官方 API。检查系统时间、磁盘空间及出站网络。
- 在服务器克隆公开仓库，切换到已审阅的提交。不要上传本地整个工作目录、私有 docs、数据库、日志或密钥。

命令在仓库根目录运行。初始化在服务器本机交互输入口令，不把口令/API key放在聊天、命令参数、Git、截图或 shell 历史中：

```sh
python3 deploy/cloud/configure.py --domain demo.your-domain.com
docker compose --env-file .env.cloud -f compose.cloud.yaml config --quiet
docker compose --env-file .env.cloud -f compose.cloud.yaml build
docker compose --env-file .env.cloud -f compose.cloud.yaml up -d
docker compose --env-file .env.cloud -f compose.cloud.yaml ps
```

使用密码管理器生成至少 20 字符的独立随机口令。工具只保存 bcrypt 哈希到被忽略的 `secrets/cloud-auth.caddy`，非秘密的部署设置放在被忽略的 `.env.cloud`；缺少认证文件时入口不能正常启动。没有默认可用口令。不要将哈希文件复制到公开工单；Windows 权限需由管理员额外检查，正式运行以 Linux 为准。

首次使用独立 `haru-estate-cloud_cloud-data` 卷，自动生成中性模拟项目，不影响本地 `haru-estate_haru-data`。Caddy 的证书数据也保留在独立卷中。禁止 `down -v`、清库或重复灌入本地验收数据。

## 2. 邀请访问与管理员入口

访客使用 `https://你的域名`，输入账号 `demo` 和统一口令。只通过可信渠道分享；不要把口令放进 URL。公开 HTTP 只重定向到 HTTPS，不用于填写口令。

云端页面提示共享环境，隐藏 AI 设置；公开模型配置接口始终返回 403，即使持有访问口令也不能配置。管理员在自己电脑建立 SSH 隧道：

```sh
ssh -N -L 127.0.0.1:18089:127.0.0.1:18088 your-admin@your-server
```

然后用浏览器打开 `http://127.0.0.1:18089`，在原有 **AI 设置** 中输入 DeepSeek 密钥。浏览器到本机为回环连接，跨网络传输走加密 SSH。此管理员入口有完整操作权限，不共享隧道，不将它代理到公网。配置仍只保存在 API 进程内存；API/服务器重启后需要重新输入。

云端默认 `HARU_DEMO_AI=off`。完成配置后，在服务器 `.env.cloud` 中改为 `HARU_DEMO_AI=on`，只重建 web 服务：

```sh
docker compose --env-file .env.cloud -f compose.cloud.yaml up -d --no-deps web
```

关闭同样改回 `off` 并更新 web；这会阻止新的助手创建/补充/重试，不取消已经运行的任务。它不影响数值测算、已有答案或草稿确认。访客仍须亲自确认草稿，LLM 没有审批权限。

公开入口限制全体访客合计写请求约 12 次/分钟（短时突发 4），助手创建/补充/重试约 2 次/分钟（突发 1）；轮询查询不占写入额度。返回 429 时请求尚未转交 API。限制不是按人计费，也不是每日费用硬上限；现有单任务调用预算仍保留。更改配置/重启 web 会重置入口限流状态，演示时仍应检查提供商用量，暂不用 AI 就关闭。无任何自动真实模型冒烟调用。

修改请求必须携带与演示域名一致的 Origin，防止浏览器缓存统一口令后被其他网站诱导写入。脚本调用也必须经 HTTPS 认证并提供相同 Origin；不要绕过入口连接内部 API。

## 3. 上线检查

1. HTTP 跳转 HTTPS；证书受信任，没有浏览器警告。
2. 无口令/错误口令访问首页、静态资源、`/api/v1/health`、项目/预测/助手接口均为 401；未认证 POST 不产生数据。
3. 正确口令能打开页面、生成模拟预测、查看来源与历史；模型配置 GET/PUT/DELETE 均为 403。
4. 错误或缺失 Origin 的写入返回 403；过频请求返回 429；AI 关闭时助手新请求返回 403。
5. 从外网连接 8000/8080/18088 应失败；管理员只能通过 SSH 隧道配置。
6. 在独立演示项目中验证版本确认与旧预测保留。先验证下面的双库备份恢复，再扩大邀请。

仓库提供 `python deploy/cloud/smoke.py`：使用独立临时容器/卷、本地测试证书及随机测试口令验证入口，不需要服务器、真实密钥或现有数据库。详见脚本帮助；不会验证公网 DNS/ACME 签发或真实模型。

## 4. 双库备份与恢复

演示期间的数据库和检查点必须一起保留。不要直接复制运行中的 WAL 数据库。先暂停邀请，关闭 AI，等待正在运行的任务结束；停止 API 会丢失内存模型配置。以下备份采用停止 API 后的一致时点，两次备份期间不要重启 API：

```sh
docker compose --env-file .env.cloud -f compose.cloud.yaml stop api
docker compose --env-file .env.cloud -f compose.cloud.yaml run --rm --no-deps api python -m app.backup /app/data/haru.sqlite3 /app/data/backups/REPLACE_UNIQUE_ID/haru.sqlite3
docker compose --env-file .env.cloud -f compose.cloud.yaml run --rm --no-deps api python -m app.backup /app/data/agent-checkpoints.sqlite3 /app/data/backups/REPLACE_UNIQUE_ID/agent-checkpoints.sqlite3
mkdir -p backups
docker compose --env-file .env.cloud -f compose.cloud.yaml cp api:/app/data/backups/REPLACE_UNIQUE_ID backups/
docker compose --env-file .env.cloud -f compose.cloud.yaml start api
```

两条备份必须都成功；使用同一个全新批次目录，禁止把不同批次混合。备份失败也保留原卷，处理后启动原 API。备份复制到服务器外的受限存储，记录应用提交、镜像 ID、两个文件的 SHA256。不要上传 Git。

恢复先新建独立空卷和独立 Compose 项目，把同批两个文件恢复为 `haru.sqlite3` 与 `agent-checkpoints.sqlite3`，设置 API 用户可写。不要把恢复文件覆盖到运行中的原卷。先以无公网入口、无真实模型的环境核对项目/版本/运行数量、已知金额与检查点，再切换；原卷保留用于回退。证书卷、访问口令哈希及部署设置另行受限备份。

## 5. 更新、回退与口令轮换

### 仅更新网页与网关（不重启 API）

适用于前端体验、文案、静态资源或网关配置更新。此操作不修改 `cloud-data` 卷，也不会使已在 API 进程内存中的模型配置失效。先核对工作区没有本地部署改动，再切换到已审阅提交；不要执行 `down`、`down -v`、`restart api` 或包含 `api` 的 `up` 命令。

```sh
cd ~/haru-estate
git fetch origin codex/cloud-demo
git checkout codex/cloud-demo
git pull --ff-only origin codex/cloud-demo
git rev-parse --short HEAD

# 将 .env.cloud 中的 HARU_RELEASE 改为上面核对过的完整提交 SHA。
# 本轮网页版本为 d398e13e6c0612100c8c4f96d9b511fd4e85fa26。
sed -i 's/^HARU_RELEASE=.*/HARU_RELEASE=d398e13e6c0612100c8c4f96d9b511fd4e85fa26/' .env.cloud

docker compose --env-file .env.cloud -f compose.cloud.yaml build web
docker compose --env-file .env.cloud -f compose.cloud.yaml up -d --no-deps --force-recreate web
docker compose --env-file .env.cloud -f compose.cloud.yaml up -d --no-deps --force-recreate gateway
docker compose --env-file .env.cloud -f compose.cloud.yaml ps
```

最后确认 `api` 仍显示原来的 `Up (healthy)`，而 `web`、`gateway` 也为运行状态；然后刷新浏览器验证新页面。若要部署改动 API 的提交，必须先按双库备份流程备份，并在 API 更新后重新通过管理员入口配置模型。

更新前完成双库备份，保存旧的 `HARU_RELEASE` 和镜像。切换经审阅的提交，更新 `.env.cloud` 的 `HARU_RELEASE`，先 build 成功，再 up；不要启动第二个 API 副本共享同一 SQLite 卷。API 重建后重新配置模型。发生数据库迁移时，回退须在独立新卷恢复匹配旧应用的双库备份，不能假定旧代码兼容新库。

轮换口令：

```sh
python3 deploy/cloud/configure.py --domain demo.your-domain.com --rotate-password
docker compose --env-file .env.cloud -f compose.cloud.yaml restart gateway
```

只重启 gateway，不丢失 API 的模型配置。Basic Auth 的凭据可能被浏览器缓存，没有可靠的应用内退出按钮；建议体验者使用独立隐私窗口，结束后关闭全部该隐私会话。撤销邀请需要轮换共享口令；无法单独撤销某个人。

日志做容量轮转，入口不启用访问日志，不转发访问口令给业务 API。不要开启请求正文/Authorization 调试日志。统一口令只适用于少量可信体验者，不提供用户隔离、操作归属审计或互联网抗滥用保证。

参考：[Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)、[口令认证](https://caddyserver.com/docs/caddyfile/directives/basic_auth)、[Nginx 请求限流](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)。
