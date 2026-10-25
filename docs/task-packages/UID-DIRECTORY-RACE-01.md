# UID-DIRECTORY-RACE-01 v1.1 — 并行首次登录共用父目录

2026-10-25 READY / INDEPENDENT_DESIGN_REVIEW_0_MUST。来源：用户本轮约90分钟自主本地开发授权，
前批LOCAL-RELIABILITY已有限验收/正常合并，Git/API核main `4690d0ca07811429b66a73c67239df643481cf9c`。
identity_scout已独立审查同范围草案0 MUST；root据此冻结本UID任务，06:12 UTC后不开大任务、06:27收尾。

## 有限目标

两个真实ClientCore使用同一history ROOT、同一durable scope而UID不同，首次接受WELCOME时，
ROOT/v2/scope任一公共父层都可能先由另一Core创建。允许已经由竞争者创建的普通目录，
不因此触发local_storage/manual_login_required。各UID目录、历史与密钥必须保持隔离。

仅改local_identity.py的scoped_directory：无论预存、自己新建或mkdir遭FileExistsError，
都必须lstat并拒绝非目录/symlink/reparse（0x400）；只容忍FileExistsError，其它IO错误保持拒绝。
不递归跳过父层检查，不改Core、crypto、协议、数据迁移，不保证抵御lstat之后任意恶意替换。
同UID首次密钥生成的exclusive-create/半写读取竞态独立保留，不宣称同UID并发初始化已解决。

## 归属与验证

server_scout在新独立uid-directory-race-20261025工作树唯一写local_identity.py与
新tests/test_uid_directory_race.py；root保持local-reliability-20261025树作集成/Task/Review/中心/投影/
必要稳定事实/最终组合验证。identity_scout只读独立设计、代码与原始证据审查，不参与实现。
v1.1仅记录组合执行决定：root另按独立GEO-FINITE-EXPIRY-01 Task修改server.py及其新测试，
两个模块无共享写入者，最终合并一次full；本UID产品/测试合同及server_scout两文件归属不变。
既有server/prefs修复不改；所有原测试/断言/skip保持，不改依赖/门禁/系统配置。

1. 新回归用两个真实Core、不同UID，按ROOT/v2/scope参数化争点。
   A完成缺失预查、调用精确mkdir前用Event暂停；B完成WELCOME和合成私聊写入，再放A。
   不sleep追竞态；旧版须实际观察A的FileExistsError/local_storage，而非门或fixture超时。
   修后两端身份有效，B历史与key hash不被A改，双方标记不互读，所有线程有界join/stop。
2. 竞争者创建普通文件、伪symlink/reparse的拒绝对照及PermissionError保留，原件字节不变。
   明确覆盖本调用mkdir成功后仍须lstat并拒绝模拟重解析的新分支，不只检查预存或碰撞路径。
3. 既有history UID/UID prefs/Core/crypto领域回归；同测试RED/GREEN与source manifest绑定，保留真实退出和原件。
   独立代码/原件0 MUST后，root集成最终字节完成一次新候选全量；失败先分类，不重试抹除失败。
4. 当前/冻结/快照、完整日志/计数/清理/旧skip与源身份复核，独立终审后才有限AI_ACCEPTED。
   已验收代码/测试/项目文档/脱敏摘要可按用户许可正常提交快进main/非强制push，不PR、不绕保护/发布/上传EXE/raw。

仅新建合成资料与必要loopback；不读取真实prefs/聊天/密钥或改个人记忆。原视频4759及所有历史失败保留，
不继承/诊断视频，不开硬件。完整GUI、自然退出、物理LAN、STT和现有EXE包含新修复仍未验证。
