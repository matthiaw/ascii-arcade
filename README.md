# ASCII ARCADE

A little collection of games for the terminal. Start the launcher, pick a game with the arrow keys, press
Enter. When the game ends you are back in the menu.

```sh
python3 arcade.py
```

Every game can also be started on its own (`python3 stackfall.py` and so on).

No dependencies: Python 3 on macOS or Linux (on Windows use WSL). Best in a truecolor terminal (WezTerm, iTerm2,
kitty, Ghostty); 256 colours work too. Bigger windows give bigger pictures.

## The games

| Game | | Window |
|---|---|---|
| **HOVERDRIFT** | Glide over endless voxel landscapes. Four vehicles (hovercraft, jet, hover tank, saucer), six worlds (meadows, ice, desert, volcano planet, Planet Xeno, crystal moon), six weapons. | 40x12+ |
| **EMBERFALL** | A party role-playing adventure: create a hero, recruit companions, fight turn by turn with d20 rules, descend beneath the Ashpeaks. | 100x30+ |
| **BLOCKFIRE** | A first-person arena shooter: raycast 3D with textured walls, lit floors and pixel-art robots that come in waves. | 60x18+ |
| **STACKFALL** | Falling blocks in a well ten wide and twenty deep. Modes: Marathon, Sprint (40 rows), Rising (rubble pushes up from below). | 40x20+ |
| **DEPTHWELL** | Falling blocks in three dimensions: look down into a well, turn cube pieces about all three axes, fill whole layers. Four well sizes, three piece sets. | 70x24+ |

## STACKFALL keys

| Key | |
|---|---|
| Left / Right (`A` / `D`) | move |
| Up, `X` (`W`) | turn clockwise |
| `Z` (or `Y`) | turn back |
| Down (`S`) | drop faster |
| Space | slam down |
| `C` / Tab | hold the piece for later |
| `P` | pause |
| `Q` / Esc | back to the menu |

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
| `P` | pause |
| Esc | back to the menu |

The falling piece is drawn as a white wire frame. The colour of a settled cube tells its depth, and the gauge
on the left shows how high the stack has grown. Fill every cell of a layer to clear it; the level rises every
4 layers.

High scores of STACKFALL and DEPTHWELL are kept in `~/.ascii_arcade_scores.json`.

## Files

| File | |
|---|---|
| `arcade.py` | the launcher |
| `arcadekit.py` | shared toolkit: raw terminal input, half-block pixel canvas, block font, high scores |
| `stackfall.py`, `depthwell.py` | the falling-block games (use `arcadekit.py`) |
| `hoverdrift.py`, `emberfall.py`, `blockfire.py` | standalone copies of the HOVERDRIFT, EMBERFALL and BLOCKFIRE repositories |
