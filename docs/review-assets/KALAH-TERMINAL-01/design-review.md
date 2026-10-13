# KALAH-TERMINAL-01 — independent read-only design review

Reviewer: /root/kalah_domain_review. 2026-10-13. Read-only production/tests/governance; no tests, native calls, app or build executed.

Observed worktree: `D:/Project/321_FISH/_tmp_gui/gate-collection-20261013`, branch `fix/gemcity-purchase-20261013`, HEAD `2fa1c9eb5fc499c1bd424b36e2093f1f5bc84b69`. Tree was clean on entry. Baseline `games_pkg/kalah.py` SHA256 `8655ba17bcc4ef36a20c1d3f46233b03df517170a6ba00126d4d33c11f89e85a`.

## Static findings

1. The module's own rule contract says either player's empty pit row ends the game and remaining seeds are swept into their respective stores. `_sow` currently calls `_check_win` only when `not go_again`, so a final seed in the mover's own store suppresses terminal detection. This is a production rule defect, not an unverified UI claim.
2. `_check_win` correctly represents draws as `finished=True, winner=None`, but `_sow` only returns before switching players when `self.winner` is truthy. A drawn terminal move therefore changes `turn` and emits a next-player instruction despite being ended. The terminal branch must use `finished`.
3. `_check_win` already performs the desired sweep and store comparison. No replacement scoring algorithm, board-index change, or transport change is warranted.

## Legal public-act near-terminal fixtures (48 seeds)

These are synthetic legal near-terminal states, not proof of an initial-position-to-terminal real GUI flow. The final transition should use `act`, not direct `_sow`/`_check_win`, after selecting a nonempty own pit with the existing global wire index.

- A: A pits `[0,0,0,0,0,1]`, B pits remain nonempty, stores plus all pits total 48, `turn=p0`, `act(p0,{"hole":6})`. It lands in index 6, empties the A row, and must finish immediately. Store distributions can cover A win, B win and 24:24 tie.
- B: A pits `[1,1,1,1,1,1]`, B pits `[0,0,0,0,0,7]`, stores A=12/B=23, `turn=p1`, `act(p1,{"hole":14})`. Starting index 13 passes A indices 0..5, skips index 6, then lands in B store index 7. The B row is empty. Correct sweep gives A=24/B=24; old production state remains playing with an impossible extra turn.

Terminal coverage should also include ordinary non-store-ending moves, capture-driven empty rows, each winning identity and tie, post-terminal act rejection with complete state unchanged, and exact last-move field values. Nonterminal coverage should preserve existing extra-turn, normal turn-switch, skip-opponent-store and capture behavior, board/store seed conservation, and existing wire 1..6 / 9..14.

## Interface and lifecycle boundary

- The five-field `last=(pid,hole,last,go_again,captured)` public shape must remain. Existing `client_gameui._g_kalah_sow_plan` only consumes fields 0..2; `_p_kalah` uses fields 0..1 for the recent-pit marker. `client.py` and the Web Kalah renderer do not read the extra-turn field. Setting terminal `last[3]=False` records no remaining playable extra turn without breaking observed consumers.
- Both graphical desktop painter and Web renderer prioritize `status="ended"` for hints and disable holes. The desktop textual summary still unconditionally writes `轮到 … 播子` (`client.py` Kalah branch). The current games-only scope should explicitly restrict the no-continuation-message requirement to `act`'s domain message list; silently promising a summary/UI rewrite would expand ownership.
- `server._on_game_action` calls the public `ended()` result after broadcasting the move, and accepts the nonempty draw dict even with `winner_uid=None`. The ticker follows the same path. `BaseGame.ended()` documents non-None as ended; no Hub/RoomManager lifecycle change is needed.

## Review status

The proposed minimal scope matches the actual two rule defects. This is design review only. No implementation diff, RED evidence, domain/full gate or new-artifact proof was available at this review point; no implementation acceptance is claimed.

Binary boundary: existing EXE artifacts remain bound to old source `13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345` (410 inputs). A production rule change requires a new source identity; absent new builds, neither these tests nor source acceptance establish the new behavior inside the old EXEs.
