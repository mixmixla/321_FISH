# UI-BOUNDARY-01 r1 — 修复交付与有限风格提议

**IMPLEMENTED / READY_FOR_INDEPENDENT_REVIEW**。不是AI_ACCEPTED或用户审美认可。[冻结范围](../task-packages/UI-BOUNDARY-01.md)。

独立commit **c5492396e01e7edc37333dc7a0694141b3110788**，base **08d263b2a78b7a6df0b888616e2fbf44793182b8**，branch `fix/ui-boundary-20261013`，工作树 `D:/Project/321_FISH/_tmp_gui/ui-boundary-20261013` clean。3文件，333新增/68删除；只有client_gameui.py及两个新增测试。client.py相对base逐字节（归一化换行）不变。未推送/PR/合并/发布，未跑全量或构建。

## 结果

- Blokus旋转/跳过固定在底部；拼块保留24px高，不再靠压到12px硬塞。空间不足时分页，2/3/4人全部21块均能经过实际点击选择；换页保留已选块，换向不改协议/规则。
- HUD裁剪先留自身，在卡片数量上限和宽度双重裁剪后仍显示准确+N。高UID、长昵称/大积分、472/480宽经过真实Tk字体边界验证。
- 局部风格样例在Blokus：白色标题/操作面板、深色正文与语义辅助字、14pt标题/11pt层级/9pt紧凑操作、7px按钮与12px面板圆角。标题长昵称收窄省略，四色玩家标记和棋盘色保持。

## 风格提议：沿用雾岸的克制桌面棋盘

这是现有设计的局部样例：复用docs/design/UX-01.tokens.json与ui_design.py，不引入平行颜色或字体系统。移除该游戏的渐变标题，用一枚小拼块矢量标记保留识别；避免下载/生成装饰位图。选中块用游戏深绿填色，方向数字与形状预览同步反馈；普通控件白底，辅助字改text_secondary。棋盘仍是视觉中心，正常宽度显示全部拼块，窄窗用页码和前后控制保持完整操作。

依据：旧480窗在只有两列、21块、四玩家战况下，旋转/跳过落在视口外；旧淡棕辅助色用于白底时难读。新布局把固定动作与可分页库存分开；选中/换向反馈在同一视线区，标题、战况、选择、固定动作四层稳定。正常尺寸右侧留白是给棋盘和固定动作留出的空间，不新增装饰填充。

建议主窗口先评估此样例的层级、24px拼块目标和窄窗分页，再决定是否推广；本提交不授权全局换皮或其他游戏美术扩展。

## 真实截图与可运行样例

实际BoardFocusWindow类与GameWindow._render_to从client.py原样提取执行，配真实Tk Toplevel/Canvas和真实规则合成快照；两版本使用相同场景与尺寸。客户端其余部分未导入，因此不接触prefs/账号/网络。Frame拖动绑定在夹具中省略；截图固定alpha=1、雾岸外层调色与Microsoft YaHei UI 11pt，用于公平比较；不声称应用默认透明度已修改。真实Tk事件通过该专注窗原来的Button-1入口触发选块/翻页/换向，非物理鼠标注入。

Pillow只捕获owned窗口HWND；Windows私有桌面运行，截图后关闭全部本次窗口。当前Tk scaling=1.333333（本机100%）；125%/150%未测，不改用户缩放。外机、LAN、EXE和完整登录/大厅流程未测。

| 场景 | 基线08d263b | 当前c549239 |
| --- | --- | --- |
| Blokus正常920×720 | [前](../review-assets/UI-BOUNDARY-01/screens/actual-before-blokus-normal.png) | [后](../review-assets/UI-BOUNDARY-01/screens/actual-after-blokus-normal.png) |
| Blokus窄窗480×400 | [前](../review-assets/UI-BOUNDARY-01/screens/actual-before-blokus-compact.png) | [后](../review-assets/UI-BOUNDARY-01/screens/actual-after-blokus-compact.png) |
| 八人HUD正常 | [前](../review-assets/UI-BOUNDARY-01/screens/actual-before-drawguess-normal.png) | [后](../review-assets/UI-BOUNDARY-01/screens/actual-after-drawguess-normal.png) |
| 八人HUD窄窗 | [前](../review-assets/UI-BOUNDARY-01/screens/actual-before-drawguess-compact.png) | [后](../review-assets/UI-BOUNDARY-01/screens/actual-after-drawguess-compact.png) |

