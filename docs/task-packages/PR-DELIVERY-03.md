# PR-DELIVERY-03 — CORE与退役设计资料追加到现有 Draft PR #5

版本 v1，2026-10-02（Asia/Shanghai），执行状态只见[指挥中心](../AI_COMMAND_CENTER.md)。
用户当前直接请求“下一阶段是什么，请给出具体提示词……如果可以提交pr就提交pr了”，授权满足验收条件后提交/推送/交付PR。
PR #5实际仍open/draft、head正是当前codex/cc02a-consistency，故将CORE追加至该PR并更新完整标题/说明，不新建包含相同前置代码的重复PR。
这项授权补充原CORE/设计的Git禁止范围，只覆盖本次Git交付与提示词，不merge/release、发Pro/其它聊天消息、真实数据或后续产品实现。

## 基线与保护

- 入场head fc9c991bed82dc969aefdbfc9a77a46e75bde5d5/tree ba45f96a9de7a55c91b8150eacd78aa6740fe95c、branch codex/cc02a-consistency；index空。
- 真实GitHub/ls-remote一致：PR5head fc9c991，base main cc7e295，open/draft/merged=false，main未改变；不pull/切分支/重开旧PR。
- CORE v1.1已独立ACCEPTED，115文件1392/0/2、37专项/276域/真实TCP-HTTP-JSON14观察；307raw source IDc647d65c7061ceb67e26bd571520230ed84730b0480968b5ea6c809abdae2f28本次仍一致。
- 入场376非ignored文件原字节、原index、dirty/owned清单保存_tmp_gui/pr03/entry.json/entry-files/entry-index；旧未提交设计与核心交付保留。
  只读核对旧主控/Goal/进程无并行操作；本批Goal在此Task冻结后启动，不重跑同版应用门禁、不恢复旧守护。

## 提交层次与角色

1. code：server.py/server_store.py、tests/test_admin_credentials.py/test_audit_server_security.py、两新增test_cc02_retire_core/test_cc02_store_min，共6路径。
2. docs：当前11份已批准未提交设计/核心/记忆/技能/指挥中心/生成清单，加本交付Task/Review，共13明确路径。
3. 实际push/PR元数据结果仅CC/Review/投影纯docs补录，不改变源码；记录code/docs/flow SHA映射而不构造文件自引用SHA循环。

主控唯一Git refs/index与交付文档写入；独立提交审查只读actual tree/原证据，不参与实现或修改。
只stage精确清单，不git add .、强推或push main；未授权文件/真实runtime/凭据/_tmp/venv/TLS不得入库。
原设计三正文c45e7f27…保持，旧Review/Task冻结正文不反写历史；当前CC及PR完整描述反映新实际范围与延期。

## 完成条件与终点

- commit前/后raw307完全保持；每一提交blob等于同路径Git clean规范化结果（区分raw SHA与规范化blob，不误称换行改行为）。
- code层6路径、docs层13路径与base父子关系正确，无敏感边界，文档链接/投影/diff-check通过，独立提交树无must。
- 推送仅既有head分支；remote实际head匹配，PR5仍open/draft且base main，标题/说明更新覆盖基础一致性+退役CORE，attach本聊天。
- 保存实际PR URL/head/remote/base/提交映射/命令/失败与限制；完成Goal、交付下一有限阶段可复制提示词后停止。
- CORE未变化引用既有1392门禁，不为Git/纯docs无意义重复应用测试；下一STORE/RESOURCE仅提示词，不在本批开代码。

证据见[Review](../review-packages/PR-DELIVERY-03-r1.md)。
