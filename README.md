# Tempo

A practice player and song library for musicians. Slow songs down or speed them up without changing the pitch (Rubber Band R3 engine), loop passages, transpose, follow along with synced lyrics, and split songs into instruments.

Works on Windows and Mac.

## Download

Get the newest version from **[Releases](../../releases/latest)**:

| File | For |
|---|---|
| `Tempo-Windows.zip` | Windows app. Unzip and run `Tempo.exe`. |
| `Tempo-Mac.zip` | Mac with Apple Silicon (M1, M2, M3, M4…). Unzip, then right-click `Tempo.app` > Open the first time. |
| `Tempo-Mac-Intel.zip` | Mac with an Intel processor. Same steps. |
| `Tempo-source.zip` | Python version for any Windows or Mac computer. See `README.txt` inside. |

Not sure which Mac you have? Apple menu › About This Mac: it says either "Chip: Apple M…" or "Processor: Intel…".

All three include instrument splitting.

Tempo checks for new versions itself: click **Updates** in the toolbar.

## Publishing a new version

1. Raise `__version__` in `tempo/__init__.py` and commit.
2. On GitHub: **Releases › Draft a new release**, create a tag like `v1.2.0`, and click **Publish release**.
3. GitHub Actions builds the apps and attaches them to the release (about 10–15 minutes). Tempo's **Updates** button finds it from then on.

## Credits

Time stretching by [Rubber Band Library](https://breakfastquay.com/rubberband/) via `pylibrb`. Lyrics from [LRCLIB](https://lrclib.net). Instrument separation by [Demucs](https://github.com/facebookresearch/demucs).
