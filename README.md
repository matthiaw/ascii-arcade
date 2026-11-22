# ASCII ARCADE

A little collection of games for the terminal. Start the launcher, pick a game with the arrow keys (or its
number: 1-9, 0 for the tenth, 0 again for the eleventh), press Enter. When the game ends you are back in the menu.

```sh
python3 arcade.py
```

Every game can also be started on its own (`python3 stackfall.py` and so on).

## Install with Homebrew

```sh
brew tap matthiaw/arcade https://github.com/matthiaw/ascii-arcade
brew trust --formula matthiaw/arcade/ascii-arcade
brew install ascii-arcade
```

(`brew trust` is needed from Homebrew 7 on, which only loads formulae from other taps once you trust them.)
Afterwards:

```sh
arcade              # the menu
arcade stackfall    # one game straight away
arcade --list       # all games
arcade --version
brew upgrade ascii-arcade
```

Homebrew brings its own Python (3.14); the games need nothing else.

## The same keys in every game

| Key | |
|---|---|
| Esc | in a game: pause / game menu - on a title screen: quit (back to the arcade) - in sub-screens: back |
| P | pause (real-time games; in EMBERFALL P drinks a potion, Esc opens its game menu: M sound, Q save and quit) |
| M | in the pause menu and in the launcher: sound on / off (remembered for every game) |
| G | in the launcher: pixels fine / solid (solid avoids streaks in macOS Terminal) |
| Q | in the pause menu: quit - on a title screen: quit (in DEPTHWELL Q also turns pieces) |
| ? | help with all of the game's keys, also on the title screens |
| Enter / Space | confirm |
| Arrows / WASD | move, choose |

The pause menu always reads: Esc / P / Enter continue, ? help, M sound on / off, Q quit. No game ends on a single stray key.

## Pixels: fine or solid

The pictures are drawn with the half-block character `▀`: every character cell shows two pixels, the top one
in the text colour and the bottom one in the background colour. WezTerm, iTerm2, kitty and Ghostty draw that
character themselves and it fills the cell exactly. macOS Terminal.app takes it from the font instead, and
there it leaves a thin gap, so pictures look streaky.

For such terminals there is **solid** pixel mode: one pixel per cell, drawn with the background colour only, so
no gaps at all (coarser, half the vertical detail). Press **G** in the launcher to switch between fine and
solid; the choice is kept for every game in `~/.ascii_arcade_settings.json`. Also `arcade --pixels solid` /
`arcade --pixels fine`, or `ARCADE_PIXELS=solid arcade` for a single run. In Terminal.app the launcher suggests
it until you have chosen once.

## Sound

Every game has its own little chiptune sound effects, synthesized in Python the first time they are needed
(cached in `~/Library/Caches/ascii-arcade`, on Linux `~/.cache/ascii-arcade`) and played with `afplay` on macOS
or `pw-play` / `paplay` / `aplay` on Linux. Press M in the launcher or in any pause menu to switch sound off or on;
the choice is kept in `~/.ascii_arcade_settings.json`. `ARCADE_SOUND=0 arcade` starts without sound.
`python3 arcadesound.py` plays a short demo.

No dependencies: Python 3 on macOS or Linux (on Windows use WSL). Best in a truecolor terminal (WezTerm, iTerm2,
kitty, Ghostty); 256 colours work too. Bigger windows give bigger pictures.

## The games

| Game | | Window |
|---|---|---|
| **HOVERDRIFT** | Glide over endless voxel landscapes. Four vehicles (hovercraft, jet, hover tank, saucer), six worlds (meadows, ice, desert, volcano planet, Planet Xeno, crystal moon), six weapons. | 40x12+ |
| **EMBERFALL** | A party role-playing adventure: create a hero, recruit companions, fight turn by turn with d20 rules, descend beneath the Ashpeaks. | 70x22+ |
| **BLOCKFIRE** | A first-person arena shooter: raycast 3D with textured walls, lit floors and pixel-art robots that come in waves. | 60x18+ |
| **DEEPCALL** | A submarine alone in the dark: only the sonar shows the trench, and every ping can be heard. Find air vents and salvage, keep the noise down, reach the Source at the bottom. | 60x20+ |
| **LIGHTKEEPER** | Keep the lighthouse through stormy nights: light ships past the reefs, sound the horn in the fog, refill the oil and send the rescue boat. Alone, or two keepers at one keyboard. | 70x22+ |
| **SKYSHOT** | An artillery duel on ground that breaks apart: set angle and power, read the wind, carve craters under the other tank. Four shells, best of three rounds. Two players at one keyboard or one against the computer (easy / normal / hard). | 70x22+ |
| **NIGHTDRIVE** | Race through the night against the clock: winding hilly roads, headlights and street lamps, traffic and oncoming cars, six stages from neon city to a rainstorm. | 70x22+ |
| **ORBITAL** | A calm gravity puzzle: launch a probe past planets, moons, asteroid belts and wormholes to the dock ring. Fewer launches, more stars. | 70x22+ |
| **LEAFLING** | A jump'n'run with a leaf for a hat: run, jump, glide and wall-jump through twelve levels in four worlds (sunlit forest canopy, crystal caves, wind-swept sky ruins, an autumn storm at night), with light motes, hidden seeds, lanterns, beetles, bats, spitting plants, two chases and two bosses. | 70x22+ |
| **STACKFALL** | Falling blocks in a well ten wide and twenty deep. Modes: Marathon, Sprint (40 rows), Rising (rubble pushes up from below). | 40x20+ |
| **DEPTHWELL** | Falling blocks in three dimensions: look down into a well, turn cube pieces about all three axes, fill whole layers. Four well sizes, three piece sets. | 70x22+ |

