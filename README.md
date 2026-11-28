# ASCII ARCADE

![The ASCII ARCADE start screen: all thirty-two games playing at once](docs/screenshots/start.gif)

A little collection of games for the terminal. Start the launcher: the start screen shows all games playing at once
(Enter starts the highlighted one, any other key opens the menu). Pick a game with the arrow keys (or its number:
1-32, two digits typed quickly one after the other), press Enter. When the game ends you are back in the menu.

```sh
python3 arcade.py
```

Every game can also be started on its own (`python3 stackfall.py` and so on).

## Which terminal?

**WezTerm is a good choice**, especially on a Mac: it draws the pixel graphics exactly (sharp, no seams), shows
24-bit colour, and supports the kitty keyboard protocol, so held keys work precisely (variable jump height in
LEAFLING, smooth steering in BLOCKFIRE). It is free and installs with `brew install --cask wezterm`; then run
`arcade` inside it. iTerm2, kitty and Ghostty work just as well.

The built-in macOS Terminal.app works, but it draws the half-block pixels from the font and leaves thin seams,
so pictures look streaky. If you stay with it, press G in the launcher for the smart or solid pixel style (see
[Pixels](#pixels-fine-smart-or-solid)); a smaller font (Cmd -) then gives finer pixels.

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
| G | in the launcher: pixels fine / smart / solid (smart and solid avoid streaks in macOS Terminal) |
| R | in the launcher: finer pixels - a smaller font while the arcade runs (normal / fine / finer, see [Finer pixels](#finer-pixels-from-the-launcher)); remembered, undone when you quit |
| X / V | in the launcher: take the highlighted game off the list and the start screen / show all games (X there puts a hidden one back); remembered |
| V | in a game and in its pause menu: the view - pixels, ASCII art or mono ASCII (see [Views](#views-pixels-ascii-art-or-mono)); remembered. FENMARK's window panes use V for the brush lock, there it is in the pause menu; EMBERFALL keeps its own map views on v |
| A | in the launcher: the same view switch |
| Q | in the pause menu: quit - on a title screen: quit (in DEPTHWELL Q also turns pieces) |
| ? | help with all of the game's keys, also on the title screens |
| Enter / Space | confirm |
| Arrows / WASD | move, choose |

Every game has an **Auto mode** entry on its title screen: the real game plays itself (EMBERFALL: `--auto`,
or `A` in a run; SKYSHOT: CPU against CPU). Space pauses, `+` / `-` change the speed (x0.25 to x8), Esc stops.
Auto runs never enter the high-score list.

The pause menu always reads: Esc / P / Enter continue, ? help, M sound on / off, V view, Q quit. No game ends on a single stray key.

## LAN games

Every game for more than one person can also be played at several computers in the same network (LAN or WLAN):
SKYSHOT, LIGHTKEEPER (co-op), WEFTWAR (2 to 4), PEBBLEPUTT (2 to 4), PUCKSLIDE and FUSEYARD (1 to 4, see
[its section](#fuseyard-keys), it has Host and Join right on its title). On the title screen pick `LAN game`, type
your name once (it is kept for every game), then:

* `Host a LAN game`: this computer runs the game. The lobby shows its address and who has joined; Enter starts as
  soon as there are enough players.
* `Join a LAN game`: games in the same network show up by themselves; or type the host's address (`192.168.1.20`,
  or `192.168.1.20:47290`).

The host's computer runs the whole game. Everyone who joined plays with the same keys as at one keyboard (either
set, where a game has two) and sees the host's picture, drawn for the size of their own window, with the sounds
too. `V` (view) and `M` (sound) work on each computer for itself. Esc on the host pauses the game for everyone;
Esc at a joined computer opens a small menu of its own (`Q` there leaves) while the game goes on. Someone who
leaves mid-game is taken over by the computer (in LIGHTKEEPER the keeper gets the boat back, `B`). After a match
Enter takes everyone back to the lobby. These LAN games record no scores.

The games use TCP port 47290 (the next free one up to 47299) and UDP port 47291 for finding games; if the macOS
firewall asks whether Python may accept incoming connections, allow it on the host.

## Pixels: fine, smart or solid

A bigger window gives finer pictures, not bigger blocks: every game keeps the same view of its world and
draws it with more detail when there are more pixels (smoothed and re-lit sprite art, finer textures, smooth
terrain). Small windows look as before, and a big window gives no advantage in play. A large window with a
small font (for example 250x70) looks best.

The pictures are drawn with the half-block character `▀`: every character cell shows two pixels, the top one
in the text colour and the bottom one in the background colour. WezTerm, iTerm2, kitty and Ghostty draw that
character themselves and it fills the cell exactly. macOS Terminal.app takes it from the font instead, and
there it leaves a thin gap, so pictures look streaky (changing the font does not help). The simplest fix is
to play in WezTerm.

Press **G** in the launcher to cycle through three pixel styles; the choice is kept for every game in
`~/.ascii_arcade_settings.json`:

| Style | | Best for |
|---|---|---|
| **fine** | two pixels per cell everywhere (the default) | WezTerm, iTerm2, kitty, Ghostty |
| **smart** | half-blocks only where the two pixels clearly differ (edges, sprites, text-like detail); gradients and flat areas become one colour per cell, which costs almost no detail but removes most seams (about 80-95 % fewer half-blocks) | macOS Terminal.app |
| **solid** | one pixel per cell, background colour only: no seams at all, but coarse | Terminal.app, if smart still shows too many lines |

Also `arcade --pixels fine|smart|solid`, or `ARCADE_PIXELS=smart arcade` for a single run. In Terminal.app the
launcher suggests it until you have chosen once.

## Finer pixels from the launcher

Press **R** in the launcher to make the terminal's font smaller while the arcade runs: **fine** (75 % of your
font size), **finer** (55 %), back to **normal**. The window keeps its size on screen and gets more character
cells, so every game draws with more detail. When you quit the arcade the font and window are put back. The
level is remembered and used again at the next start (also: `arcade --zoom normal|fine|finer`).

| Terminal | What it needs |
|---|---|
| **WezTerm** | a few lines in `~/.wezterm.lua` (above `return config`): `arcade --zoom setup` prints them. They set a font override for this one window only. |
| **macOS Terminal.app** | nothing; the first time macOS asks whether the terminal may control Terminal.app (AppleScript). It changes the font of the tab's profile and keeps the old size in `~/.ascii_arcade_settings.json`, so even after a crash the next start puts it back. |
| **kitty** | `allow_remote_control yes` in `kitty.conf` |
| **iTerm2** | a profile named `ASCII Arcade` with a small font; the arcade switches to it and back to your profile |
| others (Ghostty, ...) | not possible from inside; press Cmd - (or Ctrl -) yourself |

## Views: pixels, ASCII art or mono

Every game can also be drawn as real ASCII art. Press **V** in a game (or in its pause menu) to cycle through
three views; the choice is kept for every game in `~/.ascii_arcade_settings.json`:

| View | |
|---|---|
| **pixels** | the half-block pictures described above (the default) |
| **ascii** | every pixel pair becomes one character on black: its brightness picks it from ` .:-=+*#%@`, and where the upper or the lower pixel is clearly the brighter one an edge character keeps the shape (`'` `"` `^` above, `.` `,` `m` below); the character takes the colour of what it shows |
| **mono** | the same characters in one light grey on black: plain ASCII art, as it would look pasted into a text file |

| | |
|:-:|:-:|
| <img src="docs/screenshots/ascii-view.png" alt="DEEPCALL in the ASCII view" width="400"> | <img src="docs/screenshots/mono-view.png" alt="VOIDLANCE in the mono view" width="400"> |
| **DEEPCALL, ascii** | **VOIDLANCE, mono** |

Text (scores, menus, messages) stays readable in both: it keeps its colours in the ascii view and becomes light
on dark (highlighted lines reversed) in mono. A bigger window gives finer ASCII art, just as it gives finer pixels,
and the views also show on the launcher's start screen and in auto mode (V there too). FENMARK's window panes use
V for the brush lock, so there you switch the view in the pause menu (Esc); in HOVERDRIFT the next vehicle moved
from V to B. EMBERFALL keeps its own map views on v (narrow, square and pixel tiles) and is not affected. In the launcher press **A**; also `arcade --view pixels|ascii|mono`, or
`ARCADE_VIEW=ascii arcade` for a single run. The pixel style (G) only matters in the pixels view.

## Sound

Every game has its own little chiptune sound effects, synthesized in Python the first time they are needed
(cached in `~/Library/Caches/ascii-arcade`, on Linux `~/.cache/ascii-arcade`) and played with `afplay` on macOS
or `pw-play` / `paplay` / `aplay` on Linux. Press M in the launcher or in any pause menu to switch sound off or on;
the choice is kept in `~/.ascii_arcade_settings.json`. `ARCADE_SOUND=0 arcade` starts without sound.
`python3 arcadesound.py` plays a short demo.

No dependencies: Python 3 on macOS or Linux (on Windows use WSL). Best in WezTerm (or iTerm2, kitty, Ghostty);
256 colours work too. Bigger windows give bigger pictures.

## The games

| Game | | Window |
|---|---|---|
| **HOVERDRIFT** | Glide over endless voxel landscapes. Four vehicles (hovercraft, jet, hover tank, saucer), six worlds (meadows, ice, desert, volcano planet, Planet Xeno, crystal moon), six weapons. | 40x12+ |
| **EMBERFALL** | A party role-playing adventure: create a hero, recruit companions, fight turn by turn with d20 rules, descend beneath the Ashpeaks. | 70x22+ |
| **BLOCKFIRE** | A first-person arena shooter: raycast 3D with textured walls, lit floors and pixel-art robots that come in waves. | 60x18+ |
| **DEEPCALL** | A submarine alone in the dark: only the sonar shows the trench, and every ping can be heard. Find air vents and salvage, keep the noise down, reach the Source at the bottom. | 60x20+ |
| **LIGHTKEEPER** | Keep the lighthouse through stormy nights: light ships past the reefs, sound the horn in the fog, refill the oil and send the rescue boat. Alone, or two keepers at one keyboard or over the LAN. | 70x22+ |
| **SKYSHOT** | An artillery duel on ground that breaks apart: set angle and power, read the wind, carve craters under the other tank. Four shells, best of three rounds. Two players at one keyboard or over the LAN, or one against the computer (easy / normal / hard). | 70x22+ |
| **NIGHTDRIVE** | Race through the night against the clock: winding hilly roads, headlights and street lamps, traffic and oncoming cars, six stages from neon city to a rainstorm. | 70x22+ |
| **ORBITAL** | A calm gravity puzzle: launch a probe past planets, moons, asteroid belts and wormholes to the dock ring. Fewer launches, more stars. | 70x22+ |
| **LEAFLING** | A jump'n'run with a leaf for a hat: run, jump, glide and wall-jump through twelve levels in four worlds (sunlit forest canopy, crystal caves, wind-swept sky ruins, an autumn storm at night), with light motes, hidden seeds, lanterns, beetles, bats, spitting plants, two chases and two bosses. | 70x22+ |
| **STACKFALL** | Falling blocks in a well ten wide and twenty deep. Modes: Marathon, Sprint (40 rows), Rising (rubble pushes up from below, every 45 seconds). | 40x20+ |
| **DEPTHWELL** | Falling blocks in three dimensions: look down into a well, turn cube pieces about all three axes, fill whole layers. Four well sizes, three piece sets. | 70x22+ |
| **GLIMMER** | A will-o'-wisp in a hedge maze at night: gather the light motes, catch the four shadow spirits while a sun blossom turns them pale. Eight hand-made mazes, some with one-way hedge gates, drifting fog or no light but your own, night treats and an interlude every third maze. | 60x22+ |
| **SPOREFIELD** | Stop the sporeworm before it reaches the roots: a fixed shooter on a glowing night meadow. Every hit splits the worm and leaves a toadstool; jitterlegs, plumbugs, gloam moths, puffballs and burrowgrubs get in the way, glowing seeds give double sap, piercing sap, slow time, bombs or a shell. Eight palettes, three difficulties. | 60x22+ |
| **SCAFFOLD** | Climb an unfinished skyscraper at night while a runaway demolition robot, the Wrecker, throws oil drums, gears, crates, rivets and counterweights down at you. Five stages (sloped girders, conveyor decks, lift shafts, a windy crane yard, the breaker floor where you cut its power), then it topples and comes back faster the next night. | 60x22+ |
| **VOIDLANCE** | A side-scrolling star fighter: charge the lance (three levels and a nova), dock the Warden pod at your nose or tail, feed it six kinds of crystal weapons, add missiles, crawler bombs, orbiting bits and shields. Eight stages from an orbital wreck yard to the Null Citadel, 41 kinds of enemies, each stage with its own caves, midboss and multi-phase boss. Easy / normal / hard, checkpoints, continues, stage select. | 70x22+ |
| **SHATTERWICK** | A brick breaker with a living candle spark: bounce Wick off the brass tray and shatter tinted, frosted, iron, powder, sliding and lantern glass. Twenty-five halls in five districts, each ending with a keeper; moths, jellies, cogs and cinders turn the spark aside. Campaign and Endless, gifts and trouble capsules, combos up to x8. | 60x22+ |
| **WARDSTONE** | Tower defense: raise seven kinds of rune towers (three levels, then one of two paths) against the Hollow host. Eight lands with fixed roads, several portals or open squares your towers shape, ten kinds of foes and four bosses, three stars per land, Campaign and Endless. | 70x22+ |
| **CLATTERBELL** | Pinball with three original tables (a moonlit belfry, a lantern reef, a comet forge with a third flipper): real ball physics, a plunger you pull, bumpers, slingshots, ramps, orbits, drop targets, a spinner and a kickback; lock two balls for multiball, timed missions, a wizard mode, nudge and tilt. | 60x22+ |
| **CAIRNWARD** | A box-pushing puzzle: push the scattered waystones back onto their rune sockets. 42 hand-made cairns in seven regions with black ice, one-way wind tiles, plates and gates and coloured stones; unlimited undo, par from the game's own solver. | 60x22+ |
| **GEMBURROW** | A cave digger: Pell the badger digs for sunstones while rocks fall and roll, beetles and glassmoths creep along the walls, creepmoss spreads and rune seams turn rock to gems. Twenty caves in five worlds plus five intermissions, easy / normal / hard. | 60x22+ |
| **WEFTWAR** | Light-thread duels on a night loom: every cell your shuttle crosses is woven shut behind it, touch a thread and you burst, the last rider weaving takes the round. Two riders at one keyboard, two to four over the LAN, or one against one to three computer riders (easy / normal / hard). Seven looms, a Spur meter, four charms, a rating. | 60x22+ |
| **PEBBLEPUTT** | Top-down minigolf: three courses of nine holes (a willow meadow, ice caverns, a copper foundry at night) with slopes, ramps, portals, ice, belts and moving gear arms. Solo or two to four players at one keyboard or over the LAN, scorecard with par. | 60x22+ |
| **THATCHWOLD** | A turn-based settlement game: every turn is a season. Place cottages, farms, fisheries, woodcutters, quarries, mines, mills and markets where the land and the neighbours pay most, lay up stores for winter, answer droughts, fevers, floods, wolves and raiders. Five scenarios with goals plus an endless mode. | 70x22+ |
| **FENMARK** | Logic puzzles: sound a peat fen for hidden bog-eyes (every fen is proved solvable without guessing) and mend leadlight windows from row and column clues (22 hand-made pictures plus random ones, each with exactly one solution). Hints that explain the next deduction, best times. | 70x22+ |
| **HEATHSHOT** | A shooting gallery on the heath, for letting off steam: round, fluffy puffwings cross three layers of a panning landscape (the far ones are tiny and score most), peek over the stone wall, dart past in gold or drift over in a balloon. Eight shells, reload with a right click, combos up to x4. Leave the sheep alone. 90 Seconds or Zen (no clock, no record). Mouse or keys. | 60x22+ |
| **BREAKROOM** | A rage room in four rooms (an office, a kitchen, a living room, a china shop): smash plates, mugs, vases, bottles, the monitor, the microwave, the big TV, figurines, urns, mirrors and the motivational poster with a hammer, a bat (it knocks things off the shelves) or a firecracker. Every shard falls and piles up, stacks collapse, the next room is delivered when one is rubble. Free Smash with a stress bar, or One Minute for the biggest damage bill. Mouse or keys. | 60x22+ |
| **SOLACE** | Patience on a green felt table: Klondike (draw one or three), Spider (one, two or four suits) and FreeCell with the classic numbered deals. Drag cards with the mouse or click one to send it where it fits; unlimited undo, hints, auto-complete, a bouncing finale, best times and wins per game. In auto mode a solver plays. | 60x22+ |
| **UNDERHOLD** | A roguelike for a quick run: one hero, ten new floors (halls and doors or caves with water and lava), field of view and a remembered map, seventeen kinds of foes (fast gnawers, slingers that keep their distance, splitting jellies, unseen lurkers, chanters that call for help) and the Mawkeeper at the bottom. Warden, Hexer or Skulker, a perk choice at every level, unidentified potions, scrolls and wands, food, permadeath. Mouse or keys. | 60x22+ |
| **PUCKSLIDE** | Air hockey with real physics on a glowing table: puck and mallets with mass, elastic hits and rebounds, and a moving mallet's speed goes into the shot. Two players at one keyboard (W A S D against the arrow keys) or over the LAN, or one against the computer (easy / normal / hard, also with the mouse). First to 5, 7 or 11. | 60x22+ |
| **SPANWORK** | A bridge builder with real physics: join the anchors with road, wood, steel and cable on a one-metre grid within a budget, then send the traffic across. Every joint has mass, every beam the stiffness, weight, strength and price of its material; loads show from green to red and beams snap past their limit in tension or compression. Eight crossings: wider gaps, a stepping stone, a van, a convoy, cable towers, a truck, a long haul. | 60x22+ |
| **PROPWASH** | A vertical-scrolling shooter with propeller planes: fly the Kestrel over six stages (a strait full of islands, a harbour town, the top of the cloud deck, a desert, snowy mountains, a night storm at sea) against diving fighter formations, bombers, gunboats, tanks and flak. Five gun levels, wingmen, medals that climb in value, red squadrons, a roll and bombs; a midboss and a boss of several parts in every stage. Easy / normal / hard, stage select. | 70x22+ |
| **FUSEYARD** | Fuse-pot duels in a walled yard for 1 to 4 people: drop clay pots that burst in a cross, burn the crates and grab what they hid (more pots, longer blasts, boots, kick, a ward, the curse that jumps from tinker to tinker); the last one standing wins the round, and late in a round the walls close in. One or two players at one keyboard with the computer filling the other places (easy / normal / hard), or a LAN party: one player hosts, the others join over the LAN or WLAN. Four yards, first to 1, 2, 3 or 5. | 70x22+ |

## Screenshots

![The menu](docs/screenshots/menu.png)

| | | |
|:-:|:-:|:-:|
| <img src="docs/screenshots/hoverdrift.png" alt="HOVERDRIFT" width="260"> | <img src="docs/screenshots/emberfall.png" alt="EMBERFALL" width="260"> | <img src="docs/screenshots/blockfire.png" alt="BLOCKFIRE" width="260"> |
| **HOVERDRIFT** | **EMBERFALL** | **BLOCKFIRE** |
| <img src="docs/screenshots/deepcall.png" alt="DEEPCALL" width="260"> | <img src="docs/screenshots/lightkeeper.png" alt="LIGHTKEEPER" width="260"> | <img src="docs/screenshots/skyshot.png" alt="SKYSHOT" width="260"> |
| **DEEPCALL** | **LIGHTKEEPER** | **SKYSHOT** |
| <img src="docs/screenshots/nightdrive.png" alt="NIGHTDRIVE" width="260"> | <img src="docs/screenshots/orbital.png" alt="ORBITAL" width="260"> | <img src="docs/screenshots/leafling.png" alt="LEAFLING" width="260"> |
| **NIGHTDRIVE** | **ORBITAL** | **LEAFLING** |
| <img src="docs/screenshots/stackfall.png" alt="STACKFALL" width="260"> | <img src="docs/screenshots/depthwell.png" alt="DEPTHWELL" width="260"> | <img src="docs/screenshots/glimmer.png" alt="GLIMMER" width="260"> |
| **STACKFALL** | **DEPTHWELL** | **GLIMMER** |
| <img src="docs/screenshots/sporefield.png" alt="SPOREFIELD" width="260"> | <img src="docs/screenshots/scaffold.png" alt="SCAFFOLD" width="260"> | <img src="docs/screenshots/voidlance.png" alt="VOIDLANCE" width="260"> |
| **SPOREFIELD** | **SCAFFOLD** | **VOIDLANCE** |
| <img src="docs/screenshots/shatterwick.png" alt="SHATTERWICK" width="260"> | <img src="docs/screenshots/wardstone.png" alt="WARDSTONE" width="260"> | <img src="docs/screenshots/clatterbell.png" alt="CLATTERBELL" width="260"> |
| **SHATTERWICK** | **WARDSTONE** | **CLATTERBELL** |
| <img src="docs/screenshots/cairnward.png" alt="CAIRNWARD" width="260"> | <img src="docs/screenshots/gemburrow.png" alt="GEMBURROW" width="260"> | <img src="docs/screenshots/weftwar.png" alt="WEFTWAR" width="260"> |
| **CAIRNWARD** | **GEMBURROW** | **WEFTWAR** |
| <img src="docs/screenshots/pebbleputt.png" alt="PEBBLEPUTT" width="260"> | <img src="docs/screenshots/thatchwold.png" alt="THATCHWOLD" width="260"> | <img src="docs/screenshots/fenmark.png" alt="FENMARK" width="260"> |
| **PEBBLEPUTT** | **THATCHWOLD** | **FENMARK** |
| <img src="docs/screenshots/heathshot.png" alt="HEATHSHOT" width="260"> | <img src="docs/screenshots/breakroom.png" alt="BREAKROOM" width="260"> | <img src="docs/screenshots/spanwork.png" alt="SPANWORK" width="260"> |
| **HEATHSHOT** | **BREAKROOM** | **SPANWORK** |
| <img src="docs/screenshots/solace.png" alt="SOLACE" width="260"> | <img src="docs/screenshots/underhold.png" alt="UNDERHOLD" width="260"> | <img src="docs/screenshots/puckslide.png" alt="PUCKSLIDE" width="260"> |
| **SOLACE** | **UNDERHOLD** | **PUCKSLIDE** |
| <img src="docs/screenshots/propwash.png" alt="PROPWASH" width="260"> | <img src="docs/screenshots/fuseyard.png" alt="FUSEYARD" width="260"> | |
| **PROPWASH** | **FUSEYARD** | |

The pictures come straight from the games' own canvases: `python3 scripts/screenshots.py` renders them again
(needs Pillow).

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

In auto mode the pilot only knows what its own pings have shown: it explores the dark, keeps quiet enough not
to wake the leviathan, tops up at vents and dives for the Source.

## LIGHTKEEPER keys

| Key | One keeper | Two keepers |
|---|---|---|
| Left / Right | turn the beam | keeper: turn the beam |
| Up / Down | focus: narrow reaches far, wide lights near | keeper: focus |
| Space | horn: ships nearby slow down and see their way | keeper: horn |
| `R` | refill the oil (the light is off for a moment) | keeper: refill |
| `B` | send the rescue boat to the nearest wreck | - |
| `W` `A` `S` `D` | same as the arrows | second player: steer the rescue boat |
| | | over the LAN: the host keeps the light, the one who joins steers the boat (arrows or W A S D both) |
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

Players take turns at the same keys (over the LAN each at their own computer, the host has the blue tank and the
land fits the smaller window); the coloured banner at the top says whose turn it is, and the dotted line
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
order first): one launch earns three stars, two to four launches two stars. Eight lessons come first, then
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

Auto mode plays the levels in order from the one picked on the world map, using the game's own route planner;
Leafling sometimes mistimes a jump and really loses a leaf, and goes after seeds when they are within reach.

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

## GLIMMER keys

| Key | |
|---|---|
| Arrows (`W` `A` `S` `D`) | move; a turn pressed early waits until the path opens |
| Left / Right (title) | choose the start maze |
| Enter / Space | skip the interlude |
| Esc / `P` | pause menu (`Q` there: back to the menu) |
| `?` | help |

Light motes 10, sun blossoms 50, pale spirits 200 / 400 / 800 / 1600 in a row, night treats 100 to 5000
(two per maze). Murk chases you straight on, Nettle cuts you off ahead, Hollow flanks you with Murk's help and
Sorrel is shy; all of them are slow in the tunnels. An extra wisp at 10000 points; the mazes repeat faster.

## SPOREFIELD keys

| Key | |
|---|---|
| Arrows / WASD | move the beetle in its corner (diagonals too) |
| Space | spit sap - hold it to keep firing |
| `F` | auto-fire on / off (handy in terminals without the kitty keyboard protocol) |
| Esc / `P` | pause menu (`Q` there: back to the menu) |
| `?` | help |

Every hit splits the sporeworm and turns the hit segment into a toadstool; heads score 100, segments 10, and
toadstools take four hits. Gloam moths poison caps (a worm that touches one dives straight down), plumbugs
drop new ones, jitterlegs eat them. Losing a beetle restores damaged and poisoned caps for a small bonus; an
extra beetle every 12000 points.

## SCAFFOLD keys

| Key | |
|---|---|
| Left / Right (`A` / `D`) | walk |
| Up / Down (`W` / `S`) | climb a ladder (stand in front of it) |
| Space / `Z` | jump (a fixed arc: aim before you go) |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

Reach the kill switch at the top of each stage; on the fifth, pull all six breakers. Jump drums, crates and
sparks for 200 / 400 / 800 points, or grab a hanging wrench and smash them for 8 seconds (no climbing while you
hold it). Falls further than your jump are fatal. The bonus counts down and is yours when you reach the goal;
at zero you lose a rigger. Bonus items lie around, an extra rigger comes at 10000 points, and every night (L)
the Wrecker throws faster. `python3 scaffold.py --selftest` proves every stage can be finished with the game's
own physics.

## VOIDLANCE keys

| Key | |
|---|---|
| Arrows / WASD | fly (8 directions) |
| Space | shoot; hold to charge the lance, let go to fire (kitty protocol) |
| `C` | start charging, `C` again: fire the lance |
| `X` | rapid fire |
| `F` | launch the pod / call it back |
| `B` | smart bomb |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

The lance has three levels - a bolt, a piercing bolt and a beam straight through the screen - and keeps
charging past the third into the NOVA, which wipes every bullet away. The Warden pod comes with the first
crystal: it docks at the nose or the tail, whichever side touches it, soaks up small shots and rams enemies;
launched, it keeps firing on its own. Crystals of the same colour raise the pod weapon to level 3, another
colour switches it (ring spread, ricochet ray, crawl wave, homing needles, scatter burst, chain arc). Item
carriers drop missiles, crawler bombs, orbiting bits, speed, shields, smart bombs and extra ships. Never touch
the walls. Each stage has two checkpoints; stages unlock as you reach them and can be picked on the title.

Terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) report key releases: tap
Space to shoot, hold it to charge. In other terminals (macOS Terminal) holding Space gives rapid fire while the
key repeats, and the lance is charged with `C` (press again to fire).

## SHATTERWICK keys

| Key | |
|---|---|
| Left / Right (`A` / `D`) | move the tray |
| Space (Up / `W`) | launch the spark, release a caught spark, strike Flint bolts |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

Keep Wick, a living candle spark, bouncing off the lamplighter's brass tray and shatter the tinted glass the Gloam
has sealed the lamp town with. Where the spark meets the tray sets its angle, and panes broken before it comes back
build a combo up to x8. Panes come tinted, frosted (2-3 hits, they crack), as iron plates that never break, as
powder panes that set off chain blasts, sliding, as lanterns that always drop a gift, and as frost that grows back.
Twenty-five halls in five districts (Glasshouse, Tide Cellar, Clock Loft, Frost Spire, Kiln Heart) each end with a
keeper. Moths, jellies, cogs, frost motes and cinders drift through the halls and turn the spark aside. Endless mode
builds new halls with a keeper every fifth. Gifts: Broadwick, Tallow (catch), Kindle (three sparks), Needleflame
(burns through glass), Flint (bolts), Lull, Hearth (a saving line) and Spare Wick; dark capsules are trouble
(Pinch, Gust, Soot). `python3 shatterwick.py --selftest` shows that the autopilot clears every hall.

## WARDSTONE keys

| Key | |
|---|---|
| Arrows / `WASD` | move the cursor (hold to glide) |
| `1` - `7` | pick a tower; on free ground it is built at once |
| Tab | next tower type |
| Space / Enter / `U` | build here, or upgrade the tower here (level III: first path) |
| `B` | second path for a level III tower |
| `X` / Backspace | sell the tower (70% back) |
| `T` | aim: first, last, strongest, closest |
| `N` | call the next wave now (bonus gold) |
| `F` | speed x1 / x2 / x3 |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

The Hollow host marches out of old portals to drain the Wardstones. Move the cursor over the land and raise rune
towers: Bolt Spires (single target, air too), Mortar Kilns (splash), Frost Bells (slow), Storm Coils (chain
lightning through armour), Sky Harpoons (anti-air), Venom Briars (poison that stops healing) and Beacon Shrines
(buff their neighbours). Each tower has three levels and then one of two paths, such as Longshot or Twinbolt,
Emberstorm or Quakeshell. Eight lands: Hollybrook Vale, Saltmarsh Reach, Ember Canyon, Lantern Market, Frostpine
Pass, Mosslight Ruins, Clockwork Yard and Starfall Crater. Some have fixed roads, some have two or three portals,
and the open squares let your towers shape the road. Foes include Scuttlers, fast Dartlings, armoured Shellbacks,
flying Wisps and Gale Crows, Mirelumps that split, healing Menders, shielded Bulwarks, Gravelhorns, and four bosses
up to the Hollow King. The next wave is shown before it comes. Gold comes from bounties, a wave bonus and interest,
and calling a wave early pays extra. Each land gives up to three stars; the campaign runs through all eight lands
and Endless never stops.

## CLATTERBELL keys

| Key | |
|---|---|
| Left / `Z` (`A`) | left flipper |
| Right / `M` (`/`, `L`) | right flipper (and the Forge's upper flipper) |
| Space / Down (`S`) | pull the plunger, let go to launch (classic terminals: a tap plunges at half strength) |
| Up / `W` (`N`) | nudge the table (too often: TILT) |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

A pinball parlour with three original tables: the Moonbell Belfry with bronze bells under an owl-filled night, the
Lantern Reef among glowing fish and clams, and the Comet Forge, a smithy between the stars with a third flipper. The
ball rolls by real physics on a tilted table: flippers that never let it slip through, a plunger you pull as far as
you like, pop bumpers, slingshots, a ramp, orbits, drop targets, rollover lanes, a spinner and a kickback. Drop the
targets to light the lock, lock two balls for three-ball multiball and shoot the ramp for the jackpot; two orbits
light a timed mission at the scoop, and four missions start the wizard mode. Bonus multiplier, skill shot, extra
ball, ball save, and a tilt that punishes rough nudging.

## CAIRNWARD keys

| Key | |
|---|---|
| Arrows / WASD | walk; push the stone ahead (hold to keep walking) |
| `U` / `Z` / Backspace | undo a move (unlimited; hold to rewind) |
| `R` | restart the cairn (undo brings it back) |
| `[` / `]` | previous / next open cairn |
| Enter | next cairn once solved |
| Esc / `P` | pause (`Q`: leave the cairn, `M`: sound) |
| `?` | help |

A storm has scattered the waystones of the old mountain pass. Hesper the cairn-keeper, a small badger with a
lantern, pushes every stone back onto its rune socket, one stone at a time and never pulling. There are 42 hand-made
cairns in seven regions. The Moss Steps and the Quarry Halls are pure pushing. Frostmere adds black ice (stones and
Hesper slide until something stops them), Windgate adds wind tiles you can only cross one way, the Lantern Vault
adds plates that hold iron gates open, the Rune Garden adds stones that belong on sockets of their own colour, and
the Summit mixes everything. Undo is unlimited and restart can be undone. Each cairn shows moves and pushes, your
best, and a par: the fewest moves, found by the game's own A* solver. In auto mode the solver thinks on screen, then
walks its solution.

## GEMBURROW keys

| Key | |
|---|---|
| Arrows / WASD | walk and dig (one cell per tick; a tap is one step) |
| Space + direction | reach: dig or take the next cell without moving |
| `R` | give up the cave (costs a life) |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

Pell, a young badger in a brass miner's helmet, digs down after the sunstones that once lit the warrens. Rocks and
sunstones fall the moment the soil beneath them is gone and roll off each other; push a rock by leaning on it twice.
Take each cave's quota to open the burrow door before the lamp oil runs out. Cinderbeetles creep along the walls and
burst into flame, glassmoths shatter into nine sunstones when a rock lands on them, creepmoss spreads through the
soil (shut in, it turns to sunstones; grown too big, to rock), and old rune seams turn falling rock into gems while
they glow. Twenty caves in five worlds plus five intermissions, three difficulty levels, scrolling caves whose tiles
grow finer with the window.

## WEFTWAR keys

| Key | |
|---|---|
| `W` `A` `S` `D` | Saffron (player 1) steers |
| arrows | Woad (player 2) steers; alone against the computer either set steers you |
| Space / `E` | Saffron's Spur (burst of speed) |
| Enter / `0` | Woad's Spur |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

On the Night Loom the dye riders steer shuttles of light, and every cell they cross is woven shut behind them with a
burning weft thread. Touch a thread, a rival's or your own, or the loom's frame, and your shuttle bursts; its thread
burns away and frees the cloth. The last rider weaving takes the round, first to two to five rounds takes the match.
Two riders share one keyboard, two to four ride at their own computers over the LAN (each with either set of keys),
or you take on one to three computer riders (Easy, Normal, Hard) that read the loom
with flood fills, a who-gets-there-first split of the cloth and a fill estimate for closed pockets. Seven looms
(Open Loom, Bobbin Court, Spindle Cross, Heddle Gates, Selvage Ring, Shuttle Run, Teasel Field), a Spur meter for
bursts of speed and four charms: Spur, Skip (cross threads), Thimble (tear one) and Unravel (shed your oldest
thread). Against the computer your rating rises and falls with every match. `python3 weftwar.py --selftest` measures
how often each computer level wins.

## PEBBLEPUTT keys

| Key | |
|---|---|
| Left / Right | aim: a tap turns 0.5 degrees, holding turns faster |
| `A` / `D` | aim in 15 degree steps |
| `C` | aim straight at the cup |
| Up / Down (`W` / `S`) | set the preset power |
| Enter | strike at the preset power |
| Space | swing meter: press to start, press again to strike (with key releases: hold and release) |
| `X` / Backspace | cancel the swing |
| Tab | scorecard |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

Minigolf seen from above: putt a painted pebble round three courses of nine holes. Willow Meadow has log rails,
ponds, mill sails, toadstool bumpers and rabbit burrows. Rimewater has ice that keeps rolling, snowdrifts, meltwater
crevasses, sliding ice gates, frost portals and ice ramps. The Copperworks at night has steel plates, conveyor
belts, gear arms, pistons, pipes, springs and pools of glowing slag. Hills and slopes are shaded and marked with
downhill arrows. Water and slag cost a stroke and put the pebble back, and the pebble only drops when it is slow
over the cup. Play solo or with two to four players at one keyboard or over the LAN (only the keys of the player
whose turn it is count), with a scorecard showing par, birdies and
bogeys, and a best round for every course and the 27-hole Grand Tour.

## THATCHWOLD keys

| Key | |
|---|---|
| Arrows / WASD | move the cursor (hold to keep going) |
| Tab / `]`, Shift-Tab / `[` | next / previous in the build menu |
| `1`-`9`, `0` | pick Cottage ... Market directly |
| `B` / `E` | build (or use the tool) at the cursor |
| `I` / `X` | improve / pull down what is under the cursor |
| `U` / `Z` / Backspace | undo this season's last placement |
| `K` | choose what the lore house studies |
| `H` | cursor back to the hall |
| Enter / Space | end the season (in an event: take the choice; `1`-`5` pick directly) |
| Esc / `P` | pause (`Q`: leave, or retire in endless; `M`: sound) |
| `?` | help |

Reeve Maudry leads a handful of thatchers out to settle the empty wolds, one season per turn. Farms grow in summer,
are harvested in autumn and rest in winter, when every hearth burns wood, so the autumn stores decide who sees the
spring. Placement matters: farms beside water and mills, woodcutters among trees, markets among cottages, wells and
greens near houses, watchtowers against wolves and raiders. The panel shows exactly what ending the season will
bring (+12 food, two born, mood 62 to 66), and every placement of the season can be undone. A small lore track
unlocks mills, longhouses and the Moot Ring. Five scenarios (Brackenleigh, Larkholm, Gorsecombe, Harrowmoor,
Saltcrag) have goals and time limits; endless mode grows a new wold. In auto mode the reeve plays a sensible
economy.

## FENMARK keys

| Key | |
|---|---|
| Arrows / WASD | move the lamp (hold to glide) |
| Space / Enter | probe a tussock, chord on a number / set glass |
| `F` / `X` | plant a reed flag / mark lead |
| hold Space or `X` + move | drag a stroke (kitty releases; classic: quick move, or `V` brush lock) |
| `U` / Backspace | undo (also climbs out of a bog, +30 s) |
| `H` | hint: the solver's next deduction, explained and highlighted (+15 s) |
| `C` | check flags / cells for errors (+20 s) |
| `N` / `R` | new fen or random pane / clear the pane |
| `[` / `]` | previous / next pane |
| Esc / `P` | pause (`Q` there: back; `V` there: the view, since V is the brush lock in the panes), `?` help |

Odile Sedge is warden of the Fenmark, a lantern-lit peat marsh. By day she sounds the fen with her ash pole: every
probed tussock tells how many hidden bog-eyes touch it, and reed flags mark the ones that must be there. The first
probe is always safe, and every fen is laid so that it can be sounded without a single guess; a logic solver proves
this before the fen is handed over. By night she mends the pump-house windows from the glazier's ledger. Each row
and column lists its runs of glass, and the 22 hand-made panes (heron, windpump, owl, lantern boat and more) light
up in colour once solved; random panes are added on demand. Every pane has exactly one solution that row-by-row
logic finds. Hints explain the next deduction and highlight the cells it used, a check marks mistakes for a time
penalty, and best times are kept per difficulty and pane. In auto mode the solver plays one explained step at a
time, using only what a player can see.

## HEATHSHOT keys

| Key | |
|---|---|
| Mouse | aim; move the sight to the screen edge and the view pans along the heath |
| Left click | fire (with an empty gun: reload) |
| Right click / `R` | reload |
| Wheel / `Q` / `E` | pan left / right |
| Arrows / WASD | move the sight without a mouse |
| Space / Enter | fire |
| Esc / `P` | pause (`Q` there: back), `?` help |

The puffwings come at three distances: far ones are worth 25, middle ones 10, near ones 5. Peekers over the stone
wall give 15, the rare golden puffwing 100, the balloon (three hits) 50. A sheep costs 25 and runs off bleating.
Hits less than 1.4 seconds apart build a combo: x2 from the fourth hit, up to x4. Shots into the wall or the tree
leave holes, the windmill's sails ring and spin faster. The score counts up in big digits at the top right. 90 Seconds keeps a best
score; Zen has no clock and keeps no record. The mouse needs a terminal that reports it (WezTerm, iTerm2, kitty, Ghostty and
Terminal.app all do); `ARCADE_NO_MOUSE=1` turns it off.

## BREAKROOM keys

| Key | |
|---|---|
| Mouse | aim |
| Left click | smash with the tool in hand |
| Right click / wheel | next tool |
| `1` `2` `3` / Tab | hammer, bat, firecracker |
| Arrows / WASD | move the hand without a mouse |
| Space / Enter | smash |
| `N` | the next room now |
| Left / Right (title) | the first room |
| Esc / `P` | pause (`Q` there: back), `?` help |

The hammer hits one thing, quickly. The bat hits everything within reach twice as hard and sends whatever survives
flying: off the shelf, off the desk, onto the floor, where glass and china break and a monitor takes another blow.
The firecracker is set down at the hand, fizzes for a moment and then breaks or throws everything near it; it also
throws the rubble up again. A plate stack collapses when its bottom plate goes. Every shard falls, bounces and
piles up. There are four rooms: the office (monitor, printer, keyboard, trophy), a kitchen (microwave, toaster,
teapots, jars), a living room (the big TV, a mirror, figurines, a floor urn) and a china shop full of porcelain.
When a room is down to rubble, the next one is delivered. In Free Smash the stress bar goes down
with every smash (the room's value decides how much); One Minute keeps the best damage bill.

## SPANWORK keys

| Key | |
|---|---|
| Left click / Space | start a beam at a joint (or a red anchor), then click where it ends; beams chain on |
| Right click / `X` | cancel the beam, or delete the one under the hand |
| Arrows / WASD | move the hand on the grid |
| `1` `2` `3` `4` / Tab / wheel | road, wood, steel, cable |
| `U` / `C` | undo / clear the bridge |
| Enter / `T` | test it; `R` back to building, Enter after a crossing: the next one |
| `N` / `B` | next / previous crossing |
| Esc / `P` | pause (`Q` there: back), `?` help |

The physics is position-based dynamics with compliant constraints (XPBD), fourteen substeps a frame: every joint
carries half the mass of its beams, every beam is a stiff spring (compliance = length / EA of its material), and
the force each beam carries comes straight out of the solve. Past its strength in tension or compression it snaps.
Road is the only thing wheels touch, wood is light and cheap, steel strong, heavy and dear, cable takes only
tension (it goes slack when pushed), and a road may be doubled with steel. Gravity comes on gently while the bridge
settles, then the traffic starts. A crossing counts when everything reaches the flag; the cheapest design within
budget is kept per crossing. Designs stay while the game runs. In auto mode the bot builds a truss beam by beam
(resting it on rocks, hanging it from towers) and tests it.

## SOLACE keys

| Key | |
|---|---|
| Mouse drag | move a card (a run moves with its top card) |
| Click a card | send it where it fits best (foundation first) |
| Right click | send the card to a foundation |
| Click the stock / Tab / `T` | draw (Klondike) or deal a row (Spider) |
| Arrows / WASD, Space / Enter | move the cursor, pick up and drop |
| `U` | undo (unlimited) |
| `H` | hint: the next good move lights up |
| `A` | auto-complete once every card is face up |
| `N` | new deal (after a FreeCell win: the next number) |
| Left / Right (title) | draw one or three, one/two/four suits, the FreeCell deal number (`R`: random) |
| Esc / `P` | pause (`Q` there: back), `?` help |

Klondike builds down in alternating colours with kings on empty columns, and the waste turns over without limit.
Spider builds down in any suit, but only a run of one suit moves together; a full King-to-Ace run of one suit
leaves the table, and a new row can be dealt only when no column is empty. FreeCell has four free cells; how many
cards move at once is (free cells + 1) × 2^(empty columns), with one empty column fewer when the target is empty.
Deals are reproducible, and FreeCell uses the classic numbering (deal #1 is the well-known one). Best times and
wins are kept for every variant. In auto mode a solver plays: greedy with care in Klondike and Spider, a real
search in FreeCell.

## UNDERHOLD keys

| Key | |
|---|---|
| Arrows / WASD / numpad | move; moving into a foe attacks |
| `Y` `U` `B` `N` | diagonals |
| Mouse | left click: travel there (or attack next to you, pick up / descend on your tile); right click: describe |
| `X` | explore until something turns up |
| `>` / Enter | travel to the stairs, then go down |
| `G` | pick up |
| `I` | inventory (then the item's letter: use, equip or `D` drop) |
| `Q` `R` `Z` `T` `E` | quaff, read, zap, throw, equip / eat |
| `F` | ability: second wind (Warden), hex bolt (Hexer), vanish (Skulker) |
| `C` / Space | rest until healed / wait a turn |
| `L` | look (arrows move the marker, Esc ends) |
| Esc / `P` | pause (`Q` there: back), `?` help |

Every run makes new floors and new looks for the potions, scrolls and wands: a "violet potion" may heal in one run
and poison in the next, so things are known only once used (or read about). The Warden is sturdy and can catch a
second wind, the Hexer is frail but casts hex bolts from regenerating mana, the Skulker stabs sleeping or unaware
foes for triple damage, throws knives and can vanish. Each level up offers two perks to choose from. Food keeps
hunger away; zapped wands and thrown knives aim at the nearest foe in sight. Death is final; the best score is kept
per hero (gold, depth, kills, level, and a bonus for slaying the Mawkeeper). In auto mode a bot explores, fights,
drinks potions when low and heads down.

## PUCKSLIDE keys

| Key | |
|---|---|
| W A S D | left mallet |
| Arrow keys | right mallet |
| Mouse | left mallet against the computer |
| | over the LAN: the host plays left, the one who joins right, both with either set of keys |
| Left / Right (title) | goals to win: 5, 7 or 11 |
| Esc / `P` | pause (`Q` there: back), `?` help |

The puck and the mallets have mass. Hits are elastic with a little loss, the walls give back 90 % of the speed,
and the air cushion barely slows the puck. A mallet that is moving hands its speed to the puck, so a hard swing
makes a hard shot. The physics takes as many small steps as the speed needs, so even the fastest shot never slips
through a mallet. Each player stays in their own half. In terminals with the kitty keyboard protocol held keys
steer exactly; in classic terminals (which repeat only the last key held) every tap gives the mallet a shove and
it glides on, so two players can still play at once. The title screen shows which mode is active. Against the
computer W A S D, the arrows and the mouse all steer you. The computer reacts a little late, predicts the puck off
the walls, guards its goal and attacks with straight or banked shots. Wins against each difficulty are counted.
Auto mode lets the computer play both sides.

## PROPWASH keys

| Key | |
|---|---|
| Arrows / WASD | fly (8 directions) |
| Space / `Z` | fire (hold it) |
| `F` | auto-fire on / off (on at the start) |
| `X` / `B` | bomb: wipes out every bullet and hits everything on screen |
| `C` | roll: a moment untouchable, then it recharges (the ROLL gauge) |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off) |
| `?` | help |

Only the little glass cockpit in the middle of the Kestrel can be hit. `P` items raise the guns through five
levels (twin guns, then outer guns, two spreads and homing rockets), `B` adds a bomb, `W` brings two wingmen who
fire with you and each take one bullet, `1` is an extra life (and so is every 200,000 points after the first
100,000). Ground targets leave gold medals: each one caught is worth more than the last (200 up to 5,000), and one
that falls past starts the ladder again. Shoot down every plane of a red squadron for a `P`. Losing a plane costs
one gun level (it drops as a `P` you can catch again) and the wingmen.

Every stage has a midboss halfway and a boss at the end, built from parts: engines and turrets first, then the
core opens (the last boss has three phases). Shots only hit the parts that are open; the bar at the top shows what
is left. A stage clear pays for the share of planes downed and the bombs still in stock. Stages unlock as you reach
them and can be picked on the title; a continue after the game over keeps you where you are but resets the score.
In terminals without the kitty keyboard protocol held keys follow the key repeat, which is why auto-fire is on from
the start.

## FUSEYARD keys

| Key | |
|---|---|
| `W` `A` `S` `D` / arrows | walk (playing alone, either set works) |
| Space / `E` | drop a fuse pot |
| arrows + Enter / `0` | the second player, when two share one keyboard (the first one has W A S D + Space) |
| Esc / `P` | pause menu (`Q` there: back to the menu, `M`: sound on / off); in a LAN game a menu, the game goes on |
| `?` | help |

A pot bursts after 2.6 seconds in a cross along the lanes; pillars stop the blast, the first crate in its way
burns, and a pot the blast reaches goes off too. Burnt crates leave items: `P` one pot more, `F` a longer blast,
`S` quicker boots, `K` kick (walk into a pot and it slides until something stops it), `W` a ward that takes one
hit, and `?` the curse (slow feet, short fuses, dripping pots or tiny blasts for twelve seconds; it jumps to
whoever you touch). A tinker who is out drops some of what they carried. The last one standing wins the round; at
0:45 the walls start to close in from the outside, ring by ring. A tap walks exactly one tile, a held key keeps
walking; in classic terminals (without the kitty keyboard protocol) every key repeat walks one tile on.

On the title: `Players here` (one or two at this keyboard), `Tinkers` (2 to 4; the computer fills the places
nobody takes), `Computer` (easy / normal / hard), `Yard` (Courtyard, Mill Yard, Frost Yard, Foundry or changing
every round), `Wins needed` and `Your name` (just type it).

**LAN party.** One player picks `Host a LAN game`: that computer becomes the server and runs the game, and the
lobby shows its address. The others pick `Join a LAN game`: games in the same network (LAN or WLAN) show up there
by themselves, or the host's address can be typed (`192.168.1.20`, or `192.168.1.20:47290`). Two people may share
each keyboard, up to four players in all; the host starts with Enter and empty places go to the computer. Someone
who leaves mid-game is taken over by the computer; after a match Enter takes everyone back to the lobby. The game
uses TCP port 47290 (the next free one up to 47299) and UDP port 47291 for finding games; if the macOS firewall
asks whether Python may accept incoming connections, allow it on the host. Wins of whole matches against the
computer are counted per difficulty.

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
| `arcadekit.py` | shared toolkit: raw terminal input (with held keys via the kitty keyboard protocol, and the mouse), half-block pixel canvas with the ASCII views, block font, high scores |
| `arcadesound.py` | the sound engine: synthesized effects, played without waiting |
| `arcadenet.py` | LAN play: the host's server, the beacon that finds games, the lobby and join screens, pictures and keys over the wire |
| `stackfall.py`, `depthwell.py`, `deepcall.py`, `lightkeeper.py`, `skyshot.py`, `nightdrive.py`, `orbital.py`, `leafling.py`, `glimmer.py`, `sporefield.py`, `scaffold.py`, `voidlance.py`, `heathshot.py`, `breakroom.py`, `spanwork.py`, `solace.py`, `underhold.py`, `puckslide.py`, `propwash.py`, `fuseyard.py` | the games written for the arcade (use `arcadekit.py`) |
| `hoverdrift.py`, `emberfall.py`, `blockfire.py` | HOVERDRIFT, EMBERFALL and BLOCKFIRE (they run on their own and do not need `arcadekit.py`) |
| `extras/emberfall-art/` | the source images and tools behind EMBERFALL's pictures (not in the Homebrew package) |
| `VERSION` | the current version (written by the release workflow) |
| `Formula/ascii-arcade.rb` | the Homebrew formula (this repository is its own tap) |
| `.github/workflows/release.yml`, `scripts/next_version.py` | automatic versioning and releases |
| `scripts/screenshots.py`, `docs/screenshots/` | the README pictures, rendered from the games' canvases |
| `LICENSE` | MIT License |
