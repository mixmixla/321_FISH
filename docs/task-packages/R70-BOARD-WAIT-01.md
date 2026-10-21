# R70-BOARD-WAIT-01 v1 — 榜单等待时序的确定性诊断与最小整改

2026-10-21 READY，用户明确冻结。main仍8fc927d4236e588fdb70a7dc40681ab0cff10816；保留inventory分支79bf27b1a7dd8e7ced907a31d4f6cdde760195ec及全部失败原件，不合并未通过候选。新fix/r70-board-wait-20261021以该冻结候选为依赖，仅独立新增R70相关代码提交；不改原分支指针。root唯一写入/执行，gate_review独立只读，普通模型/Standard。

## 问题、证明与最小范围

原tests/test_r70.py:564两次完整full均实际拿bob100/alice3而期待alice7；base和候选一次原r70专项各25P没有复现，静态竞态不等于根因已证。本Task用事件门控真实Hub、真实加密ClientCore连接、原Collector/目标测试，逐请求send/server received/applied、客户端收到/入队/被wait选择记录有序timeline，证明可控跨sender合法处理顺序、最终真实积分与snapshot/restore结果。
控制只暂停测试里的Hub分数处理与观察回调，不捏造/替换协议载荷或产品状态。至少bob999在alice4前处理与相反顺序两组；旧测试原断言能否确定性失败、失败时真实server/Alice客户端最终状态与snapshot/restore是否正确需原件支持。若实际产品积分/快照错误，另明确最小修复范围再实施，不能凭静态解释结案。
若证明只是原wait提前接受中间状态，仅改原榜单等待谓词达到本请求最终状态；保留所有原积分/夹取/排序/字段/非法值/服务端状态/快照恢复断言和3s截止，不skip、不弱化、不加sleep、不改产品协议/业务/GUI/构建/依赖/门禁。不新并行框架，复用既有target/Collector和正式test-all隔离。

## 验证、组合与停止

先冻结controlled regression/预审后在未修改原r70上RED，记录原timeline与产品真实结果；最终测试同字节RED→最小实现GREEN→相关/组合领域回归/独立审查→冻结组合source→一次最终full（包含inventory全部11case和原r70）。原双full失败/未复现control全部保留，不用专项PASS替代，若finalfull失败先诊断，不盲目循环或绕过。
真实网络/组件不当完整GUI、自然退出、LAN/其它DPI或新EXE通过；本批不做无关构建，不修改用户ACL/安全设置/真实资料。raw timeline/原日志/完整summary只新ignored _tmp_gui/r70-board-wait-20261021及test-gate。
组合通过与独立验收后才在本分支更新inventory依赖为有限组合AI接受（原分支/失败原件不改），按本周有界许可公开仅代码/测试/项目文档/脱敏摘要，审精确路径和全部main之后新history。fresh fetch/保护/required checks和他人变更核，再正常push/安全集成main并核远端完整SHA/可见CI；无CI不当PASS，不强推/绕保护/删分支/发布，不公开raw/用户名/私密/密钥/profile/二进制。止于此R70整改及组合候选，不扩产品。

## 执行检查点

需求/范围仍v1；受控真实RED1F1P、最小等待修复、最终同字节领域114P、独立代码0 MUST及唯一组合full r70-wait-full-20261021-214111-6d59409cd3 2971P0F20原skip/exit0已完成，该检查点最终独立原件/资料审查待完成，现已完成见下。历史inventory失败/原分支79bf保留，尚未推送/合并；当前状态与恢复入口以AI_COMMAND_CENTER为准。

最终独立原件/资料终审0 MUST，主控有限AI_ACCEPTED_INVENTORY_AND_BOARD_WAIT_ONLY；本地完成、集成待执行，非完整R3。历史失败与frozen inventoryref79bf保留，集成与下一阶段仅依指挥中心当前记录。
