# UX-VISUAL-CHAT-01 scoped public-candidate audit

Audit date: 2026-10-10 (Asia/Shanghai)

Scope was intentionally limited to the proposed UX-VISUAL-CHAT-01 increment against `_tmp_gui/ux-visual-chat-01/baseline/manifest.json`, plus the three explicitly named ignored preview images. This is not a full-repository privacy review.

## Candidate boundary

The boundary record identifies 12 changed original files:

`client.py`, `docs/AI_COMMAND_CENTER.md`, `docs/design/UX-01.tokens.json`, `docs/任务清单.md`, `dpi.py`, `test_gate.py`, `tests/test_local_prefs_rules.py`, `tests/web_navigation_probe.cjs`, `theme.py`, `web.py`, `widgets/msg_list.py`, and `widgets/session_list.py`.

It identifies 15 new public files in that snapshot: six `docs/review-assets/UX-VISUAL-CHAT-01/*.json` metadata files, the task/review Markdown versions present at audit time, four `tests/test_ux_visual_chat_*.py` files, `tests/ux_visual_chat_probe.cjs`, `ui_design.py`, and `widgets/design_controls.py`. Later root-authored task/review replacements are outside this audit snapshot.

The scoped new files contain no TLS private-key blocks, literal passwords, bearer/API keys, token values, absolute user-home paths, or external endpoint values. The new test fixtures use `tmp_path` synthetic `prefs.json`/`history` paths (`tests/test_ux_visual_chat_regressions.py:27,121-124`) and synthetic names/messages only.

## Review assets and design material

`docs/review-assets/UX-VISUAL-CHAT-01/` contains JSON manifests, boundary metadata, token-export metadata, and run receipts only. It contains no PNG/JPEG/WebP/GIF/BMP, executable, archive, PEM, PFX, P12, or KEY file.

`current-source.json` and `entry-source.json` are path/byte/hash manifests. They mention inherited public source filenames related to credential tests at manifest lines 430, 735, 750, 835-865, and 1175; they do not embed credential values or storage contents. `runs.json` records `_tmp_gui/test-gate/...` summary/log paths, hashes, exit codes, and cleanup flags; it does not embed raw log bodies.

`docs/design/UX-01.tokens.json` is the only changed design binary-adjacent artifact: its diff adds formatting, `on_accent`, 11/10pt font roles, and dark semantic colors. It contains design tokens only. The 13 design preview JPGs under `docs/design/previews/` are byte-identical to the baseline.

## Explicit ignored preview images

The three requested ignored files were inspected in place and were not copied:

- `_tmp_gui/ux-visual-chat-01/before-native-wide.png` — old synthetic desktop preview; title identifies UX-VISUAL-CHAT-01, and visible names/messages are synthetic.
- `_tmp_gui/ux-visual-chat-01/after-native-r1.png` — early 雾岸 candidate preview; same synthetic fixture and app-only pixels. This is an early 10pt desktop stage, not final 11pt same-version acceptance.
- `_tmp_gui/ux-visual-chat-01/after-web-r2.png` — synthetic Web chat preview; app/UI pixels only, with synthetic names and messages.

No desktop, browser chrome, other application, real account, real conversation, credential prompt, or private user material was visible in these three images.

## Exclusions and limitations

Ignored `prefs.json`, `history/`, `audit/`, `server_state/`, `crash.log`, raw run logs, downloads, TLS material, and credential storage were not opened. No `git credential` command was used. The inherited account/storage dirty tree and unrelated public historical review assets were not re-audited under this scoped request.

Scoped result: no sensitive value or non-synthetic screenshot was found in the proposed UX-VISUAL-CHAT-01 public increment; the manifest-only inherited credential-test path names should be treated as metadata, not credential evidence.

## 本PR排除项补注

上述独立审计针对原开发增量，列表中的tests/test_local_prefs_rules.py仅是本地静态引用计数修订；最新main没有local_prefs模块，该文件及模块明确不在本PR transfer/提交内。最终候选范围以transfer.json和实际diff为准，原审计保留不改写为全仓或全部最终资料审计。
