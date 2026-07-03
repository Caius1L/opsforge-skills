# OpsForge 发布 Skill 使用说明

## 1. 安装指令

在本机 Codex 环境中执行：

```bash
npx --yes --package git+ssh://git@github.com/Caius1L/opsforge-skills.git#main \
  opsforge-skills install opsforge-release
```

安装完成后，skill 会写入：

```text
~/.codex/skills/opsforge-release
```

OpsForge 登录信息会在首次使用后缓存到：

```text
~/.opsforge-skills/config.json
```

## 2. 使用前提

需要在具体服务仓库目录下使用，例如：

```bash
cd /Users/lancheng/IdeaProjects/sop
```

然后直接对 Codex 说：

```text
发布到腾讯云测试
```

也可以说：

```text
发布当前分支到腾讯云测试
```

skill 会自动识别：

| 项目 | 说明 |
| --- | --- |
| 应用名 | 从当前 Git 仓库 remote 推断，例如 `sop` |
| 发布分支 | 当前分支 |
| 发布环境 | 腾讯云测试，对应 `tencent-test` |
| 发布方式 | 只发布远端当前分支，不带本地未提交文件 |

## 3. 首次使用流程

首次本机没有 OpsForge 登录凭据时，流程是两轮。

### 第一轮：发起发布

用户输入：

```text
发布到腾讯云测试
```

skill 会完成预检：

| 检查项 | 行为 |
| --- | --- |
| 当前应用 | 自动识别 |
| 当前分支 | 自动识别 |
| 远端分支是否存在 | 如果不存在，自动 push 当前 HEAD 到远端同名分支 |
| 本地未跟踪文件 | 忽略，不参与发布 |
| OpsForge 登录状态 | 如果没有凭据，会要求输入账号密码 |

此时会提示你输入：

```text
username=你的用户名
password=你的密码
```

### 第二轮：输入账号密码后直接发布

用户输入：

```text
username=你的用户名
password=你的密码
```

skill 会：

1. 登录 OpsForge。
2. 缓存账号密码到 `~/.opsforge-skills/config.json`。
3. 获取 session / cookie。
4. 直接触发腾讯云测试发布。
5. 返回发布结果。

不会再要求你回复 `确认发布`。

## 4. 后续使用流程

后续本机已经有 `~/.opsforge-skills/config.json` 后，通常只需要一轮。

用户输入：

```text
发布到腾讯云测试
```

skill 会直接：

1. 识别当前应用和当前分支。
2. 检查远端分支是否存在。
3. 必要时自动 push 当前 HEAD 到远端。
4. 自动登录或刷新 session。
5. 触发 OpsForge 发布。
6. 返回发布结果。

## 5. 首次使用和后续使用区别

| 场景 | 用户需要输入几轮 | 是否需要账号密码 | 是否需要确认发布 |
| --- | ---: | --- | --- |
| 首次使用 | 2 轮 | 需要 | 不需要 |
| 后续使用 | 1 轮 | 不需要，自动读取缓存 | 不需要 |
| session 过期 | 1 轮 | 不需要，使用缓存账号密码自动重新登录 | 不需要 |

## 6. 重要边界

| 边界 | 说明 |
| --- | --- |
| 只支持非生产发布 | 如果用户要求发布生产，skill 会拒绝 |
| 当前只发布腾讯云测试 | 默认环境是 `tencent-test` |
| 不发布本地未提交内容 | 发布的是当前分支远端 HEAD |
| 远端分支不存在会自动 push | 只 push 当前 HEAD 到远端同名分支，不会把未提交文件带上去 |
| 密码不会在后续对话中展示 | 首次输入后会缓存到本地配置文件 |

## 7. 推荐使用话术

首次或后续都可以直接说：

```text
发布到腾讯云测试
```

不需要说：

```text
确认发布
```

也不需要说：

```text
空发
```

当前 skill 的设计是：用户表达 `发布到腾讯云测试` 即视为授权发布测试环境。
