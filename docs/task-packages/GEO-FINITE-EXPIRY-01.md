# GEO-FINITE-EXPIRY-01 v1 — 位置附带时间不得污染持久历史

2026-10-25 READY / INDEPENDENT_DESIGN_REVIEW_0_MUST（identity_scout）。用户本轮有限可靠性开发与并行工作授权，base main
`4690d0ca07811429b66a73c67239df643481cf9c`。root在已交付定时修复的同类输入检查中发现：
合法坐标的live位置若expire为JSON字符串NaN，现有min/max保留NaN，CHAT将geo写入bus，
durable全量快照验证拒绝非有限JSON并调用_fail_store。冻结设计时尚未动态复现，不将静态链当实测。

## 冻结范围

仅修改server.py的_san_geo及新增tests/test_geo_finite_expiry.py。root唯一产品/测试写入，
与server_scout的独立local_identity目录修复无共享写文件；identity_scout独立设计/代码/原件审查。
本Task若READY则与UID-DIRECTORY-RACE-01组合一次最终full，不改此前已验收的定时校验。

经纬度float转换溢出视同现有TypeError/ValueError，丢弃无效geo，保留正常聊天正文语义。
live expire转换错误、溢出或非有限值统一使用现有缺省0，再沿当前TTL下限/一小时上限夹取；
输出须有限。有限合法值、数值字符串、坐标精度、静态位置与权限/广播/持久化流程保持。
正Infinity原来会夹到上限，现明确按无效非有限输入使用缺省下限；不把原Inf控制例称已污染。
不改变实际位置采集、GUI、客户端协议、Store恢复、依赖/门禁/系统配置或数据迁移。

## 验证

1. 新测试原产品RED：NaN输入通过真实CHAT/全新durable Store/Session，先force persist再判断健康，
   须实际触达原FAILED；不得先因字段断言失败而没有走到原故障链。合法JSON字符串作为实际请求。
2. 参数化NaN/正负Infinity/转换溢出/已有非法类型与有限时间边界；验证落盘/广播geo为有限范围，
   无效坐标丢geo且正文仍发送。原有正常位置卡片、有限数值字符串和静态位置保持。
3. GREEN真实durable仍READY、stop未置，正常后续聊天可保存并重开恢复；不打开定位、音视频或网络外部调用。
   共享此清洗函数的GEO_LIVE也须有合成广播对照：输出有限expiry、不入bus，不使用实际位置设备。
4. 相关位置/Store/恢复领域及独立原件审查；两最终补丁组合后root唯一新候选full。
   RED/GREEN输入绑定、真实退出/原件/旧失败保留，最终独立技术/公开审计后仅有限AI_ACCEPTED。

原件仅合成数据与ignored本地。06:12 UTC后不开大任务、06:27收尾；未验收不推送。
已验收代码/测试/项目文档/脱敏摘要沿用户许可正常提交快进main/非强制push，不PR/绕保护/发布或上传EXE/raw。
完整GUI、自然退出、物理LAN、STT和现有EXE包含修复不属于本验收。

## 验证夹具补正（合同不变）

首次RED为11F17P，独立durable用例真实进入FAILED。首次领域命令误选不存在的测试路径，
门禁入口记录exit2且未启动测试；改为实际五路径后123P2F，失败恰两个新GEO_LIVE夹具只有发送者，
与既有广播排除发送者合同不符。identity_scout独立分类0 MUST后，仅新测试login支持昵称参数，
为这两例增加不同昵称真实接收Session，保持len/finite/TTL/不入bus断言；产品字节不再改。
原件全部保留，不把初次NaN live的收件错误称有限值缺陷证据。

root独占server临时恢复到原产品，独立控制器finally恢复已修字节并核SHA。修订后同测试RED-02
11F17P（NaN live实际进入isfinite失败，durable实际FAILED），GREEN-03为28P；原四旧领域97P
仍对应相同产品字节。独立实际代码/四阶段原件/组合输入审查0 MUST，最终仍须组合全量。
