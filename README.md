# Exocism

`Exocism` is a small pattern-action game built with Python and pygame. The
player remains at the center while ghosts approach from eight directions.
Connect nodes on the surrounding 3x3 magic circle to exorcise the nearest
ghost.

## Run

Python 3.10 or newer is recommended.

```bash
python -m pip install -r requirements.txt
python main.py
```

## Controls

- Hold the left mouse button and drag through nodes.
- Release the mouse button to submit the pattern.
- Press `Esc` to quit.

Each ghost carries one to three patterns above its head. Every submitted
pattern is checked against the first remaining pattern of every active ghost.
All matching ghosts lose that pattern at the same time. A ghost stops moving
and fades away after its final pattern is removed, awarding score and holy
power. Incorrect patterns do not cost health; health is lost only when a ghost
reaches the player.

One-pattern ghosts appear most often, two-pattern ghosts appear regularly, and
three-pattern ghosts are rare. Normal patterns accept either drawing direction.
Only the start-locked variant requires the marked start point.

Ghost behavior variants:

- Slowpoke: ordinary patterns with no extra rule
- Start locked: requires the marked start point and exact direction
- Blinking: periodically becomes faint
- Wavy: its displayed pattern nodes ripple
- Forbidden: mixes one red trap pattern among its required patterns
- Partial: alternates between two halves of its first pattern

Drawing a red forbidden pattern does not remove one of that ghost's required
patterns and makes the trap ghost faster. Early waves strongly favor ordinary
slowpokes; special variants become more common later.
Ghosts pause briefly, then move toward the player with a cubic ease-in-out
step instead of moving continuously.

When holy power reaches 40, enter the gold `HEAL` pattern to spend 40 power and
restore two health. Casting it at full health does not consume power. Open the
`SPELLS` bookmark on the right to review the spell pattern.

Holy power can now hold up to 150. Hover over the `SPELLS` bookmark to review:

- `HEAL` (40): restore two health
- `REPEL` (35): push nearby ghosts away without defeating them
- `SANCTIFY` (45): remove gimmicks from nearby ghosts without changing patterns
- `SLOW` (45): slow only the ghosts present when the spell is cast for 9 seconds

Defeated ghosts send a holy-power gem toward the HUD instead of showing a
combat log. Newly spawned ghosts fade in, removed patterns fade out while the
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
