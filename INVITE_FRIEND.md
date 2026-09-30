# 邀请朋友加入仓库说明

> 仓库：`https://github.com/mixmixla/321_FISH`（私有）
> 用途：把这篇文档发给朋友，跟着做就能加入开发。

---

## 一、给朋友转发的邀请消息（可直接复制发微信）

```
Hi！跟我一起开发「摸鱼助手」吧～
仓库：https://github.com/mixmixla/321_FISH

按顺序做这 4 步：
1. 注册一个 GitHub 账号（github.com 右上角 Sign up），注册完把你的【用户名】发我，我加你为协作者
2. 安装 git：https://git-scm.com/download/win （一路下一步即可）
3. 安装 Python：装 pyenv-win，再装 3.14.5 版本（详细见下面文档）
4. 打开终端执行：
   git clone https://github.com/mixmixla/321_FISH.git
   cd 321_FISH
   pyenv local 3.14.5
   python run.py        # 全部测试通过 = 环境 OK，可以开干了

详细开发规范（分支/版本/提交格式）在仓库根目录 COLLABORATION.md，一定要看。
```

## 二、主理人（你）的操作

1. 让朋友**注册 GitHub** 并把用户名发给你。
2. 打开仓库页面 → `Settings` → 左侧 `Collaborators and teams`（协作者）→ `Add people` → 输入朋友的用户名 → 邀请。
3. 朋友会收到邮件 / GitHub 通知，**接受邀请**后即可 clone 和推送。
4. （推荐）保护 `main` 分支：`Settings` → `Branches` → `Add rule`，分支名填 `main`，
   勾选 `Require a pull request before merging` —— 这样 main 只能通过 PR 合并，不会被误推。

## 三、朋友的操作（详细版）

### 1. 注册 GitHub 账号
https://github.com/signup —— 用户名、邮箱、密码，按提示完成邮箱验证。

### 2. 安装 git（Windows）
https://git-scm.com/download/win 下载安装，全部默认选项即可。
安装完打开 PowerShell，输入 `git --version` 能看到版本号即成功。

### 3. 安装 Python 3.14.5（用 pyenv-win）
```powershell
# 安装 pyenv-win（在 PowerShell 里执行）
pip install pyenv-win --target "$HOME\.pyenv-win" --no-warn-script-location
# 把 pyenv 加进 PATH（重开终端生效）
[Environment]::SetEnvironmentVariable("PYENVWIN", "$HOME\.pyenv-win", "User")
[Environment]::SetEnvironmentVariable("PYENV_ROOT", "$HOME\.pyenv-win", "User")
[Environment]::SetEnvironmentVariable("PATH", "$HOME\.pyenv-win\bin;$HOME\.pyenv-win\shims;" + [Environment]::GetEnvironmentVariable("PATH", "User"), "User")
# 重开终端后：
pyenv install 3.14.5
```

### 4. 拉取仓库
```powershell
git clone https://github.com/mixmixla/321_FISH.git
cd 321_FISH
pyenv local 3.14.5
python run.py        # 全量测试门禁，全绿 = 环境没问题
python run.py server # 起服务器（默认 TCP 9527）
python run.py client # 起客户端 GUI
```

### 5. 日常开发流程（重要）
```powershell
git pull origin main                    # 动手前先拉最新
git checkout -b feature/你要做的功能      # 开分支，别直接在 main 上改
# ……改代码……
git add .
git commit -m "feat: 一句话说明改了什么"
git push -u origin <分支名>
# 然后去 GitHub 网页点 Compare & pull request 发起 PR
```
- 合并进 main 前必须：`python run.py` 全绿。
- 提交信息格式：`类型: 说明`，类型用 `feat`(新功能) / `fix`(修复) / `refactor` / `test` / `docs` / `style`。

## 四、注意事项

| 事项 | 说明 |
| --- | --- |
| 私有仓库 | 只有协作者能看代码，别人搜不到，放心传 |
| 敏感文件 | `prefs.json`、聊天记录、证书等已被 `.gitignore` 排除，**不要手动 git add 它们** |
| 测试门禁 | 提交前 `python run.py` 必须全绿，这是合并的硬条件 |
| 推送失败 | 国内网络连 GitHub 偶尔会 `curl 55` 断连：`git config http.postBuffer 524288000` 后重推 |
| 环境 | 本项目只支持 Windows + pyenv 3.14.5，纯标准库，无需 pip 装包 |
| 版本号 | 打 tag 时定（见 COLLABORATION.md 第 5 节），日常提交不用改 |

## 五、常见问题

- **clone 时提示需要登录/权限？** 说明还没接受邀请，检查邮箱里的 GitHub 邀请邮件，或让主理人重新邀请。
- **pyenv 装不上 3.14.5？** 确认用的是 PowerShell（不是 cmd），重开终端后 `pyenv install 3.14.5`。
- **测试挂了但没动过代码？** 先 `git pull origin main` 确认是最新代码，再问主理人。
