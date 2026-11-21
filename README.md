# ASCII ARCADE

A little collection of games for the terminal. Start the launcher, pick a game with the arrow keys, press
Enter. When the game ends you are back in the menu.

```sh
python3 arcade.py
```

Every game can also be started on its own (`python3 stackfall.py` and so on).

## The same keys in every game

| Key | |
|---|---|
| Esc | in a game: pause / game menu - on a title screen: quit (back to the arcade) - in sub-screens: back |
| P | pause (real-time games; in EMBERFALL P drinks a potion) |
| Q | in the pause menu: quit - on a title screen: quit (in DEPTHWELL Q also turns pieces) |
| ? | help with all of the game's keys, also on the title screens |
| Enter / Space | confirm |
| Arrows / WASD | move, choose |

The pause menu always reads: Esc / P / Enter continue, ? help, Q quit. No game ends on a single stray key.

No dependencies: Python 3 on macOS or Linux (on Windows use WSL). Best in a truecolor terminal (WezTerm, iTerm2,
kitty, Ghostty); 256 colours work too. Bigger windows give bigger pictures.

## The games

| Game | | Window |
|---|---|---|
| **HOVERDRIFT** | Glide over endless voxel landscapes. Four vehicles (hovercraft, jet, hover tank, saucer), six worlds (meadows, ice, desert, volcano planet, Planet Xeno, crystal moon), six weapons. | 40x12+ |
| **EMBERFALL** | A party role-playing adventure: create a hero, recruit companions, fight turn by turn with d20 rules, descend beneath the Ashpeaks. | 100x30+ |
| **BLOCKFIRE** | A first-person arena shooter: raycast 3D with textured walls, lit floors and pixel-art robots that come in waves. | 60x18+ |
| **DEEPCALL** | A submarine alone in the dark: only the sonar shows the trench, and every ping can be heard. Find air vents and salvage, keep the noise down, reach the Source at the bottom. | 60x20+ |
| **STACKFALL** | Falling blocks in a well ten wide and twenty deep. Modes: Marathon, Sprint (40 rows), Rising (rubble pushes up from below). | 40x20+ |
| **DEPTHWELL** | Falling blocks in three dimensions: look down into a well, turn cube pieces about all three axes, fill whole layers. Four well sizes, three piece sets. | 70x24+ |

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

The falling piece is drawn as a white wire frame. The colour of a settled cube tells its depth, and the gauge
on the left shows how high the stack has grown. Fill every cell of a layer to clear it; the level rises every
4 layers.

High scores of STACKFALL and DEPTHWELL are kept in `~/.ascii_arcade_scores.json`.

## Files

| File | |
|---|---|
| `arcade.py` | the launcher |
| `arcadekit.py` | shared toolkit: raw terminal input, half-block pixel canvas, block font, high scores |
| `stackfall.py`, `depthwell.py`, `deepcall.py` | the games written for the arcade (use `arcadekit.py`) |
| `hoverdrift.py`, `emberfall.py`, `blockfire.py` | standalone copies of the HOVERDRIFT, EMBERFALL and BLOCKFIRE repositories |
