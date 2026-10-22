# carryover

把 Claude 工作区搬到新账号或新电脑：Claude Code 会话、Cowork 任务、Projects、定时任务和记忆。只读源数据，不拷任何凭证。

[English](README.md)

## 为什么做这个

2026 年 10 月我停用了一个 Claude 账号，在同一台 Mac 上换新账号接着干。我在应用里没找到 Cowork 本地 Projects、项目记忆、定时任务的导出功能，只能去翻磁盘上的文件，一项一项重建。翻完才知道三件事：

1. 项目指令、每个项目的记忆、62 份定时任务提示词都在本地文件里，应用界面里找不到入口。
2. 新建的定时任务读不到旧提示词，因为 Cowork 把 `~/Documents/Claude` 当成自己的目录，会话进不去。
3. 迁移做到一半，Claude Code 启动了一次，顺手删掉了我 13 份会话记录。它默认删除 30 天前的本地记录（`cleanupPeriodDays`），我从没改过这个设置。

carryover 就是那天写的脚本整理出来的版本。

## 怎么用

需要 Python 3.9 以上，只用标准库。

```
pipx install git+https://github.com/lizhuojunx86/carryover

carryover scan                        # 盘点和预警，不写任何文件
carryover export ~/carryover-archive  # 生成归档
```

不安装也能跑：`PYTHONPATH=src python3 -m carryover scan`。

归档目录从 `INDEX.md` 看起：

- `claude-code/`：按项目文件夹整理的精简会话记录（只留你的提问和 Claude 的回答）、项目记忆、全局 CLAUDE.md 和个人技能
- `cowork/<账号>-<组织>/`：全部任务的精简记录和产出文件；每个 Project 一份 `RESTORE.md`（名称、文件夹、指令、记忆、第一条任务的提示词）；`scheduled-tasks/TASKS.md` 列出每个定时任务的计划、文件夹、最近运行和全部提示词
- `manifest.json`：写了哪些文件、来源在哪，跳过了哪些文件、为什么跳过

在新账号里重建一个 Project，照 `RESTORE.md` 粘贴四次：名称、文件夹、指令，再把第一条任务的提示词发给 Claude，让它读旧记忆、对照文件夹现状核一遍，只把仍然成立的写进新记忆。

## 安全

- 只读：源文件只以读方式打开；输出目录不能在任何源目录里面；输出目录非空时拒绝写入（除非加 `--force`）。
- 会话元数据里还有系统提示词、连接器配置（含服务器 URL）、授权状态。carryover 只读其中 12 个指定字段，其余一概不碰。
- 像凭证的文件一律不拷：`.env*`、`*.pem`、`*.key`、`id_rsa`、`credentials.json`、Cookie 库等；`~/.claude.json` 从不打开；`~/.claude/settings.json` 只读 `cleanupPeriodDays` 和顶层键名，不拷贝。
- carryover 自己写出的文本（会话记录、记忆、指令、提示词）会遮盖常见密钥格式：Anthropic、OpenAI、GitHub、AWS、Slack、Google、Stripe 的 key，JWT，私钥块，Bearer token，`password=` 这类赋值。遮盖只是兜底，分享前自己再看一遍。
- 产出文件原样拷贝，不做遮盖。

## 搬不走的

登录状态和连接器授权、插件，以及只在云端的东西：claude.ai 的 Project 文档、聊天记录、云端定时任务和它们的运行日志。这些要趁旧账号还能登录时用官方数据导出。

## 状态

v0.1.0。在 macOS（Python 3.9、3.13）和 Linux 上测过，Windows 路径写了但没测。Cowork 的目录结构是截至 2026 年 10 月桌面版的实际情况，不是公开格式，以后可能变。

与 Anthropic 无关。MIT 许可。
