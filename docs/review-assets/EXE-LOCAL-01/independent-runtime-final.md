# EXE-LOCAL-01 v1 独立运行终核

审查者 purchase_review（GPT-6.1 Sol），2026-10-13。只读原证据核查；未启动应用、测试、Tk、构建、服务或下载。

限定已完成的本机构建、入口/CLI、登录取消、主窗口隐藏和所属 Job 清理范围 **0 MUST**。本报告支持 root 仅记录这些实际完成项的技术接受，不代表整项 EXE 生命周期或发布完成。

- 原 runtime 4 PASS / 2 FAIL / exit 1；第二 runtime-recheck 1 PASS / 1 FAIL / exit 1；第三 runtime-demo-recheck 1 PASS / 0 FAIL / exit 0。原失败与三轮独立 summary/case/log 永久保留；不是把第三轮冒充整轮无历史失败。
- 已核 9 个原 case 与 summary 一致、9 份原 case 日志 SHA，以及 8 份子日志 hash/size；三轮每个 Job 清理后 active=0、PID 列表空。
- 首轮 initialize-new、inspect、StartTrial dry-run、真实菜单0均在 cleanup 前自然 exit0 + Job0，未强停。菜单使用自有 0\n\n 文件，两提示与未创建 trial 目录证据一致。
- 第二轮登录取消针对自有 private desktop 的唯一可见 TkTopLevel/内部办公助手，当前Job成员与指定 client image，经重新枚举身份重核后 WM_CLOSE；自然 exit0 + Job0 在 cleanup 前，未强停。此为登录取消，不代表主会话 quit_app。
- 第三轮 compiled入口实际两不同UID的合成 TCP登录事件均在原 server audit找到，peer=127.0.0.1；HTTP 200。端口由当前Job指定server image的loopback LISTEN/ESTABLISHED行推断；保留自有Job全表，不声称只有server行。
- 第三 desktop MoyuEXE-17840-b9c22108eb；动作前10个Job成员，其中2个精确 C:/Windows/System32/conhost.exe单列，其余为当版入口/server/client。定向主窗口 WM_CLOSE后同HWND由visible变hidden、进程仍运行，符合 hide_to_mini；后续所属Job强停124、active0，明确不算自然退出。
- 410个当前输入与 source13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345 原清单hash/size保持；三构建binary与三轮中文包副本共12次hash核验保持。沿用同hash artifact-review/artifact-proof归档收集0MUST。

原FAIL原因及观察helper修正均已独立静态审：空自有desktop零error、stdout缓冲导致端口不可见、精确Job内conhost归属；没有产品/测试/依赖/EXE整改，没有全局输入/截图/控制台广播。

主会话 quit_app、服务态 Ctrl+C、StartTrial在两client自然退出后自然返回、完整EXE游戏/邀请/结束/再开、非开发Windows、物理LAN、DPI与最终视觉仍未验；危险 --run-visual继续禁用。上游房间图标强引用缺口及历史Tcl after诊断保留。

核验数据：

{
  "errors": [],
  "case_logs_verified": 9,
  "child_logs_verified": 8,
  "current_inputs": 410,
  "binary_hash_checks": 12,
  "run_totals": [
    [
      "runtime",
      4,
      2,
      1
    ],
    [
      "runtime-recheck",
      1,
      1,
      1
    ],
    [
      "runtime-demo-recheck",
      1,
      0,
      0
    ]
  ],
  "third_desktop": "MoyuEXE-17840-b9c22108eb",
  "third_owned_count": 10,
  "third_console_count": 2,
  "login_cancel_target": {
    "hwnd": 465778,
    "pid": 35404,
    "title": "内部办公助手",
    "class": "TkTopLevel",
    "visible": true,
    "image": "D:\\Project\\321_FISH\\_tmp_gui\\exe-local-20261013\\当版 三EXE 复核2\\dist\\client.exe"
  },
  "main_hide_action": {
    "message": "WM_CLOSE",
    "hwnd": 466136,
    "pid": 9864,
    "desktop": "MoyuEXE-17840-b9c22108eb",
    "target_reverified": true
  },
  "public_archive_exists": true,
  "public_top_files": [
    "artifact-proof.json",
    "artifact-review.md",
    "bind.json",
    "build-observer.py.txt",
    "build-summary.json",
    "client.spec.txt",
    "console-helper-repair.json",
    "copy-after-double-build.json",
    "double-build-command.json",
    "double-build.json",
    "empty-desktop-probe.json",
    "entry-build-command.json",
    "generated-build-files.json",
    "logs",
    "observer-v1.py.txt",
    "observer-v2.py.txt",
    "observer-v3.py.txt",
    "raw-log-index.json",
    "runtime-demo-recheck-menu-launcher-proof.json",
    "runtime-demo-recheck-summary.json",
    "runtime-helper-repair.json",
    "runtime-menu-launcher-proof.json",
    "runtime-recheck-menu-launcher-proof.json",
    "runtime-recheck-summary.json",
    "runtime-summary.json",
    "server.spec.txt",
    "StartTrial.spec.txt"
  ]
}
