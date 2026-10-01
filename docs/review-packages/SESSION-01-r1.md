# SESSION-01 Review r1

对应 [Task](../task-packages/SESSION-01.md)，状态只见 [指挥中心](../AI_COMMAND_CENTER.md)。
最终当前交付统一绑定[BATCH-R1门禁包](BATCH-R1-r1.md)：300项内容ID64b829…，108文件1335/0/2，
下文f178等为阶段版本；最终Web9880的13项HTTP、12项生产JS与真实IAB退出另经验证，最终独立终审可接受，无必须项。
入场核验Web退出/token/多端调用链。已证实原代码没有/logout路由/按钮，现有token对象级撤销可复用，SSE仅detach应保留；
openStream旧错误回调无条件重连需加本端登录态/当前连接保护。
精确web路由/JS/新测试边界已冻结，Origin防护只限新增退出POST，不修改server认证逻辑。
非最后端UID资源清理错误已记录SESSION-02，本子候选不单独发布。
冻结边界、原代码证据、命令/环境/结果、版本ID、独立审查与修复轮次由主控按实际证据补齐。

第一候选原代码raw `session01/original-r2.*` 为6 failed/2 passed、退出1，修复8 passed；p0 Web9与admin24专项通过。
首次p0静态URL检查误匹配局部token赋值，失败已保留；改局部命名而不弱化原断言后通过。
独立初审要求补Cookie冲突优先、真实HTTPS删除Cookie、Origin细分、JS401/网络失败/旧onmessage守卫和本端游戏面板清理。
主控真实IAB（隔离loopback127.0.0.2、合成R1_UI账号）创建井字棋房间再退出：登录页已显示，fixed gpanel仍显示旧R1_UI房间；
首轮后端Web会话/token均0；合成TCP占位端因验收前空闲已被回收，首轮不能证明其它端存活。
该UI残留已实际复现，`ui/logout-panel-before.json`保存脱敏证据；后来夹具补正常TCP心跳并取得存活证据。

## 最终阶段候选与证据

- web SHA-256 `f17810084c212c6b7866c53f3ad5c6a0a31e3451fc9fce275a43e326edd9b5ae`；
  新测试 `2294d495a3593c9bbba0dddc01f585af61ffa598e3f4c1e599f66e690c2182d2`。
- 同最终测试原红：`session01/original-final/source`原295项逐hash核对、使用入场web字节d3c1cb2e…，
  完整raw `original-final/pytest.log`，11 failed/2 passed、真实exit1（预期缺功能负例）。旧r2/r3记录保留，
  r3原红使用中间测试版本，不能冒充当前版本；最终原红/绿已用相同2294…测试版本闭合。
- 当前六文件领域：13网页退出+9p0 Web+24admin+16R47+15R49+5multisession=82 passed，
  0失败/0跳过，六真实exit0，46.25秒，`session01-domain-final/summary.json`与逐文件log。
- 真实HTTPS、Cookie冲突优先/失效Cookie、body UID不选目标、Origin scheme/port/path/null/跨源、无Origin、GET无副作用与SSE detach均在HTTP矩阵。
- 实际生产leaveLogin/logout/openStream/renderGames/closeLobby函数在NodeVM运行，12项行为检查全true；
  `session01/js-runtime-result.json`与原始log；移除onmessage守卫的mutation仅使旧帧忽略项失败，证明不是静态字符串假覆盖。
- IAB隔离127.0.0.2真实浏览器：907阶段network/500保留Main、401回Login，最终f178加载hash由ready文件固定，
  创建房间→退出→清gpanel/侧栏→同页R1_NEW无旧缓存卡，另一同UID合成TCP心跳在线。
  `ui/final-ui-verification.json`及`ui/logout-final.png`；UI服务与临时tab均已清理。
- 独立阶段审查：`file_auth_review`核对代码、最终同hash原红/绿、82项域、Node行为与mutation、真实UI，
  无未关闭代码/测试必须项，可衔接SESSION02。此结论不推导最后UID端资源已修复或R1全量/里程碑通过。

本阶段没有执行完整全量，按BATCH-R1最终候选统一执行；不提交/推送/合并/发布，不复制真实用户数据。
