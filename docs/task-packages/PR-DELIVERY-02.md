# PR-DELIVERY-02 — CC-02A 与后续资料的新 Draft PR

版本 v1，2026-10-02（Asia/Shanghai），状态只见[指挥中心](../AI_COMMAND_CENTER.md)。
批准来源：用户在本聊天明确提出“同时这个pr没提交的话可以先提交了”，授权按已给出的新PR提案提交、推送和创建Draft PR。
这项补充覆盖Git交付，不批准merge/release、发Pro或其它外部消息、开始RETIRE/新产品或修改真实数据。
沿已明确的有限批次Goal偏好持续完成源/提交边界检查、独立审查、推送/PR、真实URL/版本交付后结束。

## 范围与基线

- 仓库mixmixla/321_FISH，新分支`codex/cc02a-consistency`，base main；PR #4已经合并，不重开/更新旧PR。
- 入场HEAD `d07b29577a48367f887cc0c2dbf1671ed13bb326`，原fix/cc-01a-admin-credentials，index空，已批准资料与CC02A实现仍dirty。
- 远端main `cc7e2951695041face3ea2451ef98a02d469d15b`，tree `0bdde55666b06103a46ecb02ba499ff4db93b0a5`与入场HEAD一致；
  创建新分支前保存边界并显式fetch该基线，不pull覆盖未提交成果。远端变动则先核对实际差异。
- 已验收源/测试/依赖305项raw ID`1f94f8fca3da7746c5db293b05e5729e76b37935e1a05d0314658bde9de39830`，
  最终113文件1355/0/2，独立终审与真实UI满足；代码/测试/依赖/基线树不变时引用此报告，不重复全量。

## 提交层次与所有权

1. fix提交：server.py/client_core.py/client.py/web.py、tests/test_server.py及5个新增test_cc02a_*.py。
2. docs提交：已批准DOC-ROADMAP-01、CC-02-DESIGN、架构决定/修订草案/历史draft-v1、CC-02A Task/Review、
   PROJECT_MEMORY/README/AGENTS/指挥中心/生成任务清单及本交付Task/Review；旧M0–M6归档与接续指南保留。
3. PR创建后的实际URL/head/remote/交付状态仅纯文档补录，单独记录提交映射；不冒称已创建时的head仍是最新head。

主控唯一Git refs/index和交付资料写入；cc02_docs_review独立只读审查实际提交树/范围/原证据。
同模块不并行写代码，本批不改应用/测试/依赖。只使用明确文件清单stage，不git add .，不强推、不向main直接push。
ignored原日志、_tmp_gui、prefs/history/server_state/web_files/audit/TLS/downloads/venv均不入库。
保存所有入场文件hash和原index边界，保护用户/他人新增改动；unexpected增量先核对，不覆盖或自动丢弃。

## 完成条件

- 当前raw305匹配已验收版本；提交blob逐路径等于相同文件的Git clean规范化结果，换行映射不称为行为改写。
- 新分支/两层提交base与文件范围准确，独立审查无必须项；文档链接/投影/diff-check和敏感边界通过。
- push仅目标分支，读取remote匹配实际head；成功创建一条新Draft PR并attach到本聊天。
- Task/Review/指挥中心记录PR URL、base/head/提交映射、命令结果和实际限制；必要状态补录纯docs提交后再次核对远端。
- 所有源/测试/依赖原字节不变；交付已实现才complete Goal，不merge/release/发Pro/继续其它批次。

证据见[PR-DELIVERY-02 Review](../review-packages/PR-DELIVERY-02-r1.md)。
