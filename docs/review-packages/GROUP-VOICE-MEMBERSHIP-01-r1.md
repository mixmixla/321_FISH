# GROUP-VOICE-MEMBERSHIP-01 r1

2026-10-23 READY / INDEPENDENT_DESIGN_REVIEW_0_MUST / NOT_IMPLEMENTED。[Task v1](../task-packages/GROUP-VOICE-MEMBERSHIP-01.md)，baseed287336d689360aec7090bfd4cc75c1c8099da7。root唯一资料/组合验证/集成，session_scout隔离server.py join/newtest实现，flagship_scout独立设计/代码/原件/资料与对象审查。

独立设计0 MUST：旧key/member校验在锁外，目标首次Hub锁前受控门停住join、主线程实际完成四撤销入口后放行，可证迟到重建名册。写入时同锁当前群/成员资格决定，拒绝不建房/不成功通知或审计；新增拒绝与room_full错误IO锁外，原code/text、public/合法重入port和容量/Web边界保持。锁释放后其他合法撤销导致的既有广播时序不作本Task新承诺。不启音频UDP/硬件，不改其他handler/客户端/视频。当前尚未本批测试或产品验收，视频仍暂停。
