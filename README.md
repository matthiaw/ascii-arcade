# ASCII ARCADE

![The ASCII ARCADE start screen: all twenty-four games playing at once](docs/screenshots/start.gif)

A little collection of games for the terminal. Start the launcher: the start screen shows all games playing at once
(Enter starts the highlighted one, any other key opens the menu). Pick a game with the arrow keys (or its number:
1-24, two digits typed quickly one after the other), press Enter. When the game ends you are back in the menu.

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
| Q | in the pause menu: quit - on a title screen: quit (in DEPTHWELL Q also turns pieces) |
| ? | help with all of the game's keys, also on the title screens |
| Enter / Space | confirm |
| Arrows / WASD | move, choose |

Every game has an **Auto mode** entry on its title screen: the real game plays itself (EMBERFALL: `--auto`,
or `A` in a run; SKYSHOT: CPU against CPU). Space pauses, `+` / `-` change the speed (x0.25 to x8), Esc stops.
Auto runs never enter the high-score list.

The pause menu always reads: Esc / P / Enter continue, ? help, M sound on / off, Q quit. No game ends on a single stray key.

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
| **LIGHTKEEPER** | Keep the lighthouse through stormy nights: light ships past the reefs, sound the horn in the fog, refill the oil and send the rescue boat. Alone, or two keepers at one keyboard. | 70x22+ |
| **SKYSHOT** | An artillery duel on ground that breaks apart: set angle and power, read the wind, carve craters under the other tank. Four shells, best of three rounds. Two players at one keyboard or one against the computer (easy / normal / hard). | 70x22+ |
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
| **WEFTWAR** | None | 60x22+ |
| **PEBBLEPUTT** | Top-down minigolf: three courses of nine holes (a willow meadow, ice caverns, a copper foundry at night) with slopes, ramps, portals, ice, belts and moving gear arms. Solo or two to four players at one keyboard, scorecard with par. | 60x22+ |
| **THATCHWOLD** | A turn-based settlement game: every turn is a season. Place cottages, farms, fisheries, woodcutters, quarries, mines, mills and markets where the land and the neighbours pay most, lay up stores for winter, answer droughts, fevers, floods, wolves and raiders. Five scenarios with goals plus an endless mode. | 70x22+ |
| **FENMARK** | Logic puzzles: sound a peat fen for hidden bog-eyes (every fen is proved solvable without guessing) and mend leadlight windows from row and column clues (22 hand-made pictures plus random ones, each with exactly one solution). Hints that explain the next deduction, best times. | 70x22+ |

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
Two riders share one keyboard, or you take on one to three computer riders (Easy, Normal, Hard) that read the loom
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
over the cup. Play solo or with two to four players at one keyboard, with a scorecard showing par, birdies and
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
| Esc / `P` | pause (`Q` there: back), `?` help |

Odile Sedge is warden of the Fenmark, a lantern-lit peat marsh. By day she sounds the fen with her ash pole: every
probed tussock tells how many hidden bog-eyes touch it, and reed flags mark the ones that must be there. The first
probe is always safe, and every fen is laid so that it can be sounded without a single guess; a logic solver proves
this before the fen is handed over. By night she mends the pump-house windows from the glazier's ledger. Each row
and column lists its runs of glass, and the 22 hand-made panes (heron, windpump, owl, lantern boat and more) light
up in colour once solved; random panes are added on demand. Every pane has exactly one solution that row-by-row
logic finds. Hints explain the next deduction and highlight the cells it used, a check marks mistakes for a time
penalty, and best times are kept per difficulty and pane. In auto mode the solver plays one explained step at a
time, using only what a player can see.

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
| `arcadekit.py` | shared toolkit: raw terminal input (with held keys via the kitty keyboard protocol), half-block pixel canvas, block font, high scores |
| `arcadesound.py` | the sound engine: synthesized effects, played without waiting |
| `stackfall.py`, `depthwell.py`, `deepcall.py`, `lightkeeper.py`, `skyshot.py`, `nightdrive.py`, `orbital.py`, `leafling.py`, `glimmer.py`, `sporefield.py`, `scaffold.py`, `voidlance.py` | the games written for the arcade (use `arcadekit.py`) |
| `hoverdrift.py`, `emberfall.py`, `blockfire.py` | HOVERDRIFT, EMBERFALL and BLOCKFIRE (they run on their own and do not need `arcadekit.py`) |
| `extras/emberfall-art/` | the source images and tools behind EMBERFALL's pictures (not in the Homebrew package) |
| `VERSION` | the current version (written by the release workflow) |
| `Formula/ascii-arcade.rb` | the Homebrew formula (this repository is its own tap) |
| `.github/workflows/release.yml`, `scripts/next_version.py` | automatic versioning and releases |
| `scripts/screenshots.py`, `docs/screenshots/` | the README pictures, rendered from the games' canvases |
| `LICENSE` | MIT License |
