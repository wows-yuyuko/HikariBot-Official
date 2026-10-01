## 简介

战舰世界水表BOT，基于Nonebot2，适配QQ官方机器人 水表人，出击！wws me recent！！！

交流群: 967546463
- 注意: QQ群的@处理只在全量消息的环境下生效
- 首次使用会自动下载 playwright chromium 浏览器（用于模板渲染截图）
- 建议在2G或以上内存的机器上部署 低于2G的在渲染大量数据时容易崩溃
- 本地部署推荐websocket模式 云服务器推荐webhook 具体使用参考QQ机器人官方文档

## 适配器选择（BOT_ADAPTER）

同一进程**只运行一个适配器**，在 `.env.prod` 里二选一：

| BOT_ADAPTER | 说明 | 上报给 API 的平台标识 |
| --- | --- | --- |
| `qq_official`（默认） | QQ 官方机器人 | `QQ_OFFICIAL` |
| `onebot11` | OneBot V11，仅 WebSocket 接入（正/反均可） | `QQ` |

- 业务代码不直接依赖任何具体适配器 —— 事件分类、@ 解析、发图方式、markdown 能力统一经
  `hikari_bot/plugins/hikari_bot_qq_official/adapters/` 适配层，新增适配器只需在该层实现一组同名接口。

### OneBot V11 接入

只支持 WebSocket，两个方向任选（也可同时开启）：

| 方向 | 谁主动连接 | 怎么配 |
| --- | --- | --- |
| 反向 WS（推荐） | 实现端连机器人 | 无需额外配置。端点 `ws://<本机IP>:<PORT>/onebot/v11/ws`，实现端需带 `X-Self-ID` 头 |
| 正向 WS | 机器人连实现端 | `ONEBOT_WS_URLS = ["ws://127.0.0.1:3001"]`（JSON 数组写法，可多个） |

- 鉴权用 `ONEBOT_ACCESS_TOKEN`，需与实现端一致；留空表示不校验。
- 两个方向依赖 driver 能力：反向需 ASGI、正向需 WebSocketClient。本项目默认的
  `DRIVER=~fastapi+~httpx+~websockets` 已同时满足；若只留 `~fastapi`，正向 WS 会被忽略并在启动日志里告警。

> 已知限制：V11 协议没有定义「收到文件」的消息段，`BOT_ENABLE_FILE_LISTEN` 能否生效取决于实现端是否下发 `file` 段。

## 文件消息处理

机器人对文件处理使用外部插件的方式 模板在根目录的template里面的file_handler.py 改好后复制到hikari_bot.plugins.hikari_bot_qq_official.bot.file_listener文件夹下面 里面有个file.py文件放一起就行了 然后启动机器人 在控制台看见

插件加载是扫描``file_handler-``开头的文件

插件名称规约 前缀必须是``file_handler-`` 比如 ``file_handler-test.py``

## 文件处理插件编写教程

参考``template``文件夹里面的``file_handler.py``

新建一个``file_handler-你的插件名.py``

实现你自己的相关处理逻辑就行了

## 克隆与依赖同步

> 本项目通过 git 子模块管理 `hikari_core`（战舰世界 SDK），克隆 / 同步时请带上子模块：

```bash
# 克隆（自动拉取 hikari_core 子模块）
git clone --recurse-submodules <本仓库地址>

# 若已克隆但子模块为空，初始化拉取
git submodule update --init --recursive

# 日常同步（先配置一次，之后 git pull 会顺带更新子模块）
git config submodule.recurse true
git pull

# 或将子模块手动更新到远端最新提交
git submodule update --remote --force
```

## Linux 部署（uv 方案）

