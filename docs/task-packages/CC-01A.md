# CC-01A — 管理员凭据与认证边界（迁移重建 Task Package）

本文件是 COORD-01 资料批次中的交接材料。它依据本机 ignored 资料
`_tmp_gui/cc01a-root/CC-01A-Review-Package.txt` 和实际入场差异重建已实施交付的
目标，**不是原始 CC-01A Task Package 的副本，也不代表原批准文字仍可追溯**。
原 Task Package/用户批准原文未在当前工作区找到；因此本文件不能追授新需求或新
权限。凡旧 Review 没有直接证据支持的要求，均保留为证据缺口，不能据此扩大范围。

当前批次与状态只见 [AI 指挥中心](../AI_COMMAND_CENTER.md)；本文件不维护平行状态。
批次冻结边界见 [COORD-01 v1](COORD-01.md)。

## 重建依据与目标

旧 Review 将 CC-01A 描述为一次公开仓库管理员认证清理：移除源码中的固定管理员
凭据，让部署者通过环境变量提供管理员密码；未配置时管理员登录关闭；TCP 与 Web
共用服务器端认证；管理员权限、Web token 和注销/删号行为绑定真实认证会话；公开
文档和测试同步纠偏。以下条目仅冻结这份历史交付的可追溯摘要，不能替代缺失的原
批准文本。

目标是让管理员权限只能来自部署侧凭据的服务器校验，同时保留普通用户、普通昵称
认领、聊天、Web 登录和既有管理员操作的行为边界。协议版本保持 1，认证消息字段
和线格式不因本任务改变。

## 冻结的重建需求

### 部署凭据与 fail-closed

- 管理员密码只从 `MOYU_ADMIN_PASSWORD` 读取；源码、配置默认值和 Hub 初始化不能
  回退到公开固定口令。
- 环境变量缺失、空字符串、纯空白或无效密码时不生成管理员校验值，管理员登录
  应拒绝；普通用户仍可使用。
- 管理员昵称可由 `MOYU_ADMIN_NICK` 配置，保留既有默认登录标识。配置值须去首尾
  空白并满足 1–20 字符；非法配置在启动时拒绝，错误不得回显配置值。
- 默认和当前管理员登录标识均保留为受保护标识，不能被普通首次认领占用；改名不
  得把旧标识变成普通账号。
- 配置对象的表示形式、错误、控制台提示、审计和快照不得输出实际密码；控制台只
  可提示如何配置环境变量。

### TCP、Web 与权限授予

- TCP HELLO 和 Web 登录继续经过同一服务器侧管理员密码校验；只有校验成功后由
  服务器设置 `Session.is_admin`，客户端提交的 `uid`、昵称、`is_admin` 或 token
  字段不能直接授予权限。
- Web 站点口令（若部署启用）与管理员/昵称密码字段保持隔离；站点口令不能替代
  管理员凭据。
- 管理员群管理、清理、踢人、隐身和其它既有权限继续由活跃的服务器会话逐项校验。
  普通用户的注册、登录、聊天和权限拒绝行为保留。
- 普通 `SET_PWD`/`/api/passwd` 路径不得修改或清除部署侧管理员凭据。

### Web token 与会话生命周期

- Web token 绑定原已认证的 Web `Session`，解析 token 时验证该对象仍处于 active；
  不能借同一 uid 的另一端或重登后的代表会话续权。
- 注销单端立即撤销该会话的 Web token；删号撤销该 uid 的全部相关端和 token，并
  保留既有服务器会话清理语义。
- `whoami`、SSE、REST 和管理员 API 使用同一活跃会话解析路径，不能从 token 直接
  还原 uid 后绕过会话校验。

### 文档、测试与兼容边界

- 桌面/Web 管理员界面和操作日志使用已认证操作者信息，不把固定昵称当作权限依据；
  协议注释与客户端权限注释反映“服务器授予”。
