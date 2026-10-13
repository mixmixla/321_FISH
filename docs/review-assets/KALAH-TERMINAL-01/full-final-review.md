# KALAH-TERMINAL-01 v1.1 — independent final evidence review

Reviewer `/root/kalah_domain_review`, 2026-10-13. The latest stop instruction is binding: finish this Kalah evidence review and source handoff only, with no new task, build, UI work, test retry or baseline rerun. Production, tests and governance were read-only throughout this review. Only separate ignored reports and file-hash verification helpers were written; those helpers import no production modules and execute no tests, apps, native APIs or builds.

## Final status

**FULL_FAILED / NOT_AI_ACCEPTED / NOT_MERGE_READY.** The required new-source full gate failed. The finite rule diff and completed domain review had 0 MUST findings, but that narrower result cannot replace the Task-required full gate. A documented commit/push of the candidate is not application acceptance, merge, release or a verified final binary package.

Read the actual frozen Task v1.1, current rule diff and tests, original RED/domain/full manifests, summary/progress and original raw evidence. Task v1.1 only changes the stopping instruction; its rule, 18-case and gate contracts remain the same. The actual `_sow` diff and test bytes remain the versions reviewed in `code-domain-review.md`.

## Version and source binding

- Source worktree `D:/Project/321_FISH/_tmp_gui/gate-collection-20261013`, branch `fix/gemcity-purchase-20261013`; implementation base/HEAD observed `2fa1c9eb5fc499c1bd424b36e2093f1f5bc84b69`, task change uncommitted at review start.
- Candidate source ID `1b5fa41cf53ab7146a000a37d9116b520c1c1c92e5421b9d7f7f6df29911d561`, **411 inputs**, identical in domain and full manifests and current bytes. The ID was independently recomputed using the existing runner's documented canonical-JSON hashing algorithm, without importing the runner.
- Current Kalah SHA256 `d64c0edaf201cbfa2c3d344ffc69b414e16104b6e746e96e3f5e556a71db6d11`; new test SHA256 `faa08c01749117ceb37f2b1066a8b7b095d857090069f4484cccb63502efae9a`.
- RED-to-candidate source sets differ only in `games_pkg/kalah.py`. The tests were not weakened or changed after RED. Dependencies, runner and sandbox remain unchanged across RED/domain/full.

## Exact observed gate results

| Phase | Files | Pass | Fail | Skip | Exit | Boundary |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Original RED | 1 | 7 | 11 | 0 | 1 | Preserved; old rule reproduces both defects, including a reachable initial-position sequence |
| Domain | 10 | 150 | 0 | 0 | 0 | Finite code/domain review only |
| Required full | 169 | 2457 | 2 | 20 | 1 | Candidate fails required full gate |

Full started `2026-10-13T13:33:26.417+08:00`, ended `2026-10-13T13:47:22.92+08:00`, duration **836.497 seconds**. Its new terminal file has all 18 cases passing, but there are two other failures. Every full file used one attempt; no retries, artifact errors, unexpected skips or cleanup failures were recorded. The 20 skips are exactly the unchanged opt-in cases: `test_r45.py` 1 hardware, `test_visual_screenshot.py` 1 visual, `test_ux_visual_chat_shots.py` 18 visual. Neither `--run-visual` nor `--run-hardware` was enabled.

Independent read-only verifier `verify_full.py` completed with exit 0 in 46.13 seconds. It verified all **169 raw log SHA256 values**, parsed their actual final raw result counts and cross-checked counts/status/exit with both summary and progress. It also checked all **411 full snapshot and current inputs**, and all **69,459 file hashes in 169 actual executing case copies**. Full/source/test/dependency IDs were recomputed, sandbox artifacts matched their summary copies, and single-attempt/cleanup evidence was consistent. This successful evidence verification confirms the failure record; it does not turn the failed gate into a pass. Detailed rows and hashes are in `full-proof.json`.

## Failures retained as blockers

1. **`tests/test_server.py::test_status_default_online_in_welcome`**: the actual server thread cannot bind port **2414**, raising **WinError 10013**; the client then receives **WinError 10061** on `127.0.0.1:2414`. Raw file result is **1 FAIL / 60 PASS**, exit 1. The test's ordinary Hub/TCP startup and default-welcome path has no Kalah action; the failure happens before its connection/HELLO reaches game logic. Its test and server/sandbox source bytes were not changed by this task.
2. **`tests/test_ux_visual_chat_regressions.py::test_short_history_is_not_clipped_after_window_grows`**: after loading four synthetic chat rows and growing the window to 1000x700, total message height fits, but `_first_visible` is **1**, expected **0**. Raw file result is **1 FAIL / 12 PASS**, exit 1. This is the normal chat `MsgList` load/resize path, not Kalah `_sow`; its test/client/widget source bytes were not changed by this task.

Static inspection establishes that neither failure point directly touches the finite Kalah diff. **Causal attribution remains undetermined:** no new clean-baseline control ran with the same failing conditions. Neither is labeled a historical/pre-existing failure or proven environment-only issue, and neither is waived. The stopping instruction permits no attempt to fix these other paths or rerun them during this task.

## GUI diagnostic and binary limits

The actual `test_flagship_gui.attempt1.log` still contains multiple Tcl **`invalid command name` / `after` script** diagnostics despite **6 PASS**, exit 0. The raw diagnostic remains evidence and is not erased by pytest's result. It does not prove a clean natural window exit or visual acceptance. No UI callback cleanup was modified in this rule task.

Existing three EXEs and ZIP are historical artifacts bound to `9803303` / old source `13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345`, 410 inputs. No new build occurred, so that package does not contain the current Kalah rule fix and cannot be described as the final tested candidate package. Main-session natural quit remains blocked; real EXE complete game flow, external Windows, physical LAN, DPI/visual, R1 and release acceptance remain outside this evidence.

## Handoff

Preserve the original RED and both full FAILs, publish this bounded evidence with the candidate source, and stop after the already authorized source commit/ordinary task-branch push and cleanup. No main push, merge, release, new task, test retry, baseline rerun, build or UI work is authorized by this review. Any future remediation or new artifact validation needs a separately authorized continuation; this review makes no such approval.
