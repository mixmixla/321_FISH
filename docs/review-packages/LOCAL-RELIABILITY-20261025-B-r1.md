# LOCAL-RELIABILITY-20261025-B r1

2026-10-25 IMPLEMENTED / INDEPENDENT_CODE_REVIEW_0_MUST / FINAL_FULL_PASSED / FINAL_TECH_REVIEW_0_MUST / PUBLIC_REVIEW_0_MUST / AI_ACCEPTED_TWO_FIXES_ONLY / MERGED_MAIN / REMOTE_VERIFIED。
范围仅[UID-DIRECTORY-RACE-01 v1.1](../task-packages/UID-DIRECTORY-RACE-01.md)与
[GEO-FINITE-EXPIRY-01 v1](../task-packages/GEO-FINITE-EXPIRY-01.md)。base已Git/API核main
`4690d0ca07811429b66a73c67239df643481cf9c`，承接本轮前两项已合并修复。

## 归属与范围

root在local-reliability-20261025树唯一写GEO server/newtest及集成资料/最终全量；server_scout在
uid-directory-race-20261025独立树唯一写local_identity/newtest；identity_scout只读独立设计、代码、
原件及最终技术审查。无同文件并发。两个代理显式Astra；FAST偏好实际服务回执不可见。
本轮用户授权有限本地开发、独立验收后普通提交/快进main/push，不PR/强推/绕保护/发布/上传EXE。

## UID目录竞争

`scoped_directory`只吞FileExistsError；预存、mkdir成功或竞争失败后均lstat，拒绝非目录、
symlink、reparse；PermissionError等其它IO错误保持拒绝。没有修改Core、crypto或迁移逻辑。
14例中三个真实双Core、不同UID在ROOT/v2/scope层以Event定位竞争，验证双方有效绑定、
合成私聊/密钥隔离；九个路径来源×非法对象检查、其它IO拒绝与普通现存目录正对照。
symlink/reparse为模拟lstat，不声称实际恶意系统替换测试。

`uidr25-red` 6F8P/exit1；三个Core真实FileExistsError/local_storage，另三个新建后检查缺失。
`uidr25-green` 14P与`uidr25-domain`五文件90P，均exit0；同测试字节，RED→GREEN仅产品变化。
GREEN/domain 504输入source `03f6aff0ffa9c37543b559f359f6845a02f83b447236925d6cd307d8bec09a37`。
原summary SHA依次为
`be83a477819d8827858e287e96c65d3e028228163ade9dfb4e402b75adb511b6`、
`4f8c722fa3cd3e31ada1d80ebad001514e5e54b1ce8f4b63a82ff50989b81386`、
`a8927d011cfc345ad3cfc77f61320d2615d175ea1af3a4276e95028e68340f7d`。
identity_scout独立代码/三阶段原log、退出、sandbox、清理、source审查0 MUST，root按两文件SHA接入。

## 位置过期时间

仅`_san_geo`新增两处OverflowError捕获与expire有限性检查；无效expire按原缺省0继续TTL夹取。
合法有限值、数值字符串、精度、静态位置与权限流程保持；+Inf从原上限改为明确缺省下限。
真实原故障为NaN写入bus后，全量持久验证拒绝非有限JSON并使Hub FAILED/停止；不把Inf称污染。

初RED `geo25-red` 11F17P，durable确实FAILED；其中NaN live例先失败在收件数量，不能当有限性证据。
首次领域选择包含不存在的路径，被门禁入口exit2拒绝且未运行测试。改选实际五文件后的
`geo25-green-domain-02` 123P2F：四旧域97P，两新live夹具只有发送者，而既有广播排除发送者。
此失败保留。只给两例添加不同昵称真实接收Session；原数量/有限值/TTL/不入bus断言不变。
产品此时已固定，未为测试改协议。独立审查支持此分类。

受控原产品对照由finally恢复候选并核SHA，修订同测试`geo25-red-02`仍11F17P：NaN live到达
isfinite失败，durable仍真实FAILED。`geo25-green-03`28P/exit0/1.789s；四旧域97P对应相同产品。
GREEN-03 504输入source `ab0b407fd09edebb16f17dd9b399f863fa00cf0b5d58300541ac61ab65bf31f4`。
四summary SHA依次为
`c459b752cd17a0e72d81a954a0ad28d863106e8e0c426d2be36e8e6a16b0f2c3`、
`b30aff094ce7a940078b3acbdd1725ff96a2c05d5d7ebd6f27554ae3e198b40a`、
`484c0a815924bf2bfa3620629c3d53b46343fb4a304e87968c20ef2d3625da5b`、
`b70818d1f443ed4120abb215fee7b7c7285c92831589312081f45be85636be72`。
identity_scout独立实际代码/夹具补正/四阶段原件及恢复SHA审查0 MUST。

## 组合全量与待办

505输入source `1f5f2de16d3acb5eac082596863cfb193a453f75ad0cffd7c322aac7ae9d4be5`，
相对前批503仅local_identity.py、server.py及两个新test变化。worker两旧测试为CRLF，
规范化内容与base相同，不混称各阶段raw source相同。root组合边界独立审查0 MUST。
唯一全量`lrb25-full`于05:36:54 UTC启动并自然完成：227文件3153P/0F/20既有skip，
actual shell exit0，818.796s；summary SHA
`55fd8fe1f9cb306e738a6a459de9244ded38ab5a0121e14abc801d96c4da17ad`。
root26项后验全true：227完整日志/计数/单attempt/清理/sandbox、505当前/冻结/快照一致，
旧225逐文件计数/20 skip未变，两个新测试14+28P，解释器/依赖/门禁身份保持。
七阶段原件、入口拒绝exit2与原产品恢复证据、前批全量与两个历史失败原SHA保留。
identity_scout独立重算227原log/计数/SHA/退出/单attempt/清理/sandbox/fingerprint，核505当前逐项
size/SHA/冻结/快照、旧225计数及20skip逐原因，七阶段/两个历史失败、依赖/解释器与source边界，
最终技术0 MUST。root据此有限AI_ACCEPTED仅本批两个Task；没有活动测试，不重复全量。
server_scout只审公开资料，非其UID代码自验：精确12路径、八个run摘要逐项与原件匹配、431相对链接、
中心投影/hash与隐私边界均0 MUST。server_scout另直接枚举全部24新增Git对象（1commit/11tree/12文本blob）
与Codex metadata，核最新有限验收与12路径，0 MUST后正常main快进/非强制push，Git/API双核
`8a4a27c1433f3b650c28635fb785106802932f7d`。fresh main仍为base，protected=false、可见rulesets空，
check-runs/status contexts/Actions均0（aggregate pending/total0），不称CI通过。
main仅两新test检出行尾不同，规范化及Git内容相同后对齐实测字节并刷新相同索引；505再次精确等full，
main工作树clean，无产品变化或重测。本末纯资料回执另审新增对象后正常推送，最终leaf以Git refs为准。
原件位于本地ignored的`_tmp_gui/uidr25-*`、`geo25-*`、`lrb25-full`及集成树
`_tmp_gui/reliability-b-20261025`。[脱敏结构化索引](../review-assets/LOCAL-RELIABILITY-20261025-B/evidence.json)
绑定七阶段与本次唯一full，不含原日志或用户数据。

暂停视频4759及0xC0000005、旧UID与本轮所有失败原件保留。没有修改个人记忆或真实用户资料。
同UID首次密钥初始化、lstat后恶意替换、完整GUI、自然退出、物理LAN、STT、现有EXE包含本修复
均未验证；此批不等同用户/Pro验收、完整里程碑或发布。
