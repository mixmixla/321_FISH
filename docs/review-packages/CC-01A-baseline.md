# CC-01A 入场基线与内容快照

本记录对应 COORD-01 v1 的 CC-01A 资料迁移。它描述 2026-10-01（Asia/Shanghai）
捕获的 dirty 入场快照，不是当前状态数据库，也不是测试通过证明。状态和下一动作
只见 [AI 指挥中心](../AI_COMMAND_CENTER.md)。

## 快照身份

| 项目 | 入场值 |
| --- | --- |
| base / HEAD | `fbdd915e8fd5947e01b6f4d371b3cd1e37020729` |
| local `origin/main` | `fbdd915e8fd5947e01b6f4d371b3cd1e37020729`（未 fetch） |
| branch | `fix/cc-01a-admin-credentials` |
| dirty | `true` |
| tracked / untracked | `20 / 2` |
| 文件总数 | `22` |
| 完整入场 patch | `_tmp_gui/coord-01/incoming-22.patch` |
| patch SHA-256 | `49e1f238774a25c8557c9465ba28b00013322bce5f2f096c3a8ccba189ad8c6e` |
| 内容集合标识（manifest） | `607471b077692fb1ff17b836904b6556501ad5e66ccdb6da06cbbe4ec7d43d6d` |

`incoming-22.patch` 是本次保存的原有 22 文件完整差异。上表的两个哈希来自
`_tmp_gui/coord-01/incoming-manifest.json`；原始 patch 和 manifest 位于 ignored
本机资料区，不进入公开文档。

## 22 文件路径、状态、字节数与 SHA-256

下表按入场 manifest 原顺序记录原始文件的原始字节快照。`M` 表示 tracked 修改，
`??` 表示 untracked 新文件。

| status | path | bytes | SHA-256 |
| --- | --- | ---: | --- |
| M | `.agents/skills/fish-assistant-dev/SKILL.md` | 4200 | `9761bddfea2856cbeaf3f962384583a8f64f48733b05c35a8cfab1c0a6122146` |
| M | `.agents/skills/fish-assistant-dev/references/invariants.md` | 7554 | `37bd35ee6bb3721c63cfa6b39a97a56ba42bd97bec30db75a190c86ab5e7ac59` |
| M | `.agents/skills/fish-assistant-dev/references/project-map.md` | 9326 | `9b32cec25c72397e6b2c61a41cdcd611d1ecb4d5a126b0b6a99692327de53ed5` |
| M | `COLLABORATION.md` | 5509 | `3759c72e9a35c09eeceaa21f2ff9f25f0f5852fc43c5459f3a96bac380c0160b` |
| M | `INVITE_FRIEND.md` | 4741 | `0accd127929577086be2e398194e68ad386161b4d053faf7d9fbe9fed48c984f` |
| M | `PROJECT_MEMORY.md` | 8883 | `7ba640d5178b7e4134a295029595f83c82a0d84d3ac6eed0b0b8e2a0a52bd33d` |
| M | `README.md` | 1825 | `85fb0fae6989f759b1037a4ddcb58435909b79b3595bb80144039a3d0d10ec88` |
| M | `client.py` | 660058 | `1e3280d0db2c94399b3ecc6c92a4221b01b2f873c0469aaadf4ace03a5fc6380` |
| M | `client_core.py` | 136698 | `f2ba79e530154f32dce75b9778e130e9409e9890d2aa28c19622f863eecd5081` |
| M | `config.py` | 18191 | `744beee0e9f29d52f2068d3ced54b80f44c607d5016b37d73ba98454d9eb2d58` |
| M | `docs/任务清单.md` | 22920 | `b830165ee4b930877f96b8127bb5c2e47043eaa1eccc6afbfebc441fc98611bd` |
| ?? | `docs/管理员凭据与公开仓库安全.md` | 3824 | `c7705cf92937452a41388e366af8a0c131cb1da668c0712c716658eaf1beb786` |
| M | `protocol.py` | 21032 | `80ea178b57d023b54cccccf9813dd1b0a66391fcf5d413ddb6147fe478f2ed97` |
| M | `server.py` | 326513 | `d518297ee23b3032369b408a15d4c4ab53671d07920091141d15a0fab80a4a2d` |
| ?? | `tests/test_admin_credentials.py` | 24107 | `3414dab20c3f4e9b173b099e59c561865acbc20a4c7683dbf4ef8310a9121642` |
| M | `tests/test_admin_groups.py` | 10591 | `ae508873d2a9be246abc650c2981b68638df5e5763897d92619905c3fdb59ce0` |
| M | `tests/test_admin_groups_web.py` | 4263 | `7534b32916ddb652ec468289d55287baad1a0bcd1ecccb43ddcc786391dffb30` |
| M | `tests/test_audit_server_security.py` | 6415 | `aea875574fd33b80c3f3a7d6c415a1687557ab9fc2dca7e0f024b470acb4c66d` |
| M | `tests/test_invis.py` | 6812 | `244e073d97dacfb38ae59ba80e90d41cdc29e0ee00fe502975b8d13c7e05ef18` |
| M | `tests/test_r53.py` | 14051 | `25dba9cc32ea64bac43fd5d285987732357a160c51c6da39367d557697e211d3` |
| M | `tests/test_r54.py` | 12871 | `943587b754f7f79b39494562db7adea87dfe54158999ecb2c4df26633ddf5536` |
| M | `web.py` | 481290 | `d3c1cb2e9633a897067336a22a68b63c0f40b39261c252ad9a070400e7f09be1` |

