# 321_FISH · 摸鱼助手

Windows 局域网聊天与桌游应用：Tkinter 桌面端、TCP 服务器、网页端、文件传输、
语音和多款桌游。支持多套主题，包括新增的 **Excel 工作簿** 主界面皮肤。

项目到哪一步、下一项和后续路线见[任务清单](docs/任务清单.md)；
当前授权/主控/检查点以[指挥中心](docs/AI_COMMAND_CENTER.md)为准，换聊天继续见[接续指南](docs/连续开发与换窗口接续.md)。

## 开发环境与运行

使用 Windows 10/11、PowerShell 7、Python 3.14.5。
首次配置见 [开发环境](docs/开发环境.md)，分支和 PR 规范见
[COLLABORATION.md](COLLABORATION.md)。

```powershell
.\dev.ps1             # 全量测试
.\dev.ps1 server      # 先启动服务器
.\dev.ps1 client      # 再启动客户端
```

仓库已公开，服务器没有默认管理员密码。部署者须在启动服务器前设置
`MOYU_ADMIN_PASSWORD`；未设置或为空时禁止管理员登录，普通用户仍可正常使用。
管理员登录标识默认 `L57`，可用 `MOYU_ADMIN_NICK` 设置。配置、Web 登录与旧部署升级说明见
[管理员凭据与公开仓库安全](docs/管理员凭据与公开仓库安全.md)。

在客户端「设置 → 外观 → 皮肤」选择 **Excel 工作簿**；选择自定义皮肤时请关闭
「跟随系统深浅」。新版以可编辑工作表作为主区域：双击/F2 编辑单元格，Enter 保存并下移，Tab 右移，
Esc 取消，Ctrl+Enter 将当前格发送到下方选定会话。公式栏同步当前格内容，支持复制、
剪切及多格 TSV 粘贴；单元格保存在本机偏好中。
「会话记录」表页显示聊天历史；需要原有聊天操作时点击「原聊天界面」。

![Excel 工作簿皮肤](assets/excel-skin-preview.png)

本地审核记录见 [2026-09-30 项目审核](docs/项目审核_2026-09-30.md)。

后续开发参考 [项目记忆](PROJECT_MEMORY.md) 与仓库内的 [fish-assistant-dev skill](.agents/skills/fish-assistant-dev/SKILL.md)。
