<!-- markdownlint-disable MD033 MD041 -->

## 简介

战舰世界水表BOT，基于Nonebot2，适配QQ官方机器人
水表人，出击！wws me recent！！！  

交流群: 967546463

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
git submodule update --remote
```


## Linux 部署

> 以 Ubuntu / Debian 为例；CentOS 系可参考 `manage.sh install` 中的 yum 依赖列表。

### 1. 环境要求

- Python **3.11**（项目要求 `>=3.11,<3.13`，推荐 3.11）
- Git、能够访问外网

### 2. 克隆代码（带 hikari_core 子模块）

```bash
git clone --recurse-submodules https://github.com/wows-yuyuko/HikariBot-Official.git
cd HikariBot-Official
# 若克隆时忘了带子模块，执行：git submodule update --init --recursive
```

### 3. 安装系统依赖（含中文字体）

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip git fonts-noto
```

### 4. 创建虚拟环境并安装项目依赖

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .                      # 按 pyproject.toml 安装全部依赖

# 或使用 poetry（按 poetry.lock 精确安装）：
# pip install poetry && poetry install
```

### 5. 安装 Playwright 浏览器及运行库

```bash
playwright install chromium
sudo playwright install-deps chromium   # 自动安装浏览器系统运行库（Ubuntu/Debian）
```

> `install-deps` 不可用或非 Debian 系时，可手动安装 `manage.sh install` 中列出的 apt/yum 包。

### 6. 配置环境变量

```bash
cp .env.prod-example .env.prod
vi .env.prod
```

必填项：

- `QQ_BOTS` 中的 `id` / `token` / `secret`：QQ 官方机器人凭证
- `API_TOKEN`：战舰世界 API 平台 token（格式 `数字:字符串`）
- `SUPERUSERS`：你的 QQ 号
- `HOST` / `PORT`：默认 `0.0.0.0:9999`，云服务器需在安全组放行对应端口

### 7. 启动

```bash
python bot.py
```

> 等价于 `nb run`；启动时会自动加载 `hikari_core` 子模块源码。需要后台常驻可加 `nohup python bot.py > bot.log 2>&1 &`，或自行配置 systemd 服务。

### 8. 更新

```bash
git config submodule.recurse true   # 配置一次，之后 git pull 会顺带更新子模块
git pull
git submodule update --remote       # 手动将 hikari_core 更新到远端最新
```

> `manage.sh` 提供 `./manage.sh install` / `./manage.sh start` / `./manage.sh update` 快捷命令（基于 `nb run`），但其 `update` **不会**更新子模块，请按上面手动方式同步 hikari_core。

### 9. 常见问题

- 中文字体显示异常：见下方「Ubuntu系统下部署字体不正常」一节
- `ZoneInfoNotFoundError` / 鉴权失败：见「可能会遇到的问题」


## 特色

- [x] 账号总体、单船、近期战绩
- [x] 全指令支持参数乱序
- [x] 快速切换绑定账号
- [x] 支持@快速查询
- [x] 全异步，高并发下性能更优
- [x] 适配官方BOT


## 更新
实验性更新指令：`wws 更新Hikari`
请确保在能登录上服务器的情况下使用
以下是旧更新方法
1. 按不同版本
   - Windows一键包：下载最新一键包，复制旧版本中`accounts`文件夹和`env.prod`文件替换至新版文件夹中即可
   - 完整版：以管理员身份运行`更新.bat`或执行`./manage.sh update`
      >等效于在cmd中执行如下代码
      ```
      pip install --upgrade hikari-bot
      git pull
      ```
   - 插件版：在cmd中执行如下代码
      ```
      pip install --upgrade hikari-bot
      ```
2. **对比`.env.prod-example`中新增的配置项，并同步至你本地的`env.prod`**
    - install结束后会打印当前版本
    - 您也可以通过`pip show hikari-bot`查看当前Hikari版本
    - 如果没有更新到最新版请等待一会儿，镜像站一般每五分钟同步
    - 从0.3.2.2版本开始，您没有填写的配置将按.env文件中的默认配置执行，具体逻辑为
      - 私聊、频道默认禁用
      - 群聊默认开启，默认屏蔽官方交流群



## 可能会遇到的问题

### 出现ZoneInfoNotFoundError报错
>
>您可以在[这里](https://github.com/nonebot/nonebot2/issues/78)找到相关解决办法
>
### Recent和绑定提示'鉴权失败'
1. 检查Token是否配置正确，token格式为`XXXXX:XXXXXX`
2. 如果配置正确可能是Token失效了，请重新申请



### Ubuntu系统下部署字体不正常(针对一些云服务器的Ubuntu镜像，不保证成功，只是提供一个解决方案)
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
  
  4. 将三个字体文件上传到`msyh`文件夹中(过程中遇到的问题请自行解决)

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

<a href="https://github.com//benx1n/HikariBot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=benx1n/HikariBot" />
</a>

[Nonebot2](https://github.com/nonebot/nonebot2)  
[go-cqhttp](https://github.com/Mrs4s/go-cqhttp)  
[战舰世界API平台](https://wows.shinoaki.com/)  

## 开源相关
MIT
修改、分发代码时请保留原作者相关信息

## 赞助
<p align="left">
  <a href="https://afdian.net/a/JustOneSummer?tab=home"><img src="https://hikari-resource.oss-cn-shanghai.aliyuncs.com/%E7%88%B1%E5%8F%91%E7%94%B5.png" alt="afdian" ></a>
</p>
