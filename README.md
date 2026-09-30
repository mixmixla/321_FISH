# 321_FISH · 摸鱼助手

Windows 局域网聊天与桌游应用：Tkinter 桌面端、TCP 服务器、网页端、文件传输、
语音和多款桌游。支持多套主题，包括新增的 **Excel 工作簿** 主界面皮肤。

## 开发环境与运行

使用 Windows 10/11、PowerShell 7、Python 3.14.5。
首次配置见 [开发环境](docs/开发环境.md)，分支和 PR 规范见
[COLLABORATION.md](COLLABORATION.md)。

```powershell
.\dev.ps1             # 全量测试
.\dev.ps1 server      # 先启动服务器
.\dev.ps1 client      # 再启动客户端
```

在客户端「设置 → 外观 → 皮肤」选择 **Excel 工作簿**；选择自定义皮肤时请关闭
「跟随系统深浅」。新版以可编辑工作表作为主区域：双击/F2 编辑单元格，Enter 保存并下移，Tab 右移，
Esc 取消，Ctrl+Enter 将当前格发送到下方选定会话。公式栏同步当前格内容，支持复制、
剪切及多格 TSV 粘贴；单元格保存在本机偏好中。
「会话记录」表页显示聊天历史；需要原有聊天操作时点击「原聊天界面」。

![Excel 工作簿皮肤](assets/excel-skin-preview.png)

本地审核记录见 [2026-09-30 项目审核](docs/项目审核_2026-09-30.md)。

后续开发参考 [项目记忆](PROJECT_MEMORY.md) 与仓库内的 [fish-assistant-dev skill](.agents/skills/fish-assistant-dev/SKILL.md)。