> 以 Ubuntu / Debian 为例。部署使用 [uv](https://docs.astral.sh/uv/) 在项目内创建 **完全隔离** 的虚拟环境（生成在项目内 `.venv`），不污染系统 Python。依赖由 uv 解析安装（锁文件 `uv.lock` 未纳入版本控制，首次部署时生成）。本机有 Python 3.11/3.12 可直接使用；没有则脚本自动用 uv 下载隔离的 Python 3.11。

### 1. 克隆代码（带 hikari_core 子模块）

```bash
git clone --recurse-submodules https://github.com/wows-yuyuko/HikariBot-Official.git
cd HikariBot-Official
# 若克隆时忘了带子模块，执行：git submodule update --init --recursive
```

### 2. 一键部署

```bash
./deploy.sh
```

脚本自动完成：

1. 检查本机 Python（要求 `>=3.11,<3.13`）：符合要求则 **询问**是否使用本机 Python 构建（默认是）；不符合或选否，则自动用 **uv 下载隔离的 Python 3.11**
2. 初始化 `hikari_core` 子模块
3. 安装 uv（若缺失，优先国内镜像 `uv.agentsmirror.com`，失败回退官方安装器）
4. 在项目内创建隔离环境 `.venv`，并安装依赖（`uv.lock` 缺失时现场解析并生成，之后复用）
5. 安装 Playwright Chromium 及系统运行库、中文字体（需 sudo）
6. 生成 `.env.prod`（若不存在）

> 锁文件 `uv.lock` 未纳入版本控制：首次部署会解析依赖并落盘，之后 `uv sync` 会复用它，仅当 `pyproject.toml` 改动时才重新解析。若想强制按现有锁文件安装（不改动锁文件），改用 `uv sync --frozen`。

> 国内加速：uv 本体安装优先走国内镜像 `uv.agentsmirror.com`（失败自动回退官方源）；uv 下载 Python 默认走南京大学 `mirror.nju.edu.cn` 的 github-release 镜像。如需更换 Python 镜像，先 `export UV_PYTHON_INSTALL_MIRROR=<镜像地址>` 再运行 `./deploy.sh`（脚本会尊重你的设置）。

### 3. 配置环境变量

```bash
vi .env.prod
```

必填项：

- `QQ_BOTS` 中的 `id` / `token` / `secret`：QQ 官方机器人凭证(`token`在新版本bot已经过时了 可以不填)
- `API_TOKEN`：战舰世界 API 平台 token（格式 `数字:字符串`）
- `SUPERUSERS`：你的 QQ 号
- `HOST` / `PORT`：默认 `0.0.0.0:9999`，云服务器需在安全组放行对应端口

### 4. 启停管理

```bash
./service.sh start     # 启动（后台运行）
./service.sh status    # 查看状态
./service.sh restart   # 重启
./service.sh stop      # 停止
```

- 进程后台运行（通过 `nb run` 启动，即 `uv run --no-sync nb run`），标准输出/错误日志写入 `logs/bot.log`（机器人自身日志在 `logs/info.log`）
- 生产环境建议用 systemd 托管（可选）：

```ini
# /etc/systemd/system/hikaribot.service
[Unit]
Description=HikariBot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/HikariBot-Official
ExecStart=/path/to/HikariBot-Official/.venv/bin/nb run
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now hikaribot
```

### 5. 更新

```bash
git config submodule.recurse true   # 配置一次，之后 git pull 会顺带更新子模块
git pull
git submodule update --remote       # 手动将 hikari_core 更新到远端最新
uv sync                             # 依赖有变动时按 uv.lock 同步
./service.sh restart                # 重启生效
```

### 6. 常见问题

- 中文字体显示异常：见下方「Ubuntu系统下部署字体不正常」一节
- `ZoneInfoNotFoundError` / 鉴权失败：见「可能会遇到的问题」
- 机器人群里发送非@指令没响应 请在手机QQ端点击机器人资料设置全量消息获取 (仅群主可以设置)
- webhook机器人收不到部分小消息 请在https://q.qq.com/qqbot/dashboard选择你的机器人,开发设置 webhook设置下面的消息推送选择全部推送

## Windows 离线包（CI 自动构建）

> 通过 GitHub Actions 自动打包：内置 uv + 托管 Python 3.11 + 依赖缓存 + Chromium 浏览器， **免安装、可离线运行**（与 QQ 官方平台通信需联网）。

### 获取

- 推送 `v*` 标签（如 `git tag v1.0.0 && git push --tags`）自动构建并发布到 **GitHub Release**
- 或到仓库 Actions 页面手动点击 "Run workflow"

### 使用

1. 下载 `HikariBot-Windows.zip` 并解压（ **解压后请勿移动整个文件夹**）
2. 复制 `.env.prod-example` 为 `.env.prod` 并填写（`QQ_BOTS` / `API_TOKEN` / `SUPERUSERS`）
3. 双击 `start.bat` 启动（首次运行会用包内 uv 纯离线创建 `.venv`，无需联网、无需预先安装 Python）

### 包内结构与启动原理

| 目录 / 文件 | 作用 |
| --- | --- |
| `uv.exe` | uv 可执行文件，负责建环境和跑命令 |
| `uv-python/` | 托管 Python 3.11（可迁移的独立解释器） |
| `uv-cache/` | 全部依赖的 wheel 缓存，离线安装的来源 |
| `ms-playwright/` | Chromium 浏览器（模板渲染截图用） |

`start.bat` 把 `UV_PYTHON_INSTALL_DIR` / `UV_CACHE_DIR` / `PLAYWRIGHT_BROWSERS_PATH` 指向上述目录，
并设置 `UV_PYTHON_PREFERENCE=only-managed` 保证只用包内 Python；随后执行 `uv sync --offline` 建立 `.venv`，
再以 `uv run --no-sync nb run` 启动。离线初始化失败时会自动回退到联网安装。

### 更新

下载新版 zip，保留旧包中的 `accounts`、`data`、`.env.prod`，覆盖解压即可。

## 可能会遇到的问题

### 出现ZoneInfoNotFoundError报错

>
>您可以在[这里](https://github.com/nonebot/nonebot2/issues/78)找到相关解决办法
>

### Recent和绑定提示'鉴权失败'

1. 检查Token是否配置正确，token格式为`XXXXX:XXXXXX`
2. 如果配置正确可能是Token失效了，请重新申请

### Ubuntu系统下部署字体不正常 (针对一些云服务器的Ubuntu镜像，不保证成功，只是提供一个解决方案)

1. 执行以下命令，完善字体库并将中文设置成默认语言（部分Ubuntu可能不需要该步骤，可直接从第二步开始）

  ```
  sudo apt install fonts-noto  
  sudo locale-gen zh_CN zh_CN.UTF-8  
  sudo update-locale LC_ALL=zh_CN.UTF-8 LANG=zh_CN.UTF-8  
  sudo fc-cache -fv
  ```

2. 在你的Windows电脑上打开`C:\Windows\fonts`文件夹，找到里面的微软雅黑字体，将其复制出来，放在任意目录，应该会得到`msyh.ttc`，`mshybd.ttc`，`msyhl.ttc`三个文件。（不会有人还用Win7吧？）

3. 进入到`/usr/share/fonts`文件夹下，创建一个文件夹命名为`msyh`，然后进入其中

  ```
  cd /usr/share/fonts 
  sudo mkdir msyh 
  cd msyh
  ```

4. 将三个字体文件上传到`msyh`文件夹中 (过程中遇到的问题请自行解决)

5. 执行以下命令（此时你应该是在`msyh`文件夹下），加载字体

  ```
  sudo mkfontscale 
  sudo mkfontdir 
  sudo fc-cache -fv
  ```

6. （可选，若不正常可尝试）重启Hikari。

## 贡献代码

请向dev分支提交PR

## 鸣谢

感谢以下开发者及项目做出的贡献与支持

<a href="https://github.com/wows-yuyuko/HikariBot-Official/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=wows-yuyuko/HikariBot-Official" />
</a>

[Nonebot2](https://github.com/nonebot/nonebot2)  
[go-cqhttp](https://github.com/Mrs4s/go-cqhttp)  
[战舰世界API平台](https://wows.shinoaki.com/)

## 开源相关

MIT 修改、分发代码时请保留原作者相关信息

## 赞助

<a href="https://afdian.net/a/JustOneSummer?tab=home"><img style="width: 100px; height: 100px;" src="/wows-yuyuko.png" alt="afdian" ></a>
