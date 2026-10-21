# R70-BOARD-WAIT-01 r1 — 榜单等待的确定性诊断与组合门禁

2026-10-21 **AI_ACCEPTED_INVENTORY_AND_BOARD_WAIT_ONLY / FULL_PASSED / MERGE_PENDING / NOT_R3_ACCEPTED**。
[Task v1](../task-packages/R70-BOARD-WAIT-01.md)。base/main `8fc927d4236e588fdb70a7dc40681ab0cff10816`；依赖 inventory 原分支/检查点 `79bf27b1a7dd8e7ced907a31d4f6cdde760195ec` 保持不变，原两次失败门禁及全部原件保留。
新分支 `fix/r70-board-wait-20261021` 从依赖候选分出，仅本项独立代码提交；root唯一写入/执行，gate_review独立只读，普通模型/Standard。本周授权只公开代码、测试、项目文档和脱敏摘要，不包含原始日志、用户名、私人数据、密钥或二进制，不发布。

## 可复现的结论与边界

首次受控真实集成 `r70-wait-red-20261021-213542-dd85da673d`：1F1P，exit1，2.836s。新测试执行原目标函数及原Collector/真实加密ClientCore/Hub；只在Hub处理函数取锁之前控制合法跨sender处理顺序、在原回调前延迟原帧入队，不替换消息或产品状态。共享门预算从Alice4发送起≤2s，不增加原Collector的3s截止。
Bob-first：实际Bob收到100/3（观察索引18）→Alice收到真实100/7（19）→Alice4原handler返回后观察server最终7/100（21）→原wait返回较早100/3（25），准确原tests/test_r70.py:564失败。实际最终board、snapshot、restore均Alice7/Bob100，两个fixture_errors为空、所有捕获worker结束/owned Hub收尾成功。反序Alice4先处理时原目标全部断言通过。
这证明合法可控交错可导致测试过早接受中间榜单；未记录的历史两次full精确时序无法重放，不冒称已取得历史请求轨迹，也没有证明产品积分或快照损坏。

## 最小改动和验证

只将原wait谓词从“有两项”收紧到gomoku、两项、两个实际UID的预期累计分数。排序、昵称/分数、字段集合、截断、非法输入、Hub状态、snapshot/restore断言全部留在原处；未加sleep/延时/skip，未改业务代码或门禁。新 `tests/test_r70_board_wait.py` 纳入正式全量，两个合法顺序都执行原目标全部断言，夹具异常不得掩盖原断言，逐资源清理并保存私有timeline，后台观察异常单独记录。
最终同字节RED/GREEN的490输入集合相同，仅tests/test_r70.py变化。新测试SHA `66cf38179da7c97243854a4eee3db5e76b63f32fc9d1bde7e93c6b2630c93326`。领域 `r70-wait-domain-20261021-213719-efd3b4512d`：7文件114P/0F0S/exit0/37.642s，source `81851f98a10c994a180dbf5613d22a711b65dfd59f62333182e82094f7b83993`，当前逐hash相同；两GREEN目标、快照和收尾通过。包含inventory全部11case及原五文件领域87P、原r70 25P、新2case。
初领域命令误写不存在文件名，被runner测试前拒绝；根据旧领域manifest纠正后执行上述唯一有效领域。预审1组MUST（异常保留/逐项收尾/后台错误记录）已关闭，执行前0 MUST；未以夹具失败冒充红测。

## 后续门禁与证据位置

代码/领域独立审查已完成；组合候选唯一一次适用最终全量已完成，独立核最终原件前不有限AI接受或安全集成。若失败先诊断，不盲目全量追绿。不得以本专项通过替代最终门禁。
私有原件在 `_tmp_gui/r70-board-wait-20261021`（baseline、original-test-r70.py、deterministic-red-proof.json、domain-binding.json）及 `_tmp_gui/test-gate/` 对应run；原timeline、原日志、完整summary只留本地。公开后续只写脱敏结果与SHA索引。
完整GUI、自然应用退出、LAN、其它DPI、新源码EXE、硬件/STT和非开发机仍未验；协议/组件测试不等同这些验收。本批不重建EXE或扩产品；完成后恢复有限R3真实未测清单，有受支持入口才推进。

独立代码/确定性原件与领域审查0 MUST；仅两测试代码提交 `9d6d1de92998e85d73923ff91acb45a46ee0320f`，父提交79bf，待组合full与最终独立审查，不推合。

## 最终组合门禁原件（终审前检查点，终审结论见下）

唯一full `r70-wait-full-20261021-214111-6d59409cd3`：213文件**2971P0F20原opt-in S/actual exit0/793.493s**。490当前/领域/snapshot逐hash同source `81851f98a10c994a180dbf5613d22a711b65dfd59f62333182e82094f7b83993`；全部213文件单attempt、原log SHA、原sandbox、exit/cleanup/artifact与16项后验均通过。原211未受影响文件counts相同，原r70由24P1F到25P、新2case通过；20原跳过保持。两个full timeline真实原target/state/restore正确且fixture_errors空、owned收尾成功。
原inventory双failed full及base/候选未复现control全部保留，原分支仍79bf；本次组合绿不抹去历史。无新EXE、无活动测试/构建、无本轮远端写入，GUI等未测不升级。公开[脱敏结果/213 log哈希索引](../review-assets/R70-BOARD-WAIT-01/evidence.json)，原raw/完整summary/timeline只留本地。
该检查点下一独立终审全部原件与当前资料；满足质量后依本周授权审全新history和14路径，fresh检查远端/保护/required checks再安全推合。候选未上传，不宣称CI通过。

## 独立终审与有限AI验收

独立终审0 MUST：原213门禁日志/清理/源码绑定与双受控轨迹、原inventory双失败记录、14公开路径和四提交历史核对通过。有限AI接受仅覆盖严格清单维护及R70等待契约，完整R3仍未验收。 主控据此仅AI接受严格清单维护和R70等待契约两项组合；不是用户/Pro/完整R3验收。原inventory分支79bf及所有failed原件保留，其单项历史状态未被改成PASS。下一仅审准确14路径及全部新commit history，fresh核远端/保护/required checks后正常安全推合；尚未远端写入，不发布。
