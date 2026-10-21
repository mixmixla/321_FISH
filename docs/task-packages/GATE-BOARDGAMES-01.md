# GATE-BOARDGAMES-01 v1 — 补齐桌游展示包的隔离源码输入

2026-10-21冻结时READY；执行状态唯一来源为[指挥中心](../AI_COMMAND_CENTER.md)。来源：用户本轮授权建立新机基线并完成一个优先小增量。
base：84444b5aea305f1d179b2f07c9ace132fa78071b；独立分支 fix/gate-boardgames-20261021。

## 现状与范围

干净主干在本机现有五文件隔离基线得到26 PASS / 3 FAIL / 0 SKIP、exit1。
三个失败在 test_boardgame_asset_img.py；原日志明确 boardgames 模块未复制，
Azul退回通用绘制。test_gate._allowed_relative 与 _source_files 只知道旧包。
主干10月14日起已有32个 boardgames 跟踪输入（Python和PNG），旧门禁结论不能沿用。
这是CC-05/VB-01验证基线的窄补正，优先于仍为DRAFT的 UI-ROOM-ICON-01。

仅修改 test_gate.py 的包/静态资产收集，以及必要回归。纳入跟踪与未跟踪的
boardgames Python、包内 assets 静态文件，并纳入字节指纹/副本/恢复失配检查。
保留敏感运行目录、prefs/私钥等排除、reparse边界、私有桌面、loopback与设备限制。
不改游戏规则、渲染实现、客户端、依赖、skip/超时/已有断言，不运行美术生成器。

## 验收

1. 保存干净base原失败，不覆盖或借重试改判。
2. 新回归先在原门禁RED：真实子门禁可导入包并读取包内素材；tracked/untracked均覆盖。
3. 素材字节变化导致原run恢复拒绝；敏感运行文件始终不进入源清单/副本。
4. 原五文件领域复测，实际Tk渲染不得skip；随后同版全量逐文件门禁。
5. 独立只读审查Task、diff、原始证据；实现者不能自行验收。必测FAIL保留并阻断接受。
6. 更新唯一指挥中心和生成阅读视图，Review提供命令、退出码、版本和限制。

本轮只允许本地相关提交；不push/PR/merge/发布，不操作真实账号或其它项目。
结束后停止本轮，不自动扩展后继功能。恢复入口：AGENTS → 指挥中心 → 本Task/Review。