- 既有权限测试保留，不删除、跳过或弱化断言；新增凭据测试覆盖配置矩阵、真实
  TCP/HTTP 登录、token 绑定、删号/注销失效、普通用户路径和 secret 脱敏。
- 任务要求保留每文件独立进程门禁的原始失败和退出码。专项通过不能替代最终全量；
  全量失败不能被复测或重试抹掉。
- `PROTOCOL_VERSION` 保持 1；不新增账号系统、密码复杂度策略、热更新、secret
  管理服务或发布 EXE。

## 历史交付范围

入场快照显示 20 个 tracked 修改和 2 个 untracked 新文件，共 22 个文件；逐路径、
字节数和 SHA-256 见 [CC-01A 入场基线](../review-packages/CC-01A-baseline.md)。
旧 Review 将这 22 个文件作为管理员交付的历史入场快照；其中源码和相关测试有可见
管理员差异，下面 9 个文档/技能文件只是旧 Review 声称的配套范围。原批准文字缺失，
不能据此证明这 9 个文件逐文件获批，也不能把它们扩展为新的冻结需求：

- 源码：`config.py`、`server.py`、`web.py`、`client.py`、`client_core.py`、
  `protocol.py`。
- 测试：`tests/test_admin_credentials.py`、`tests/test_r53.py`、
  `tests/test_r54.py`、`tests/test_admin_groups.py`、
  `tests/test_admin_groups_web.py`、`tests/test_invis.py`、
  `tests/test_audit_server_security.py`。
- 文档/技能：`docs/管理员凭据与公开仓库安全.md`、`README.md`、
  `COLLABORATION.md`、`INVITE_FRIEND.md`、`PROJECT_MEMORY.md`、
  `docs/任务清单.md`、`.agents/skills/fish-assistant-dev/SKILL.md` 及其
  `references/invariants.md`、`references/project-map.md`。

当前 CC-01A 资料迁移只整理这份脱敏交接材料，不重新实现上述源码。入场 22 个文件
作为历史快照保留；COORD-01 另有明确允许主控整理 `COLLABORATION.md` 与
`PROJECT_MEMORY.md` 的文档增量，这两份增量由主控单独记录，本资料代理不修改它们。
其余 20 个入场文件在本批资料边界内应保持逐字节不变。

## 明确排除项

本重建包不授权 CC-01B 或其它 Roadmap，不授权修复 R26 频道事件等待、R43A 淡入
时序、账号数据清理、管理员多端踢人、完整游戏 UI、可选扩展、真实音频、EXE 发布
或任何真实用户数据。没有原批准文字时，不从 PROJECT_MEMORY 中夹带的 Excel、登录
窗或其它历史报告推导 CC-01A 新需求。

## 证据与验收边界

历史实现者不能自行验收。独立审查应从本文件、[CC-01A Review](../review-packages/CC-01A-r1.md)、
[入场基线](../review-packages/CC-01A-baseline.md)、实际 diff 和原始摘要开始，核对
命令、环境、计数、失败、退出码、版本绑定和敏感资料边界。接受条件还包括：

1. [CC-01A 入场基线](../review-packages/CC-01A-baseline.md) 永久保存原始 22 文件的
   路径、字节数、hash 和 patch；除 COORD-01 已批准单独记录的
   `COLLABORATION.md`/`PROJECT_MEMORY.md` 文档增量外，其余 20 个保护文件逐字节
   不变。本条是资料批次的边界检查，不是 CC-01A 应用验收或新增实现需求。
2. 历史专项、复测和两轮全量的真实失败如实保留；缺少原始日志、原命令或干净
   main 对照的地方明确标注缺口。
3. 资料链接、UTF-8 内容和 Git 空白检查通过；本批不以文档检查推出应用门禁通过。
4. CC-01A 的状态、下一动作、是否 ACCEPTED/MERGED 只由 [AI 指挥中心](../AI_COMMAND_CENTER.md)
   维护；本文件不产生验收结论。