## DEEPCALL keys

| Key | |
|---|---|
| Arrows / WASD | steer the sub (it drifts: plan ahead) |
| Space | sonar ping all around: lights up the trench, loud |
| `F` | focused ping ahead: reaches further, quieter |
| `L` | lamp on / off: a short cone of light, drains power, can be seen |
| `E` | drop a flare: lights its surroundings and lures hunters to itself |
| Esc / `P` | pause menu (`Q` there: back to the menu) |
| `?` | help |

Rising bubbles mark air vents. Gold glints are salvage; blue, green and orange ones are oxygen, batteries and
flares. Jellyfish glow and sting; lurkers carry a blinking lure and swim towards every sound; in the deep zones a
leviathan listens, and the NOISE bar shows how loud you have been.

## LIGHTKEEPER keys

| Key | One keeper | Two keepers |
|---|---|---|
| Left / Right | turn the beam | keeper: turn the beam |
| Up / Down | focus: narrow reaches far, wide lights near | keeper: focus |
| Space | horn: ships nearby slow down and see their way | keeper: horn |
| `R` | refill the oil (the light is off for a moment) | keeper: refill |
| `B` | send the rescue boat to the nearest wreck | - |
| `W` `A` `S` `D` | same as the arrows | second player: steer the rescue boat |
| Esc / `P` | pause menu (`Q` there: back to the menu) | |
| `?` | help | |

Ships in the beam steer clear of the reefs; ships in the dark sail on blindly. A wreck fires red flares: get the
crew home before its time runs out, or a lifebuoy is lost. The rescue boat is slow in the dark, so keep it in the
light. Each night brings more ships and worse weather (wind, fog, rain and lightning, storm); at dawn the
lighthouse gets one improvement of your choice.

## SKYSHOT keys

| Key | |
|---|---|
| Left / Right (`A` / `D`) | turn the barrel (angle) |
| Up / Down (`W` / `S`) | power (PgUp / PgDn: +-10) |
| Tab or `1`-`4` | choose the shell: shell, heavy shell (3 per round), splitter (2), dirt ball (2) |
| Space / Enter | fire |
| Esc / `P` | pause menu (`Q` there: back to the menu) |
| `?` | help |

Players take turns at the same keys; the coloured banner at the top says whose turn it is, and the dotted line
at the barrel shows the aim (longer means more power). The wind changes every turn and pushes the shells. Craters
swallow tanks and falling hurts. The splitter bursts in three at the top of its arc, and the dirt ball buries the
other tank in fresh earth.

## NIGHTDRIVE keys

| Key | |
|---|---|
| Left / Right (`A` / `D`) | steer: a tap is a small correction, holding the key turns |
| Up (`W`) | accelerate (with manual throttle each press adds gas, which slowly fades) |
| Down (`S`) / Space | brake |
| Esc / `P` | pause menu (`Q` there: back to the menu) |
| `?` | help |

Six stages through the night (neon city, coastline, pine forest, desert highway, mountain pass, storm run), each
with a time limit: every checkpoint adds time, and time left over carries on. Overtake the traffic; on the forest,
desert and mountain stages cars come towards you in the left-hand lanes. Curves push you outwards, the verge slows
you down, and lamps, trees and rocks spin you round. On the title screen choose the start stage (stages unlock as
you reach them) and the throttle: auto (the default, you only steer and brake) or manual.

## ORBITAL keys

| Key | |
|---|---|
| Left / Right (`A` / `D`) | aim: a tap turns 0.5 degrees, holding turns faster |
| Up / Down (`W` / `S`) | launch power: a tap is 0.5 %, holding is faster |
| Space / Enter | launch |
| Space (in flight) | nudge: one short push forward, on levels with fuel |
| Enter (in flight) | fast forward on / off |
| `R` | abort the flight / play the level again |
| `N` or `]` / `B` or `[` | next / previous unlocked level |
| Esc / `P` | pause menu (`Q` there: back to the menu) |
| `?` | help |

Every planet pulls on the probe according to its mass; the dotted line shows only the first part of the flight,
and your last three paths stay on screen as faint lines. Reach the gold dock ring (passing numbered beacons in
order first): one launch earns three stars, two or three launches two stars. Eight lessons come first, then
generated levels add moving moons, asteroid belts, wormholes, a fuel nudge and waypoints.

