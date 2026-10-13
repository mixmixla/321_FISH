# SYNC-LATEST-MAIN-01 v1.2 — 同步本轮期间推进的上游

2026-10-13。属于用户本轮同步与有限试用授权，root冻结有限下一Task；状态及前置见
指挥中心。当前批次正常full自然结束并保存后才实施，不中断或并行重复全量。

## 版本与目的

入场main08d263b之后，上游现推进到52d5ff00c53c2e104811048a2db55d6b53e432cc：
d6105df P2图标/资源双端接入与52d5ff0桌游位图层/素材/三新增测试，64文件改变，
含client.py/client_gameui.py/web.py/ui_design.py及widgets，不是纯文档推进。
本轮候选3877a5d4cbbbf25364303210e1f0f74b4eeac542保留GemCity、拉密、Kalah、
Blokus/HUD和资料校正；它的165文件full是08基线候选，不能当新main整合版验证。

`git merge-tree --write-tree 3877a5d 52d5ff0`只预检Git对象，exit0、候选tree
3b5b4431ba8c50a33e5621d73fcc30a6cfcad954、0文本冲突；没有改工作树或建立merge commit。
这不是行为兼容或视觉接受，新的上游必须纳入实际审查与同版验证。

## 所有权与限定动作

root唯一治理及client.py/client_gameui.py/web.py整合作者；原UI/文档/fixture窗口闲置，
实施前确认无旧作者/进程，保护原目录c864234全部dirty/index。使用已保存干净任务
分支或另独立worktree；普通merge已fetch的main，不reset/clean/强推/rebase覆盖旧证据。
已有资料与来源commit不改成新源码实测，保留两个parent及明确整合diff。

仅同步现有上游与本批修复，确认用户自己的上游代码全部保留。本Task不批准按
docs/superpowers新设计扩大美术方向/新增产品特性，不运行素材生成器或应用构建。
若文本冲突，按两侧真实功能保留做最小整合；行为缺陷先保存具体失败和范围，再冻结
后继有限整改，不通过删除断言、增加skip、改timeout或采用“无新增FAIL”替代全绿。

## 验证与完成条件

- 独立读合并实际差异，确认本批购买原子性、最近空选、双方参数/点击与陈旧上下文
  守卫、紧凑控制/HUD均保留；上游图标、位图层和现有功能未回退。
- 相关领域含本批输入、UX双端及新位图/截图测试；新增opt-in先核原合同与门禁分类，
  环境缺失/跳过按证据记录，不放宽本批原跳过要求。
  v1.1只读细化：test_boardgame_assets默认3个像素合同，test_boardgame_asset_img默认
  3个桩/解码/真Tk合同；本机缺Pillow/模块/Tk导致环境skip视为前置未满足，不当通过。
  test_ux_visual_chat_shots整模块visual、18参数场景需--run-visual，默认opt-in不算
  视觉接受；先独立核子进程/private desktop/固定截图输出与瞬时Tcl重试证据合同，
  未满足前不启用该截图模式、不复用上游上传截图为当前候选接受。
  v1.2独立只读已确定：_gui_hint原regex漏pytestmark = pytest.mark.visual，新shots
  会被分类desktop=None；即使--run-visual也不能隔离。该测试含屏幕bbox抓取和Escape
  keybd_event，当前禁止启用。默认18个visual opt-in由conftest跳过只记未验，必须
  单列为上游新增opt-in，不能与本批原2个混同。启用前另冻结门禁分类与子进程私有
  desktop证据整改，不能把截图模式直接纳入此SYNC执行；本Task只做默认安全验证。
- 源码/依赖/测试实际改变后，唯一root完整同版新run，绑定输入hash/单attempt/cleanup/
  exit和原raw；旧2323P3F与165文件08候选结果全部保留。
- 独立终审无MUST后root技术接受限定源码整合；普通任务分支commit/push，PR403不
  重试，main禁止push，不merge到共享main/发布/真实资料/公司/CP4。15:00北京收尾。

EXE完整游戏/自然退出、非开发Windows、真实LAN及最终视觉/DPI仍是后继验收，不由
源码同步或全量自动完成。
上游client.spec新加作者机器绝对vosk models路径及collect_all('vosk')；本Task不构建，
保留为后继打包可移植性实证风险，不借同步自动修改构建/生成器或安装依赖。
上游已有文档尾空格只读已观察；导入差异的diff-check与本Task相对最新main的新增
差异分开记录，不冒称上游历史空白检查全绿、不自动重写用户上游文档。