另有[正常选中/换向](../review-assets/UI-BOUNDARY-01/screens/actual-after-blokus-normal-selected-rotated.png)与[窄窗选中/换向](../review-assets/UI-BOUNDARY-01/screens/actual-after-blokus-compact-selected-rotated.png)。[基线元数据](../review-assets/UI-BOUNDARY-01/screens/actual-before-capture.json)/[候选元数据](../review-assets/UI-BOUNDARY-01/screens/actual-after-capture.json)保存source、两个源码hash、实际Canvas尺寸、每张PNG hash、原Canvas文本与热区。初始自有画布/迭代风格截图均保留，正式配对用actual-before/actual-after。

运行人工查看样例（自己的合成专注窗和四种场景切换，关闭窗口退出）：

```powershell
& D:/Project/321_FISH/.venv/Scripts/python.exe -B -X utf8 D:/Project/321_FISH/_tmp_gui/ui-boundary-evidence-20261013/capture_focus.py D:/Project/321_FISH/_tmp_gui/ui-boundary-20261013 D:/Project/321_FISH/_tmp_gui/ui-boundary-evidence-20261013/screens sample
```

本运行器在独立证据目录，不增加项目入口文件。截图工具初次CreateDesktop失败及能力边界如实保留在`初始失败说明：_tmp_gui/ui-boundary-evidence-20261013/capture-initial-failure.txt`；必要提权后actual-before 4图、actual-after 6图均exit0，不拿源码图形坐标代替截图。

## 测试与证据

新增26个纯行为边界+3个真实Tk测试：2/3/4人、全21块、正常/480×400/472×360/480×300画布、分页完整可达、转向/跳过动作字段、非本人操作守卫、宽度隐藏数、实际字体自身积分不与阶段重叠、长标题不越界。

基线RED：14 FAIL / 12 PASS，exit1，`RED原件：_tmp_gui/ui-boundary-evidence-20261013/red/summary.json`保留。首次修复green三文件102 PASS，风格修订domain-final五文件110 PASS；最后长标题守卫形成新候选，并新增一个GUI测试后最终五文件 **111 PASS / 0 FAIL / 0 SKIP，exit0，22.107秒**。所有版本结果各自独立保存，没有覆盖失败/skip/削弱断言。

最终覆盖test_flagship_board、test_flagship_gui、test_gameui_compact_controls、test_gameui_compact_gui、test_gomoku_fx；43/6/26/3/33 PASS。[领域汇总](../review-assets/UI-BOUNDARY-01/domain-summary.json)、`逐文件attempt原件：_tmp_gui/ui-boundary-evidence-20261013/final/progress.json`、[核验](../review-assets/UI-BOUNDARY-01/verification.json)。五文件各单attempt、日志SHA256匹配、cleanup_ok均true。最终文件与gate源码副本相同，实际候选截图hash匹配最终client_gameui；source_content_id `ee54ab793090c5ec1cd6674d61f4b65870c2ed9f9f6ff36ddaccb0be8f3d89df`，fingerprint `4bae5d3cfe068238daf5c6059fe6721b314c2e9cdecd24035e38d097129b1f7b`。

```powershell
& D:/Project/321_FISH/.venv/Scripts/python.exe -B -X utf8 run.py test-all tests/test_gameui_compact_controls.py tests/test_gameui_compact_gui.py tests/test_gomoku_fx.py tests/test_flagship_board.py tests/test_flagship_gui.py --run-dir D:/Project/321_FISH/_tmp_gui/ui-boundary-evidence-20261013/final --label ui-boundary-final
```

命令执行cwd是独立工作树。`git diff --check`、暂存差异检查均通过。原开发HEAD仍c864234，本窗口没有写原目录应用、client.py或主治理文档；所有运行进程已自然结束。

下一动作：主窗口独立审查实际diff/本范围/原证据，评估风格样例后选择cherry-pick `c5492396e01e7edc37333dc7a0694141b3110788`。整合后的适用全量由主窗口唯一安排；本轮领域全绿不覆盖购买主任务历史full FAIL，也不等于产品/发布验收。没有实现或截图技术阻塞，独立审查与整合全量尚未完成。

## 主控独立接受（2026-10-13）

AI_ACCEPTED_UI_BOUNDARY_ONLY：独立Sol实际diff/111领域/raw/截图身份审查0 MUST；root亲自读185行Painter/HUD改动与两个新测试，并实际查看4组共8张配对PNG，确认正常与窄窗Blokus分页/固定操作可见、字层级清晰、HUD自身积分及隐藏数准确。只接受本修复与Blokus局部雾岸样例，不接受全局风格、47款、完整客户端/EXE/自然退出、125%/150%或发布。Tcl after诊断、近似字宽/库存缩减等覆盖限度保持。整合后的完整门禁仍待root协调，购买历史2323P/3F/2S不被此领域通过改写。
