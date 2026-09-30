# 开发协作规范（COLLABORATION.md）

> 仓库：`https://github.com/mixmixla/321_FISH`
> 维护：mixmixla（主理人）+ 协作者（朋友）
> 适用：两人及以上共同开发「摸鱼助手（内部办公助手）」局域网 IM + 游戏客户端/服务器

---

## 1. 项目一句话

Windows 桌面端的局域网聊天 + 内置桌游应用：Tkinter 客户端（伪装成办公助手界面）、
自建 TCP 服务器（含网页端）、P2P 文件传输、语音通话、多款桌游。纯 Python 标准库。

## 2. 环境要求（双方必须一致，否则本地跑不起来）

| 项 | 要求 |
| --- | --- |
| 系统 | Windows 10 / 11（客户端依赖 tkinter、注册表深浅色、托盘等 Windows 特性） |
| Python | pyenv **3.14.5**（在项目根目录 `pyenv local 3.14.5`） |
| 第三方包 | 无（纯标准库；测试另需 pytest，`pip install pytest`） |
| 自检 | `python -c "import tkinter"` 不报错即通过 |

> 注意：本项目**不是跨平台**代码，不要引入 Linux/macOS 专用写法。

## 3. 怎么跑起来

```powershell
python run.py             # 全量测试门禁（提交前必须全绿）
python run.py server      # 启动服务器（默认 TCP 9527 / 网页 9529，可用环境变量覆盖）
python run.py client      # 启动客户端 GUI（可加 --host <服务器IP>）
python run.py build       # PyInstaller 打包 server.exe / client.exe
```

- 先起服务器再起客户端；开发时**各跑各的** server 即可（局域网互相联机是后话）。
- 手动冒烟脚本见根目录 `_smoke_*.py`；改到哪块功能就跑对应 smoke。

## 4. Git 工作流

### 4.1 分支约定

| 分支 | 用途 |
| --- | --- |
| `main` | 稳定分支。**禁止直接 push**，只通过 Pull Request 合并 |
| `feature/<简述>` | 新功能，如 `feature/r73-forward` |
| `fix/<简述>` | 修 bug，如 `fix/login-panel-overflow` |

动手前先 `git pull origin main`，避免基于过期代码开发。

### 4.2 提交信息规范

```
<类型>: <一句话说明>
```

- 类型：`feat` 新功能 / `fix` 修复 / `refactor` 重构 / `test` 测试 / `docs` 文档 / `style` 界面文案 / `chore` 杂务
- 示例：`fix: 登录窗服务器折叠面板高度溢出`、`feat: 图片消息支持转发`

### 4.3 合并流程（PR）

1. 从最新 `main` 开分支 → 开发 → 本地全量测试绿
2. push 分支到 GitHub，发起 Pull Request（写清改了什么、怎么测）
3. 主理人 review，必要时修改后再合；**合并进 main 前测试必须全绿**

## 5. 版本号约定（重要）

统一用**语义化版本** `v主.次.修`，发布时打 git tag。

| 位 | 什么时候 +1 | 举例 |
| --- | --- | --- |
| 主版本 | 协议 / 架构不兼容改动（**必须同步 bump `config.py` 的 `PROTOCOL_VERSION`**） | v1.0.0 |
| 次版本 | 新功能里程碑（对齐内部 R 系列：完成 R73 → v0.73.x） | v0.73.0 |
| 修订 | bug 修复、UI 微调、文案 | v0.73.2 |

- 发布动作：`git tag v0.73.0 && git push origin v0.73.0`
- 当前基线：**v0.1.0**（首个可协作版本）
- 日常提交**不用**改版本号；版本号只在打 tag 时定。

## 6. 敏感文件（已写入 .gitignore，禁止入库）

- `web_tls/*.pem` —— TLS 私钥
- `history/`、`audit/`、`server_state/` —— 聊天记录、审计日志、运行状态
- `prefs.json` —— 本地账号与会话配置
- `crash.log`、`build/`、`dist/` —— 日志与打包产物

> 约定：密钥、证书、用户数据一律不进仓库。`config.py` 里的管理员密码属代码逻辑
> （局域网应用，默认密码仅对自家服务器有效），**仓库请保持私有**，不要公开。

## 7. 目录速览

```
client.py / client_core.py   客户端 UI / 核心逻辑
server.py / web.py           服务器 / 网页端
widgets/                     自绘控件（登录窗、对话框、自绘标题栏…）
tests/                       单元测试（pytest）
_smoke_*.py                  手工冒烟脚本（回归用）
games_pkg/                   内置桌游包
docs/ im_design_notes/       设计文档与学习笔记
```

## 8. 谁负责什么（建议分工）

- 主理人 mixmixla：服务器 / 协议 / 登录门禁 / 主干 review
- 协作者：客户端 UI、游戏玩法、网页端；改动走 PR，避免两人同时改同一文件。

## 9. 仓库可见性

- **建议私有**（免费，协作者人数不限）：Settings → Collaborators → 添加朋友的 GitHub 账号，
  朋友即可 `clone` / `push` / 提 PR。
- 若改公开：请先评估 `config.py` 默认管理员密码、网页口令等配置是否可接受暴露
  （本地局域网应用，风险相对可控，但请自行判断）。

## 10. 开工清单（朋友首次拿到仓库后）

1. `git clone https://github.com/mixmixla/321_FISH.git`
2. 按第 2 节配好环境，`python run.py` 全绿
3. `git checkout -b feature/<要做的功能>` 开始第一个任务
