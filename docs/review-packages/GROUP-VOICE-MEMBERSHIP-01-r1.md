# GROUP-VOICE-MEMBERSHIP-01 r1

2026-10-23 IMPLEMENTED / DOMAIN_PASSED / INDEPENDENT_CODE_REVIEW_0_MUST / FINAL_FULL_PASSED / FINAL_TECH_REVIEW_0_MUST / AI_ACCEPTED_GROUP_VOICE_MEMBERSHIP_ONLY / PUBLIC_REVIEW_0_MUST / MERGED_MAIN / REMOTE_VERIFIED。[Task v1](../task-packages/GROUP-VOICE-MEMBERSHIP-01.md)，baseed287336d689360aec7090bfd4cc75c1c8099da7。root唯一资料/组合验证/集成，session_scout隔离server.py join/newtest实现，flagship_scout独立设计/代码/原件/资料与对象审查。

独立设计0 MUST：旧key/member校验在锁外，目标首次Hub锁前受控门停住join、主线程实际完成四撤销入口后放行，可证迟到重建名册。写入时同锁当前群/成员资格决定，拒绝不建房/不成功通知或审计；新增拒绝与room_full错误IO锁外，原code/text、public/合法重入port和容量/Web边界保持。锁释放后其他合法撤销导致的既有广播时序不作本Task新承诺。不启音频UDP/硬件，不改其他handler/客户端/视频。本批三个阶段及唯一组合full已完成，产品仅本Task有限AI接受，公开资料独立0 MUST，普通main集成和远端核实已完成，视频仍暂停。

## 专项与领域证据

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原产品RED | 5F，actual exit1，2.65s | group-voice-race-red-20261023-20261023-192148-7c4b02b2e9 |
| 首GREEN | 5P，actual exit0，2.017s | group-voice-race-green-20261023-20261023-192228-11dac1c8d4 |
| 必要旧域 | 5文件66P，actual exit0，22.232s | group-voice-race-domain-20261023-20261023-192243-a552b14153 |

RED直接观察四撤销后缺预期room拒绝、room_full回调仍持Hub锁；四race最先停在拒绝probe断言，后续名册/peers/audit断言未执行，不能写成RED日志已断名册。受控门位于旧_room_key_ok成功后的首次Hub锁前，主线程真实撤销完成、worker无异常正常返回，绑定原处理器唯一路径必setdefault/插UID，故独立审查确认可确定推导名册复活/删群孤儿房，无需为镜像断言重跑。GREEN才完整执行名册/peers/audit及锁外probe断言。

test三阶段SHA `30f4c69ec314ec4e1bda6f9217462580f7181c23499e691c7e7a8dc3b61322be` 相同，RED→GREEN仅server.py变。GREEN/domain同source `75e7d3c61546b61114b877da4317f945b8b41fb665ddad063f35fb24eba1d296`，domain summary SHA `ec63b0fce7f3fcbf6d6bf03cef7f02d6767f884cd674a31322d88843d6bb6ee2`。旧域为R72+leave/kick/admin remove/dissolve，不重复newtest。三run manifest/progress、源快照、log SHA/计数、sandbox、单attempt/cleanup均核，actual exec12263/51231/14562结束exit1/0/0；worker产品两文件与domain同字节，组合498输入及其独立source ID另见下文。[脱敏证据](../review-assets/GROUP-VOICE-MEMBERSHIP-20261023/evidence.json)。

实际修改仅_on_room_join局部：写锁内群存在/成员二查，不预建失效群房；拒绝与原room_full错误IO锁外，public/容量、Web拒绝、合法同UID重入port、原peers/state/audit语义保持。线程事件门/有界join/异常传播，其他群/public名册保持，无音频UDP或设备；flagship_scout独立代码/三run原件0 MUST，两文件已提交/等blob组合冻结，最终full及技术审查见下，main集成见交付回执。

## 唯一最终组合门禁

worker94685dbd9d03130159279b833ac2a2e0bedaaf48无冲突集成ceae77c497e08742db1fa0acc1a72e757d12905d，两blob一致。498输入source `f3b5e013dc2008d10b198ccdac9273bd5fbd5c0b144c9b2134b1abbaf7b8eaae`，相对已验收base只有server/newtest输入变化；client/client_core/vmemo_api等base，视频4759非祖先。

唯一full `gvm23-final-01`：221文件3022P/0F/20既有skip，actual exit0，862.58s，summary SHA `de53fa5bd1c8f69c1d657a6d62b2e2562188fd56eff8b70c69831cc4c4ee0986`。使用现有短run-dir，不改环境/系统设置；exec96207自然结束，现无活动测试。root首次28后验全true，冻结/当前/快照、完整集合、逐原log SHA/计数/sandbox/单attempt/cleanup、解释器依赖、既有220文件逐计数及20skip、各阶段与旧失败原件均保持。

flagship_scout独立复算全221原件/498源及身份/旧计数/失败保留，最终技术0 MUST；root据此有限AI_ACCEPTED_GROUP_VOICE_MEMBERSHIP_ONLY。公开七资料独立审查0 MUST（领域与组合源ID措辞已修正）；全部42新增可达对象/metadata独立审计0 MUST，普通main集成/远端双核见下。原始日志仅本地ignored；视频仍暂停且未接受/合并，不诊断/开设备。不代表CI、可视GUI、自然退出、物理LAN、新EXE、完整R1或发布验收。

## 远端交付回执

全部42新对象（4commit/21tree/17blob）及metadata独立0 MUST后，正常快进main并非强制push；Git ls-remote和GitHub branch API双核完整SHA `fc7c2092f001fdacc47277784369badba9609f54`，498源逐字节等full，现无活动测试。该提交check-runs/status contexts/Actions均0（aggregate pending/total0），不称CI通过。本回执纯资料，最终leaf以Git refs为准，回执对象另审；无源码变化不重测/发布，视频继续暂停。
