# KEY-INIT-RACE-REPRO-01 r1

2026-10-25 PARTIAL_BLOCKED / NOT_AI_REPRO_CONFIRMED_TASK / NO_PRODUCT_CHANGE / LOCAL_CANDIDATE_ONLY。
[Task v1](../task-packages/KEY-INIT-RACE-REPRO-01.md) / [脱敏证据](../review-assets/KEY-INIT-RACE-REPRO-20261025/evidence.json)。
base为已Git/API核main `18a4a5e4e90bc1669dda142c9f0db02dc14a2a7d`。
root独立key-init-race-repro-20261025树/diag同名分支；server_scout唯一写本地候选测试/ignored辅助，
identity_scout独立设计、实际测试/控制器和原件审查；root唯一公开资料。原集成源码与试用包不改。

## 唯一执行与失败分类

最终本地`tests/test_key_init_race_repro.py` SHA
`3467f3035f2796d6e68d59241496b883d2c399c7a19ecf963755ce76064aacc0`，
两个实际Core、同合成UID/ROOT/scope、预存目录；Event分别门控A精确open(x)之前与创建空文件后dump之前。
真实open/dump/fsync/load继续执行，观察wrapper只记录类型后原样rethrow，不注入异常。
执行前独立测试/控制器0 MUST；case2无先前完整文件，published-key比较明确null不适用，未用True虚报。

唯一`kir25-red` 06:08:06 UTC启动、06:08:09结束；1文件2F/0P0S，actual exit1，1.221s，
summary SHA `8403037942d6d03f41ddd79703ec4a4599aed0a95157e5baea1e5ea138aa61d9`。
只有一个attempt，无timeout、unexpected skip、sandbox或清理失败；没有改产品、重跑或弱化断言。

- `before_exclusive_open`完整到末正常行为断言：B先真实WELCOME成功、fsync1/handle关闭；
  A放行后真实FileExistsError，随后manual_login_required/stop/local_storage1。赢家文件SHA与stop前后保持，
  双Core公钥不相同；只输出相等布尔、不公开密钥/公钥值。门唯一、线程完成、两Core清理均通过。
  这一个窗口确认，仍不是修复或跨进程试验。
- `before_first_dump`部分观察：真实open(x)后零字节门与B真实异常链已触达，实际链包含
  E2EEError→JSONDecodeError→StopIteration。Python 3.14的JSON解码器保留底层context，
  测试仅预期两个类型的精确断言提前失败。finally释放A并完成线程/Core清理，但报告缺最终
  双Core状态、完整写成后的SHA比较；不补造缺字段，不把本例记作完整复现，也不称持久损坏或泄漏。

准备阶段一次shell ParserError发生在写文件前；执行前静态纠正Core字段和不适用比较。
后验索引已完成后外层exit转义报错也单独保留，均不是产品测试结果或第二次gate。
本地原件/辅助说明保留，不以这些工具问题替代实际2F分类。

## 输入与原件

诊断506输入/source `15bba77c4b500c5763c9f4ca46128adafb8554a02ddd9dae05497bbcd8485857`，
worker当前/source快照/case副本逐SHA相同。相比已验main的505输入，501个输入逐字节相同，四个前批新增
test在新checkout仅LF→CRLF（已逐字节归一核），再新增本地候选test；无产品文本变化。
root原505仍精确等已验full/source1f5f2de16d3acb5eac082596863cfb193a453f75ad0cffd7c322aac7ae9d4be5。
实际stdout/exit收据、summary/progress/原log/sandbox/清理/指纹与候选test绑定均由root和identity_scout
独立核实；旧UID与暂停视频失败summary SHA保持。没有活动测试；worker仅该新test未跟踪，无tracked修改。

原gate只本地`_tmp_gui/kir25-red`；实现树
`_tmp_gui/worktrees/key-init-race-repro-20261025/_tmp_gui/key-init-race-repro-20261025`保存
red-output、red-exit、run-index、safe-observations和辅助错误说明；root集成树对应ignored目录保存独立核验。
失败候选test不入main，不将其当已验收代码。公开摘要不含key SHA、scope、路径私密值或原log正文。

## 结论与续接

独立技术结论为PARTIAL_BLOCKED / NOT_AI_REPRO_CONFIRMED_TASK，只有第一窗口完整确认。
下一轮先修订诊断夹具合同，使异常链判断保留真实额外context，然后只补第二窗口的完整终态证据；
本轮已停止，不能在本Task v1名下悄悄重跑。之后另行设计跨进程协调/不可覆盖原子发布，
含已有合法/坏key、reparse、写入失败、超时/关闭与不同UID边界；本批不批准实现。

identity_scout已对最终技术分类/披露独立审0 MUST，server_scout仅审公开准确性/隐私，
五路径/404相对链接/投影与原件映射0 MUST，非其测试技术自验。新增Git对象另审后仅交付这五资料。
资料通过不代表诊断Task或产品修复通过；
仍保留完整GUI、自然退出、LAN、异机/DPI、STT和视频失败边界，不发布二进制或原始资料。
