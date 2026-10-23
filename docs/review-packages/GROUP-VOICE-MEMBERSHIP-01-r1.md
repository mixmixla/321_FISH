# GROUP-VOICE-MEMBERSHIP-01 r1

2026-10-23 IMPLEMENTED / DOMAIN_PASSED / INDEPENDENT_CODE_REVIEW_0_MUST / NOT_AI_ACCEPTED。[Task v1](../task-packages/GROUP-VOICE-MEMBERSHIP-01.md)，baseed287336d689360aec7090bfd4cc75c1c8099da7。root唯一资料/组合验证/集成，session_scout隔离server.py join/newtest实现，flagship_scout独立设计/代码/原件/资料与对象审查。

独立设计0 MUST：旧key/member校验在锁外，目标首次Hub锁前受控门停住join、主线程实际完成四撤销入口后放行，可证迟到重建名册。写入时同锁当前群/成员资格决定，拒绝不建房/不成功通知或审计；新增拒绝与room_full错误IO锁外，原code/text、public/合法重入port和容量/Web边界保持。锁释放后其他合法撤销导致的既有广播时序不作本Task新承诺。不启音频UDP/硬件，不改其他handler/客户端/视频。本批三个阶段已完成，组合full与产品验收仍待，视频仍暂停。

## 专项与领域证据

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原产品RED | 5F，actual exit1，2.65s | group-voice-race-red-20261023-20261023-192148-7c4b02b2e9 |
| 首GREEN | 5P，actual exit0，2.017s | group-voice-race-green-20261023-20261023-192228-11dac1c8d4 |
| 必要旧域 | 5文件66P，actual exit0，22.232s | group-voice-race-domain-20261023-20261023-192243-a552b14153 |

RED直接观察四撤销后缺预期room拒绝、room_full回调仍持Hub锁；四race最先停在拒绝probe断言，后续名册/peers/audit断言未执行，不能写成RED日志已断名册。受控门位于旧_room_key_ok成功后的首次Hub锁前，主线程真实撤销完成、worker无异常正常返回，绑定原处理器唯一路径必setdefault/插UID，故独立审查确认可确定推导名册复活/删群孤儿房，无需为镜像断言重跑。GREEN才完整执行名册/peers/audit及锁外probe断言。

test三阶段SHA `30f4c69ec314ec4e1bda6f9217462580f7181c23499e691c7e7a8dc3b61322be` 相同，RED→GREEN仅server.py变。GREEN/domain同source `75e7d3c61546b61114b877da4317f945b8b41fb665ddad063f35fb24eba1d296`，domain summary SHA `ec63b0fce7f3fcbf6d6bf03cef7f02d6767f884cd674a31322d88843d6bb6ee2`。旧域为R72+leave/kick/admin remove/dissolve，不重复newtest。三run manifest/progress、源快照、log SHA/计数、sandbox、单attempt/cleanup均核，actual exec12263/51231/14562结束exit1/0/0；当前源等domain。[脱敏证据](../review-assets/GROUP-VOICE-MEMBERSHIP-20261023/evidence.json)。

实际修改仅_on_room_join局部：写锁内群存在/成员二查，不预建失效群房；拒绝与原room_full错误IO锁外，public/容量、Web拒绝、合法同UID重入port、原peers/state/audit语义保持。线程事件门/有界join/异常传播，其他群/public名册保持，无音频UDP或设备；flagship_scout独立代码/三run原件0 MUST，可两文件提交/组合冻结，未full/AI接受或main集成。
