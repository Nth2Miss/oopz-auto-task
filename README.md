# Oopz 自动签到 · 每日星辉任务

一键完成 Oopz 每日签到与社区星辉任务，支持服务器无人值守定时运行。

<img src="https://img.shields.io/badge/Python-3.7%2B-3776ab?logo=python&logoColor=white" alt="Python 3.7+">
<img src="https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen" alt="dependencies: stdlib only">
<img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="platform">
<img src="https://img.shields.io/badge/license-MIT-blue" alt="license: MIT">

通过复刻 Oopz Web 端的请求签名算法直接调用官方 API，完成手机端每日签到与全部社区星辉任务，不需要抓包工具，不留后台进程。

## 功能特性

- **每日签到** —— 星辉签到，连续签到 7 天后每日可得 10 星辉。
- **每日任务全自动** —— 浏览 10 篇 → 点赞 3 篇 → 评论 1 篇 → 分享 1 篇 → 发布 1 篇笔记 → 自动领取全部奖励。
- **发布内容自动生成** —— 正文取自[一言 API](https://developer.hitokoto.cn/sentence/)（自动拼接保证 ≥ 20 字），配图取自[必应每日一图](https://cn.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1)，上传后随笔记一并发布。
- **三种登录方式** —— 密码/ 微信扫码（二维码直接渲染在终端）/ 短信验证码。
- **凭证自动续期** —— 密码登录后 token 失效时自动重新登录。

## 环境要求

- Python 3.7 或更高版本
- 可选依赖：[`qrcode`](https://pypi.org/project/qrcode/)（仅 `login-wechat` 在终端渲染二维码时需要）

## 安装

```bash
git clone https://github.com/<your-name>/oopz-auto-task.git
cd oopz-auto-task

# 可选：仅微信扫码登录需要
pip install qrcode
```

## 快速开始

### 1. 登录

```bash
# 方式一：密码登录（推荐，全自动，token 过期自动续期）
python oopz_sign.py login-password --phone 13812345678 --password 你的密码

# 方式二：微信扫码
python oopz_sign.py login-wechat

# 方式三：短信验证码（需先在手机 App 里点一次“获取验证码”）
python oopz_sign.py login-sms --phone 13812345678 --code 123456
```

登录成功后凭证写入 `oopz_config.json`，后续所有命令自动复用。

### 2. 签到 / 做任务

```bash
python oopz_sign.py sign     # 签到（凭证失效时自动重新登录）
python oopz_sign.py tasks    # 每日任务全流程 + 自动领奖
```

### 3. 查看状态

```bash
python oopz_sign.py whoami   # 校验凭证是否有效
python oopz_sign.py check    # 查询签到 / 任务进度
```

## 命令一览

| 命令                                             | 说明                                                             |
| ---------------------------------------------- | -------------------------------------------------------------- |
| `sign`                                         | **一站式签到**：校验凭证（失效自动重登）→ 执行签到                                   |
| `tasks`                                        | **一站式每日任务**：浏览 10 篇 → 点赞 3 篇 → 评论 1 篇 → 分享 1 篇 → 发布 1 篇 → 领取奖励 |
| `publish [正文]`                                 | 单独发布一篇笔记（不填正文时自动从一言 API 生成，配图自动获取）                             |
| `login-password --phone <手机号> --password <密码>` | 密码登录（全自动，推荐）                                                   |
| `login-wechat [--timeout 180]`                 | 微信扫码登录（终端渲染真二维码）                                               |
| `login-sms --phone <手机号> --code <验证码>`         | 短信验证码登录                                                        |
| `login`                                        | 交互式登录入口（优先密码登录，否则走短信验证码）                                       |
| `login-web`                                    | 浏览器登录助手（需 Node.js，见 `tools/oopz_login.js`，一般用不到）               |
| `whoami`                                       | 校验凭证有效性                                                        |
| `check`                                        | 查询签到 / 任务状态                                                    |
| `probe`                                        | 逐接口探测真实响应（排障用）                                                 |
| `loop --at HH:MM`                              | 常驻进程，每天定点签到（推荐用系统定时任务替代）                                       |

## 凭证与配置

### 凭证来源优先级

| 优先级 | 来源                                        | 适用场景                  |
| --- | ----------------------------------------- | --------------------- |
| 1   | 环境变量 `OOPZ_TOKEN` / `OOPZ_UID`            | 临时运行、CI；不落盘           |
| 2   | 脚本顶部 `ACCOUNT_PHONE` / `ACCOUNT_PASSWORD` | 服务器无人值守（token 失效自动重登） |
| 3   | `oopz_config.json`                        | `login-*` 命令成功后自动写入   |

### 服务器无人值守（推荐配置）

在 `oopz_sign.py` 顶部填入账号密码：

```python
# oopz_sign.py 顶部
ACCOUNT_PHONE = "13812345678"
ACCOUNT_PASSWORD = "your_password_here"
```

配置后，`sign` / `tasks` 会在 token 缺失或失效时自动使用该账号密码重新登录，全程无需人工介入：

```
python oopz_sign.py sign
    ├─ oopz_config.json 中 token 有效   → 直接执行
    ├─ 无 token / token 失效            → 使用顶部账号密码自动登录 → 执行
    └─ 密码错误 / 触发风控              → 明确报错退出（不会静默失败）
```

若未填写顶部字段，脚本会回退使用 `oopz_config.json` 中保存的 `login_phone` / `login_password`（密码登录时自动存入）。

> `oopz_config.json` 内含账号 token，密码登录时还包含明文密码，等同于账号凭证，**切勿提交到公开仓库** 

## 定时任务

### Linux（cron）

```bash
# 每天 8:30 执行签到 + 全部每日任务 + 领奖
30 8 * * * cd /path/to/oopz-auto-task && python3 oopz_sign.py sign >> oopz_sign.log 2>&1 && sleep 5 python3 oopz_sign.py tasks >> oopz_sign.log 2>&1
```

### Windows（任务计划程序）

新建任务 → 操作：程序填 `python`，参数填 `oopz_sign.py sign`，起始目录填项目目录。

> [!TIP]
> 微信登录的凭证过期后无法自动续期（扫码无法无人值守完成），需要重新扫码一次。**要彻底无人值守，请使用密码登录。**

## 工作原理

签名与接口协议逆向自 Oopz Web 端（`web.oopz.cn` 的 Flutter Web 产物 `main.dart.js`）。

### 请求签名

```
sign = Base64( RSA_PKCS1v15_SHA256( hex(MD5(路径含query + JSON请求体)) + 毫秒时间戳 ) )
```

- 路径包含 query string，无请求体时使用空字符串
- RSA-2048 私钥硬编码在客户端中（脚本已内置），填充方式 PKCS#1 v1.5

### 必需请求头

| 请求头                                  | 值                           |
| ------------------------------------ | --------------------------- |
| `oopz-sign`                          | 上方算法计算出的签名                  |
| `oopz-time`                          | 毫秒时间戳（须与签名内保持一致）            |
| `oopz-request-id` / `oopz-device-id` | UUID                        |
| `oopz-platform`                      | `windows`                   |
| `oopz-channel`                       | `Web`                       |
| `oopz-app-version-number`            | `88053`                     |
| `oopz-web`                           | `true`                      |
| `oopz-signature`                     | 登录 token（注意：此头放 token，不是签名） |
| `oopz-person`                        | 用户 uid                      |

### 返回码

| HTTP | 含义                 |
| ---- | ------------------ |
| 401  | 签名不正确              |
| 403  | 缺少请求头              |
| 405  | 请求方法不对             |
| 428  | 需要登录 / token 缺失或无效 |

### 每日任务接口

| 任务   | 接口                                         | 关键字段                                                                                                                                                                                          |
| ---- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 签到   | `POST /task/v1/signIn`                     | `{}`；成功返回 `data.awardType/awardNum`（星辉），重复签到返回「今日已签到」。⚠️ `/user_points/v1/sign_in` 是空接口，永远返回成功但服务端不记账，签到日历不会更新                                                    |
| 任务进度 | `GET /task/v1/detail`                      | `signInEveryDay`：连续签到天数 `signInNum`、今日是否已签 `isTodaySignIn`；`taskEveryDay.list[]`：id 9=发布 10=浏览 11=点赞 12=评论 13=分享；state 0=未完成 1=可领取 2=已领取                                                                                                                 |
| 浏览计数 | `GET /community/v1/detail?momentId=X`      | 逐篇拉取详情才计数（只拉 feed 不算）                                                                                                                                                                         |
| 笔记列表 | `GET /community/v1/feed?pageSize=N`        | 每页固定返回 20 篇                                                                                                                                                                                   |
| 点赞   | `POST /community/v1/like`                  | `{momentId, author, like: 1}`（取消点赞为 `like: 2`）                                                                                                                                                |
| 评论   | `POST /community/v1/moment/comment_commit` | `{momentId, content}`                                                                                                                                                                         |
| 分享   | `POST /community/v1/share`                 | `{momentId, author}`                                                                                                                                                                          |
| 发布   | `POST /community/v1/publish`               | `{groupType: "article", title, content(≥20字), imageList: [{cover, resource, resourceType: "IMAGE", sourceResource, height, width}]}`。⚠️ 字段名必须是 `imageList`（写成 `resources` 会返回「上传类型错误」）；图片地址必须保留 hostUrl 上的 `?sign=` 签名                                                                                                                                  |
| 图片上传 | `POST /v1/upload/getCommunityImagePreSignUrl` → `PUT` 到 COS | 请求 `{fileName, contentType}`，响应 `data.url`（COS 预签名地址，3 分钟内有效）与 `data.hostUrl`（CDN 地址，带 `sign` 签名）；把图片 `PUT` 到 `data.url`，发布时提交**完整的** `data.hostUrl` |
| 领奖   | `POST /task/v1/receive`                    | `{taskId}`；未完成时返回「领取失败」属正常，跳过即可                                                                                                                                                               |

<details><summary>逆向路径（点击展开）</summary>
<ol>
<li><strong>APK 静态分析</strong> —— 从 <code>libapp.so</code>（Flutter Dart AOT，21 MB）提取字符串，定位 API 端点、<code>Oopz-*</code> 请求头与签名相关模块（<code>xx_mobile/etc/hash.dart</code>、<code>etc/signature_selector.dart</code>、<code>http_api/src/header.dart</code>）。但 Dart AOT 为机器码，签名逻辑读不出来。</li>
<li><strong>发现 Web 版</strong> —— 官网 JS 中出现 <code>web.oopz.cn</code>，它是 Flutter Web（Dart → JS，明文可读），分析难度大幅降低。</li>
<li><strong>追出签名链</strong> —— 在 6.3 MB 的 <code>main.dart.js</code> 中还原调用链：<pre><code>hVa(url, body, reqId, token, ver, uid, time)
  → aaw(body, time, reqId, token, uid, url, ver)
    → bRa(url, body, time)          ← 真正的签名实现</code></pre></li>
<li><strong>提取硬编码私钥</strong> —— <code>aC1()</code> 将客户端内置的 PKCS#8 私钥分 4 段 + 3 个内嵌片段拼接后解析，全部提取后还原出完整 RSA-2048 参数。</li>
<li><strong>真实样本验证</strong> —— 使用 CDP 在真实 Chrome 中 hook 网络，抓取 3 个真实签名，用公钥解密还原 <code>DigestInfo</code> 反推输入拼接，<strong>3/3 完全匹配</strong>。</li>
</ol>
</details>

## 目录结构

```
.
├── oopz_sign.py          # 主脚本（登录 / 签到 / 每日任务，已内置签名私钥）
├── oopz_config.json      # 登录凭证（login 后自动生成，已被 .gitignore 排除）
├── .gitignore
├── LICENSE
└── tools/
    ├── oopz_login.js     # 备用登录助手：浏览器方式自动截获凭证（需 Node）
    ├── assemble_key.py   # 从 main.dart.js 提取私钥的分析脚本（存档）
    ├── rsa_params.txt    # 提取出的 RSA n/e/d 参数（存档，主脚本已内嵌同款）
    └── oopz_priv.der     # 客户端硬编码的 PKCS#8 私钥（存档）
```

## 常见问题

**`whoami` 返回 428，提示 token 失效？**
token 已过期。重新登录一次即可；若配置了密码登录，`sign` / `tasks` 会自动重新登录并更新 `oopz_config.json`。

**`tasks` 报「未取到笔记 id」？**
运行 `python oopz_sign.py probe` 查看接口原始响应，确认 `/community/v1/feed` 返回的字段名后再适配。

**签到提示成功，但 App 里签到日历没变化？**
旧版本的脚本调用了 `/user_points/v1/sign_in`，它是空接口：永远返回 `{"status":true,"data":true}` 但服务端不记账。真实签到接口是 `POST /task/v1/signIn`（当前版本已修正）。可用 `python oopz_sign.py check` 核对「今日已签到 / 连续签到天数」。

**发布笔记报「上传类型错误」？**
两个原因：① 资源字段名必须是 `imageList`（写成 `resources` / `image_list` 会被忽略）；② 图片地址必须保留 `getCommunityImagePreSignUrl` 返回的 `hostUrl` 上的 `?sign=` 签名，不能只取路径部分。当前版本已修正。

**微信扫码登录后凭证过期怎么办？**
微信扫码无法无人值守完成，需要重新扫一次；建议改用密码登录实现全自动续期。

**怎么在服务器上直接修改 `ACCOUNT_PHONE`？**
推荐用 `sed` 批量替换或直接编辑（`nano` / `vim`）；若担心密码明文落盘，可改用环境变量 `OOPZ_TOKEN`（但需自行处理过期后的更新）。

## 免责声明

- 本项目仅用于**学习交流与个人自动化**，请仅操作**你自己的账号**，不涉及任何越权行为。
- 使用自动化可能违反应用服务条款，请自行评估风险，并保持与人工使用相当的频率。
- 脚本仅复用客户端前端代码中公开可见的签名逻辑生成合法请求，**不包含任何人机验证绕过**，登录环节保留必要的人工操作。
- 因使用本工具产生的一切后果（包括但不限于账号封禁）由使用者自行承担。

## License

[MIT](LICENSE)
