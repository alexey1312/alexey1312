# Profile generator

This folder makes the [profile README](../README.md).
The README is a stack of SVG slices that read as one console.
Do not edit `README.md` or `assets/` by hand:
the next run writes over them.

## Files

| File | What it holds |
| --- | --- |
| `profile.json` | The text: header, links, projects, stack, posts. Edit this file. |
| `fetch.py` | Gets the numbers from GitHub into `data/`. |
| `render.py` | Draws `assets/*.svg` and writes `README.md` from `profile.json` and `data/`. |
| `data/` | The last numbers that `fetch.py` got. A failed fetch keeps them. |
| `icons.json` | Icon paths for the link buttons. |
| `fonts/` | JetBrains Mono. Each SVG embeds a subset of it. |

## Run it

```bash
mise run render    # draw from the data that is already in data/
mise run readme    # get fresh numbers, then draw
```

`mise run readme` needs `GITHUB_TOKEN` or `PROFILE_TOKEN`.
Locally, `GITHUB_TOKEN=$(gh auth token) mise run readme` works.

The same data gives byte-identical files,
so a second run on the same day makes no commit.
The `last sync` date in the stats changes every day,
so the workflow commits once a day.

## Phone

Each slice has a phone variant in `assets/phone/`.
It is 440 px wide, half the desktop width,
so its text shows twice as large on a narrow screen.
The README swaps it in with `<picture>` below 600 px.
The image widths in a row stay the same,
so a phone card is half as wide and wraps its text.
The `srcset` points to the file on `main`,
so a phone variant shows only after a push.

## Every day

`.github/workflows/profile.yml` runs `mise run readme` every day at 08:17 in Almaty
and commits the changes.
It also runs when you push a change to this folder.

With only `GITHUB_TOKEN`, the stats count public work.
To count private contributions too,
add a classic token with the `read:user` and `repo` scopes
as the repository secret `PROFILE_TOKEN`.

## Change the content

- A new project card:
  add an item to `projects` in `profile.json`.
  The cards go in pairs, so keep an even number.
  The description wraps at 43 characters and can have three lines at most.
- A small project:
  add an item to `also`.
  Keep a multiple of four items.
  The description wraps at 21 characters and can have two lines at most.
  On a phone, only the name shows:
  it wraps at 10 characters and can have three lines at most.
- A new post:
  add an item to `writing.posts`, newest first.

`render.py` stops with an assertion when a text does not fit its box.

## Credits

The console design, the slices and the contribution city come from
[Giorgi Kobaidze's profile](https://github.com/georgekobaidze/georgekobaidze)
under the MIT license; see [NOTICE](../NOTICE).
The install line on each project card and the phone variants are ideas from
[@jdx's profile](https://github.com/jdx/jdx).
