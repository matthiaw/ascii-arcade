# EMBERFALL art sources

The pictures of EMBERFALL (monsters, areas, portraits, the title picture) are baked into `emberfall.py` as
half-block pixel art, so the game needs nothing from this folder. These are the sources, kept so the art can be
changed and baked again:

| | |
|---|---|
| `art/src/*.jpg` | the source images (generated with Leonardo.ai) |
| `art/manifest.json` | which image becomes which picture, with width, height and crop |
| `tools/bake_art.py` | converts the images and writes them into `../../emberfall.py` (between the PICS markers) |
| `tools/img2term.py`, `tools/term2png.py` | image -> terminal pixels, and terminal output -> PNG for checking |

```sh
python3 extras/emberfall-art/tools/bake_art.py
```

This folder is not part of the Homebrew package. The code is under the MIT License like the rest of the
repository; the images were made with Leonardo.ai, and their use follows Leonardo.ai's terms.