## LEAFLING keys

| Key | |
|---|---|
| Left / Right (`A` / `D`) | run |
| Space / Up / `W` / `Z` | jump - press again in the air to glide on your leaf |
| Down (`S`) | drop through thin platforms; also stops you |
| `R` | back to the last lantern |
| Esc / `P` | pause menu (`Q` there: back to the world map, `M`: sound on / off) |
| `?` | help |

Slide down mossy walls and jump off them to climb; springy mushrooms throw you high; crumbling blocks fall
away under your feet. Stomp beetles, bats and plants from above and dodge the seeds the plants spit. Touch a
lantern to make it your restart point. Every level hides three seeds (behind fake walls, high up, off the
beaten path); every 50 light motes give an extra leaf. The last level of each world ends with a set piece:
a bramble wall or a storm front chasing you, or a beetle boss you stomp while it is dizzy. Levels unlock as you
finish them; the world map shows your best time and seeds per level.

Terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) report key releases: there
the jump height follows how long you hold the key and holding jump in the air glides. In other terminals (macOS
Terminal) a direction key keeps you running while it repeats (it bridges the initial repeat delay), the other
direction turns at once, Down stops; jumps are always full and jump in the air switches the glide on and off.
`python3 leafling.py --selftest` plans a route through every level with the game's own physics.

## STACKFALL keys

| Key | |
|---|---|
| Left / Right (`A` / `D`) | move |
| Up, `X` (`W`) | turn clockwise |
| `Z` (or `Y`) | turn back |
| Down (`S`) | drop faster |
| Space | slam down |
| `C` / Tab | hold the piece for later |
| Esc / `P` | pause menu (`Q` there: back to the menu) |
| `?` | help |

Rows: 100 / 300 / 500 / 800 points times the level for 1-4 rows at once, a bonus for combos and for an empty
well. The level rises every 10 rows.

## DEPTHWELL keys

| Key | |
|---|---|
| Arrows (`I` `J` `K` `L`) | move the piece across the well |
| `Q` / `A` | turn about the x axis (forward / back) |
| `W` / `S` | turn about the y axis |
| `E` / `D` | turn about the z axis (flat spin) |
| Space | drop to the bottom |
| Enter (`Z`) | sink one layer |
| `G` | ghost (where the piece will land) on / off |
| Esc / `P` | pause menu (`Q` there: back to the menu) |
| `?` | help |

The falling piece is the bright block; the outlined spot below it shows where it will land. The map
FROM ABOVE on the right colours every column by its height and outlines the landing cells, and the gauge on
the left shows how high the stack has grown and where your piece is. Fill every cell of a layer to clear it;
the level rises every 4 layers.

High scores of STACKFALL and DEPTHWELL are kept in `~/.ascii_arcade_scores.json`.

## Versions and releases

Versioning is automatic: every push to `main` that changes the games becomes a release
(`.github/workflows/release.yml`). The workflow checks that every file compiles, raises the version, writes it to
`VERSION` and to the Homebrew formula, tags the commit `vX.Y.Z` and publishes a GitHub release with notes.

| In a commit message | Step |
|---|---|
| (nothing special) | patch: 1.0.0 -> 1.0.1 |
| `[minor]` or a message starting with `feat` | minor: 1.0.1 -> 1.1.0 |
| `[major]` or `BREAKING` | major: 1.1.0 -> 2.0.0 |
| `[skip release]` | no release |

Changes only to Markdown files, the formula, the workflow or `scripts/` do not make a release. A release can also
be started by hand under Actions -> release -> Run workflow, with a choice of step. Writing a new version into
`VERSION` by hand releases exactly that version.

## Licence

Copyright (c) 2026 Matthias Wegner. Released under the MIT License - see [LICENSE](LICENSE). You may use, copy,
change and share the games freely, as long as the copyright notice stays in.

## Files

| File | |
|---|---|
| `arcade.py` | the launcher |
| `arcadekit.py` | shared toolkit: raw terminal input, half-block pixel canvas, block font, high scores |
| `arcadesound.py` | the sound engine: synthesized effects, played without waiting |
| `stackfall.py`, `depthwell.py`, `deepcall.py`, `lightkeeper.py`, `skyshot.py`, `nightdrive.py`, `orbital.py`, `leafling.py` | the games written for the arcade (use `arcadekit.py`) |
| `hoverdrift.py`, `emberfall.py`, `blockfire.py` | HOVERDRIFT, EMBERFALL and BLOCKFIRE (they run on their own and do not need `arcadekit.py`) |
| `extras/emberfall-art/` | the source images and tools behind EMBERFALL's pictures (not in the Homebrew package) |
| `VERSION` | the current version (written by the release workflow) |
| `Formula/ascii-arcade.rb` | the Homebrew formula (this repository is its own tap) |
| `.github/workflows/release.yml`, `scripts/next_version.py` | automatic versioning and releases |
| `LICENSE` | MIT License |
