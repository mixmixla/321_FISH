# GATE-FIXTURE-01 v1 — 对齐已合并导航与输入区测试合同

2026-10-13。本轮本地自治范围内由root冻结为READY；执行状态见指挥中心。仅修两个
测试文件的现行夹具/断言合同，不修改产品、run.py/test_gate、依赖、skip或超时。

## 正式对照与现行合同

原158文件全量2323P/3F/2S保留。干净main08d263b与购买候选2826784在同环境、同
选文件门禁各20P/3F，原证据见FOLLOWUP-20261013/failure-comparison.json；只是
两文件对照，不称基线full。三条失败根因：Web夹具遗漏closeLobby的真实导航依赖；
R32两条旧1行断言与当前自动3..6行行为冲突。旧UX Task v1.5没有明确批准test_r32，
本Task明确冻结补正，不能借旧注释解释为产品仍须1行。

- test_cc02a_web_kick.py：抽取真实uxSelectNavigation；合成DOM提供chat/game/moments
  dataset、可观察classList.toggle和setAttribute/removeAttribute。保留原13认证checks
  及len==13；另断言kicked后仅chat有on/aria-current，game/moments清除。禁止noop导航。
- test_r32.py：单行从6收缩、count异常的严格期望改3；保持99→6与同高不config。
  自动合同为max(3,min(6,n))；手动为max(n,manual)，可低于3、高于6，内容继续增高。
  新增manual2、manual8、n9/manual4、count异常/manual5四个严格行为案例；更新旧测试
  描述。保留其余20原行为及Tk/Windows既有skip，不扩展跳过/吞异常。

## 所有权与验证

gate_diagnosis代理独立worktree `_tmp_gui/gate-fixtures-20261013`，branch
test/gate-fixtures-20261013，basebb84967，只写上述两测试及ignored本任务合成原证据；
root写Task/Review/中心/投影。不得改root dirty或client.py；UI窗持有client_gameui.py/web.py。
普通commit交SHA、不push/PR，不全量/构建。先两文件专项，再必要输入区/Web领域，
单attempt/hash/source/cleanup与RED基线对照可审阅。独立审查无MUST后root决定整合；
完整候选全量由root唯一安排，专项通过不替代原full FAIL。禁止merge/release/main push、
真实用户资料/公司/CP4/系统设置；14:30不新开大任务，15:00北京时间收尾。
