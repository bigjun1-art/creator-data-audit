# 达人数据核查

`creator-data-audit` 是面向 Codex 的达人数据批量核验 Skill。它复用用户本人已经登录的营销平台页面，参数化核验达人身份、粉丝、类型、内容主题和近期作品表现，并生成带日期证据的可复核评估表。

当前巨量星图链路已经具备统一入口、批量执行、失败续跑、离线自测和飞书写入回读。小红书蒲公英适配仍处于首次真实样本验证阶段，不应视为已经完整支持。

> 非抖音、巨量星图、小红书、蒲公英或飞书官方项目。仅限核查自己或已获明确授权的数据，并遵守适用的平台规则和法律。

## 适用场景

- 批量核验抖音达人或巨量星图达人身份。
- 给达人名单补充平台数据、近期作品播放量和发布日期证据。
- 生成可回读验收的飞书达人评估表。
- 从检查点续跑失败或未完成的达人，不重复抓取已完成记录。

## 安全边界

- 不保存或导出密码、Cookie、Token、API Key、浏览器配置和登录会话。
- 不提交真实达人名单、账号 ID、飞书 token、业务表格、截图、日志或运行目录。
- 同名或身份不能唯一确认时标记为“未唯一匹配”，不猜填相似账号。
- 验证码、风险控制或登录确认出现时停止，不尝试绕过。
- 飞书发布必须先校验身份、记录数和列映射，写入后回读关键行。

## 安装

把下面这段直接发给支持 Skills 的 Agent：

```text
请使用 skill-installer 安装这个 GitHub Skill：
https://github.com/bigjun1-art/creator-data-audit

安装后检查 SKILL.md、scripts 和 references 是否完整，运行离线验证，但不要访问真实营销平台、抓取达人数据或写入飞书。
```

也可以将仓库目录复制到 Codex 的 Skills 目录，目录名保持为 `creator-data-audit`。具体执行边界见 [SKILL.md](SKILL.md)。

## 本地校验

需要 Python 3、Node.js 和 Pillow：

```bash
python3 -m pip install Pillow
node scripts/validate-repository.mjs
```

校验包含 Skill 结构、敏感信息模式、Python/Node/Bash 语法和完整离线自测，不会访问真实平台或写入飞书。

## 许可证

本仓库按 [MIT License](LICENSE) 开源。

## English summary

Codex Skill for authorized creator-data audits using an existing logged-in marketing-platform session. It provides parameterized Xingtu collection, strict identity matching, resumable checkpoints, dated evidence charts, optional serial Feishu publishing, and readback verification. No credentials, production identifiers, creator lists, screenshots, or business data are included.