原始 manifest 的 22 行是与 CC-01A 一起保存的管理员交付入场差异：源码和相关测试
有管理员凭据/权限变更，旧 Review 将其余 9 个文档/技能文件称为配套材料。由于原
批准文本缺失，不能据此证明这 9 个文件逐文件获批；本表只记录观察到的文件归属和
字节快照，不扩展需求。`PROJECT_MEMORY.md` 中夹带的 Excel、登录窗或其它历史报告
也不能自动成为 CC-01A 证据，须按各自原始文档、diff 或日志逐项核实。

## 哈希算法与局限

- 表内每个文件的 `sha256` 是对该文件原始字节计算的 SHA-256；`bytes` 是同一快照
  的字节长度，不是字符数。
- `patch_sha256` 是对 `incoming-22.patch` 原始字节计算的 SHA-256，可绑定保存的
  完整 patch 内容。`content_id_sha256` 的聚合算法是：先输入 `UTF-8(base)` 和一个
  NUL 字节，再按 22 个相对路径的 Python `sorted`（默认大小写敏感 Unicode 顺序）
  逐项输入 `UTF-8(path)`、NUL、该文件字节长度的 ASCII 十进制表示、NUL、文件原始
  字节，最后取 SHA-256。它不是对 hash 表 JSON 的再哈希。
- 快照绑定的是 base、分支、dirty 标识和捕获时文件内容，不绑定测试日志、执行命令、
  Python/pytest 环境、干净 main 对照或后续工作树状态。原有 22 文件的历史测试日志
  没有内嵌这个新内容 ID；patch/hash 也不能证明某条历史测试结果确实运行在这些字节上。
- 原始 patch、`run_gate.py`、各轮 summary 和日志只留在 ignored 本机资料区；本记录
  不复制私有聊天全文、prefs、运行数据、实际口令/token 或 TLS 私钥。

## 使用规则

后续资料审查应先核对本表与 `incoming-manifest.json`，再核对 [CC-01A Task](../task-packages/CC-01A.md)
和 [CC-01A Review](CC-01A-r1.md) 的证据边界。本表是不可改写的入场历史快照；
COORD-01 已批准的 `COLLABORATION.md`/`PROJECT_MEMORY.md` 文档增量应在批次 Review
中单独记录，不会使本表失效。若代码、测试或其余 20 个保护文件相对本快照发生变化，
应建立新的交付版本并重新审查，不能改写本表或沿用旧 Review 的结论。
