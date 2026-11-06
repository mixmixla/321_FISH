# 快速验收入口

候选源码冻结后，在该工作树的 **PowerShell 7 (`pwsh`)** 中执行：

```powershell
$out = Join-Path (Get-Location) ('_tmp_gui/arcade-final-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
& 'D:/Project/321_FISH/.venv/Scripts/python.exe' ./fast_verify.py --run-dir $out `
    --priority tests/test_gomoku_rules.py `
    --priority tests/test_tielu_play.py `
    --priority tests/test_server_games.py `
    --priority tests/test_web_boardgame_assets.py
exit $LASTEXITCODE
```

省略位置参数会覆盖当前全部 `tests/test_*.py`（含新增未跟踪文件）。
`--priority FILE` 可重复添加本批专项文件，完成后从后续队列剔除。
`--plan-only` 只打印全部文件与分队；`--serial` 用于单队列对照。

入口只调用原有 `run.py test-all`：45 个已审过的纯规则/内存房间文件可与
其余串行文件重叠，新文件默认串行。原门禁识别出的 GUI 文件先独占执行，
避开实测的 Tk 事件循环争用；工具自身的嵌套测试文件也独占执行。
顶层最多两队，含嵌套检查最多三个 pytest。主控仍须协调其他聊天的活动测试。
逐文件源码/profile/basetemp、进程/桌面/数据隔离、日志与 sandbox 证据均由原门禁保存。

`plan.json` 保存选定全集和分队。总 `summary.json` 汇总各队原生结果，核对
相同 source/dependency ID、全集无漏/重、真实退出码与 cleanup；原件在各队子目录。
总 summary 的 planned_files=files、missing/duplicates/extra/errors/failures 全空且
退出 0 才是完成。源码冻结及最终候选核对仍由主控负责。

某队失败就创建 `STOP`，其他队只完成正在运行的文件；原生 `--fail-fast`
保留首个红记录，`--stop-file` 阻止启动下一文件。失败/未完成返回 1，工具、
不同源或 cleanup 问题返回 2；不会重试、抹掉失败或覆盖旧目录。
人工停止可创建本次输出目录的 `STOP`，等待当前文件按原超时与清理规则结束。
