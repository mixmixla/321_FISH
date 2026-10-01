# SESSION-02 Review r1

对应 [Task](../task-packages/SESSION-02.md)，状态只见 [指挥中心](../AI_COMMAND_CENTER.md)。
最终当前交付统一绑定[BATCH-R1门禁包](BATCH-R1-r1.md)：300项内容ID64b829…，108文件1335/0/2；
最终server3b99保留本项保护，当前7项cleanup全部通过，最终独立终审可接受，无必须项。
保留最初调查与各轮证据；阶段已满足，最终批次全量/版本统一验收尚未完成。
精确函数/保护边界、回归证据、版本ID与独立审查按实际结果记录。

只读调查确认unregister每端token撤销/代表切换/min_idle正确，但每端都drop UID传输/游戏，且锁释放后重连窗口可能误清新端。
主控合成动态探针 `baseline-probes/result.json`：非最后端其它Web/TCP仍活，传输与玩家却被删除、对端收到误file_cancel；
在logout audit回调的真实调用窗口重登同名UID，新token活而传输/玩家仍被旧注销删除。探针只用隔离合成对象。
语音房名册非最后端在这两个探针均保留；没有服务器持久1v1 call表，不能发明新call registry。

## 当前阶段版本与整改证据

最初4项回归原代码3 failed/1 passed、修复4 passed；旧595候选在主控追加受控探针中仍误发当前活端下线，
并删除重登后已成功重新加入的群及群语音名册。`remaining-races.json`、probe源码与raw均保留。
追加6项版本原竞态2 failed/4 passed，修后6 passed；后续独立审查发现检查→snapshot极窄窗口，继续整改而未提前通过。

最终候选：server `3790d676401f4a75962c4ddff9895c25138fda49928ea636abe298e7b4652fe5`，
test_session_cleanup `c12e6b1c17e6cedccdaf43698a0cbd50dc65ab6d4d80b80d161ff746e49cd5b8`，实际文件hash已复算。
UID通知有效性与收件人snapshot在同Hub锁内，锁外发送；通用system广播不再解析昵称字符串。
传输/游戏/语音内存清理确认离线与修改序列化，空群GC复查当前成员；原4/6项与中间版本均不能冒称最终测试版本。

实现者当前报告6项专项及multisession5/R49 15/R72 45/admin24通过；R47老化释放16通过记录保留。
当前独立终审继续核对真正的提交/snapshot边界及不同通知代次，不由旧初审替代最新版本结论。
所有原始命令/退出码/日志位于 `session02/`，本阶段尚未执行批次最终全量。

阶段独立终审已核验3790/C12候选可衔接GameB：同Hub锁的UID检查/snapshot、pending rec对象身份、
锁内实际资源清理与群GC复查均闭合，锁外发送；没有生产代码必须项。最终6项绿与领域5/15/45/24、
R47老化释放16项证据保留。本结论不代表批次全量完成。
证据限制：原竞态红为595源+8EB测试，最终绿为3790源+C12测试，C12控制屏障改为最终私有before_snapshot接口，
不可宣称两轮字节同版；`remaining-races.json`是旧候选历史动态结果。快速重登再注销正向循环可在批次最终全量前补覆盖，
源码`current is rec`身份保护已静态核验，不能仅凭旧6项报告宣称覆盖所有交错。

随后主控补`rapid reattach → fresh last disconnect → old notice恢复`正向屏障回归：
新端资源最终全部清理、新代通知恰好一次、旧记录不消费新代，不残留pending记录。
当前7项全部passed（`client-session-extra/test_session_cleanup.log`，真实exit0），
原6项与新7项不是同字节测试版本；最终源码/测试hash随批次manifest统一记录。
GameB审查已核验S2 UID、群GC、notice保护保持；最终full前不把历史3790 hash当整个server的当前hash。
