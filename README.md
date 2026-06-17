# Exocism

`Exocism` is a small pattern-action game built with Python and pygame. The
player remains at the center while ghosts approach from eight directions.
Connect nodes on the surrounding 3x3 magic circle to exorcise the nearest
ghost.

## Run

Python 3.10 or newer is recommended.
The opening MP4 tutorial also requires `ffmpeg` to be available on `PATH`.

```bash
python -m pip install -r requirements.txt
python main.py
```

On the first launch, `exorcism_sceen1.mp4` plays once and holds its final
frame. Its embedded audio plays with the video. The target pattern and input
grid fade in and spread from the center after the video finishes.

After the pattern succeeds, `exorcism_sceen2.mp4` plays with its embedded
audio. The final frame remains on screen while three dialogue lines fade in.
Click or press `Enter`/`Space` to advance. After the last line, the scene fades
to black and then fades into the game.
The in-game scene uses `stage1.png` as its background.
Background music is selected by game state. Add these optional files next to
`main.py`: `title_bgm.mp3`, `stage1_bgm.mp3`, `stage2_bgm.mp3`,
`stage3_bgm.mp3`, `boss1_bgm.mp3`, `boss2_bgm.mp3`, `final_boss_bgm.mp3`, and
`gameover_bgm.mp3`. `title_bgm.mp3` is used on the title/settings screens, and
`gameover_bgm.mp3` is used on the game-over screen. The three stage tracks are
used during regular Stage 1, Stage 2, and Stage 3 play. `boss1_bgm.mp3` is for
Piton, `boss2_bgm.mp3` is for Weaver, and `final_boss_bgm.mp3` is for Stage 3+
boss battles. Story/dialogue/video scenes do not play separate BGM; they rely
on the video's embedded audio.
Dialogue characters appear one by one with a short upward motion. The panel
stays in place while lines switch with a quick text fade.
Peter's speech sound overlaps once for every two revealed dialogue characters.
Each newly
spawned ghost randomly plays one of `boo1.mp3` through `boo3.mp3`; defeating
that ghost stops its boo immediately and plays `ghost_defeated.mp3`.
Peter briefly switches to `peter_attack1.png` whenever a ghost pattern hits or
any holy-power spell is successfully cast.

## Controls

- The game opens on `main.png` with `START` and `SETTINGS` menu options.
- `SETTINGS` provides mouse-draggable background-music and sound-effect volume
  sliders, plus a `BACK` button.
- Hold the left mouse button and drag through nodes.
- Release the mouse button to submit the pattern.
- Hold `Shift` while drawing to store a first layer, then draw a second layer
  without `Shift` to submit a two-layer pattern.
- Press `P` or `Esc` during play to pause.
- Secret shortcut: `Ctrl+Shift+G` skips the opening story to gameplay. During
  regular gameplay it jumps to the Piton intro video; pressing it again during
  that video or its fade transitions starts the Piton battle immediately.

Each ghost carries one to three patterns above its head. Every submitted
pattern is checked against the first remaining pattern of every active ghost.
All matching ghosts lose that pattern at the same time. A ghost stops moving
and fades away after its final pattern is removed, awarding score and holy
power. Incorrect patterns do not cost health; health is lost only when a ghost
reaches the player.

One-pattern ghosts appear most often, two-pattern ghosts appear regularly, and
three-pattern ghosts are rare. Normal patterns accept either drawing direction.
Only the start-locked variant requires the marked start point.

Stage 1 is limited to three curated waves:

- Wave 1 introduces ordinary and start-locked ghosts with short patterns.
- Wave 2 increases the number of ordinary and start-locked ghosts.
- Wave 3 mixes start-locked and forbidden-pattern ghosts while shifting toward
  longer patterns. Forbidden traps deliberately reuse another ghost's required
  pattern. Hiding creeps do not appear until Stage 2.

