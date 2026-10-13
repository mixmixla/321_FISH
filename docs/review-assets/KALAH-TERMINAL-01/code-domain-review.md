# KALAH-TERMINAL-01 v1 — independent code, RED and domain review

Reviewer `/root/kalah_domain_review`, 2026-10-13. Production, tests and governance remain read-only. No tests, apps, native calls or builds executed by this reviewer. Only a separate ignored read-only byte/evidence verification script and these reports were written.

## Reviewed version and verdict

Worktree `D:/Project/321_FISH/_tmp_gui/gate-collection-20261013`, branch `fix/gemcity-purchase-20261013`, base/HEAD `2fa1c9eb5fc499c1bd424b36e2093f1f5bc84b69` with the finite uncommitted task. Read the frozen `docs/task-packages/KALAH-TERMINAL-01.md` v1, actual `git diff`, current production and new tests, the complete original RED raw log, and completed domain raw evidence.

**0 MUST findings in the actual finite code/test scope.** This is independent code, RED and domain review, not full-gate or artifact acceptance. Full gate remains pending at this report version.

- Production baseline `games_pkg/kalah.py`: SHA256 `8655ba17bcc4ef36a20c1d3f46233b03df517170a6ba00126d4d33c11f89e85a`.
- Reviewed current production: SHA256 `d64c0edaf201cbfa2c3d344ffc69b414e16104b6e746e96e3f5e556a71db6d11`.
- New `tests/test_kalah_terminal.py`: SHA256 `faa08c01749117ceb37f2b1066a8b7b095d857090069f4484cccb63502efae9a`, identical in RED snapshot, RED executing case, domain snapshot/cases and current worktree.
- Actual production diff is 9 additions / 4 deletions, wholly within `_sow`; no UI/server/room/protocol or other scoring/sowing code changed.

## Code and contract analysis

1. `_check_win` now runs after the existing sow and capture calculation for every legal move, including a last seed in the mover's store. The existing empty-row sweep and store comparison remain the sole scoring logic, and no seed is added or removed by the new control flow.
2. `finished` takes priority before the five-field `last` is published. Terminal `go_again=False` suppresses the extra-turn message and accurately denotes no remaining legal entitlement. Actual mover, original global pit, final landing index and captured count stay unchanged. Existing graphical consumers read only the first three fields.
3. A finished game returns a winning or explicit draw message before switching `turn`. Capture facts can still be returned. Nonterminal extra turns retain the mover; nonterminal ordinary/capture moves retain their original next-turn behavior and message order.
4. The production diff leaves public action coercion/own-pit validation, A1..6/B9..14 wire convention, ring order, opponent-store skipping and capture geometry untouched. `act` already rejects all subsequent moves when `finished`, including ties; snapshot/ended already expose the terminal state. Existing Hub consumption of nonempty ended dicts supports a tie without lifecycle changes.
5. Task v1 explicitly confines continuation-message guarantees to `act`'s domain list. The desktop text summary's unconditional turn line remains an accurately documented package-external static limitation. No hidden UI acceptance is implied.

## New test quality and RED evidence

The 18 cases match the frozen set: six A/B store-ending win/loss/draw positions, two A/B capture draws, two nonterminal extra turns, two nonterminal normal turns, two real RoomManager public action cases, and four initial-position-to-terminal legal action sequences.

All near-terminal fixtures have 48 seeds and invoke public `act` (or real `RoomManager.handle_action`) through existing wire holes, not direct private `_sow`/`_check_win`. Expected A/B store totals were manually traced for all six store-ending positions. Both capture-draw positions yield a capture of four, sweep the other four and end 24:24. Terminal assertions cover empty rows, exact stores/winner/last, retained mover, domain messages, ended result and later rejection with full snapshot unchanged.

The four bounded sequences construct the normal initial 48-seed game and choose only nonempty own pits via public `act`; there is no board/turn injection in those cases. Each loop checks conservation and availability until ended. The RoomManager cases explicitly label their synthetic near-terminal setup and assert the actual rule result; they do not claim RoomManager independently changes room status to ENDED, transmits game_end or enables a new round.

Original RED was inspected in full: **11 FAIL / 7 PASS / exit 1**, one attempt, no cleanup failures or skips. Six store-ending and two RoomManager cases remain `playing`; two capture draws change turn and emit the next-player message; the natural choice-seed 1 sequence fails at step 49 with A pits all empty while the current game still says `playing`. This is a real reachable production defect, beyond manually prepared positions. The RED raw SHA256 `8edde1f8b30d2a64ab0b52922143cbd0e206b3d9e7ad9275b61f4f552b0e3d55` matches summary/progress and the actual bytes. Its production hash exactly matches the pre-implementation baseline.

## Completed domain evidence

The unique completed domain run is **10 files / 150 PASS / 0 FAIL / 0 SKIP / exit 0**, 19.158 seconds. Source ID `1b5fa41cf53ab7146a000a37d9116b520c1c1c92e5421b9d7f7f6df29911d561`, 411 inputs. Files include all five Kalah test files plus existing games_w2_logic, rooms and game/client/server lifecycle coverage.

Independent byte verifier exit 0: all 411 domain manifest inputs match domain snapshot, each of the ten actual executing case copies and current source bytes. The RED's 411 inputs likewise match its snapshot and actual executing case. RED-to-domain input sets differ only in `games_pkg/kalah.py`; new tests and dependencies were not changed. All eleven original RED/domain raw logs match their declared SHA256 and actual raw counts. Every file ran a single attempt with real exit status, installed loopback/hardware-blocking sandbox, no artifacts/unexpected skips and successful cleanup. Details: `domain-proof.json`, verifier `verify_domain.py`.

## Remaining acceptance limits

The Task-required unique new-source full gate must still be reviewed; previous full runs cannot substitute. The current source ID differs from old EXE source `13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345` / 410 inputs. No rebuild occurred, so old binaries do not contain this correction. These rules/domain results do not establish real GUI EXE game completion, main-session natural quit, external Windows, physical LAN, visual/DPI or release readiness.