Stage 2 is prepared as three data-driven waves and can be started with
`GameSession.start_stage(2)` after its future transition video. Wave 1 focuses
on blinking, wavy, and partial-pattern ghosts. Wave 2 introduces crease and
layered snarl ghosts. Wave 3 mixes those newer gimmicks with forbidden, hiding,
start-locked, and ordinary ghosts. It begins with two medium-length patterns
per ghost and gradually adds three-pattern and complex-pattern combinations.
Each Stage 2 ghost can carry one Piton-style sealed pattern slot. `SANCTIFY`
removes that seal, and no regular ghost can hold more than one sealed slot.
For temporary testing, pressing `Ctrl+Shift+G` during the Piton battle defeats
the boss and support ghosts, then runs the `scene2.png` epilogue before Stage 2.

After wave 3, the screen fades to black and `exorcism3.mp4` plays before the
Piton boss battle. Piton has three rows of seven patterns. Sealed pattern slots
cannot be attacked; each `SANCTIFY` cast removes one seal. Adjacent sealed slots
share one rectangular seal frame. Piton adds a random seal every 10 seconds and
adds another when advancing to rows two and three. If `SANCTIFY` itself is
sealed, it returns automatically after five seconds.

Piton approaches 1.7 times more slowly than the slowest regular ghost. Contact
deals two health, then Piton fades out and reappears from a clear outer
direction. Support ghosts spawn more frequently as each boss row is cleared.
When Piton is defeated, every remaining support ghost immediately loses its
attack and plays its defeat animation in place. After all defeat animations,
the game fades to `scene2.png`, presents Peter's three-line epilogue dialogue,
plays `exorcism4.mp4` with its original audio, displays temporary Peter
dialogue over the final frame, then fades into Stage 2.

When Peter's health reaches zero, gameplay fades to black and then reveals
`peter_defeat_scene.png` before the game-over controls appear.

Ghost behavior variants:

- Slowpoke: ordinary patterns with no extra rule
- Start locked: requires the marked start point and exact direction
- Blinking: periodically becomes faint
- Wavy: its displayed pattern nodes ripple
- Forbidden: mixes one red trap pattern among its required patterns
- Partial: alternates between two halves of its first pattern
- Creep: hides for several seconds when hit, then reappears faster in a clear position
- Crease: shows mirrored patterns with a dotted symmetry-axis marker
- Snarl: carries longer complex patterns, sometimes including two-layer ones

Drawing a red forbidden pattern removes that red trap marker and makes the trap ghost faster.
Early waves strongly favor ordinary
slowpokes; special variants become more common later.
Ghosts pause briefly, then move toward the player with a cubic ease-in-out
step instead of moving continuously.

When holy power reaches 40, enter the gold `HEAL` pattern to spend 40 power and
restore two health. Casting it at full health does not consume power. Open the
`SPELLS` bookmark on the right to review the spell pattern.

Holy power can now hold up to 150. Hover over the `SPELLS` bookmark to review:

- `HEAL` (40): restore two health
- `REPEL` (35): push nearby ghosts away and slow them for 1 second
- `SANCTIFY` (45): remove gimmicks from active ghosts without changing patterns
- `TRUTH` (45): reveal hidden creeps and clear forbidden trap gimmicks

Defeated ghosts send a holy-power gem toward the HUD instead of showing a
combat log. Newly spawned ghosts fade in while moving, removed patterns fade out while the
remaining patterns ease into their new centered positions, and partial-pattern
ghosts crossfade between pattern halves.

## Project Structure

- `main.py`: pygame loop, input, drawing, and screen states
- `core.py`: patterns, ghosts, wave queue, scoring, and spells
- `test_core.py`: standard-library unit tests for the game rules
- `exorcism_MC.png`: player artwork
- `exorcism_Monster1.png`: ghost artwork

## Add Content

Add base ghost definitions to `GHOST_SPECS` in `core.py`. Patterns are tuples
of node indices from 0 through 8. Runtime behavior variants are represented by
`GhostKind`.

Run the logic tests without opening a game window:

```bash
python -m unittest -v
```
