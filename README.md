# Tempo

A practice player and song library for musicians. Slow songs down or speed them up without changing the pitch (Rubber Band R3 engine), loop passages, transpose, follow along with synced lyrics, and split songs into instruments.

Works on Windows and Mac.

## Download

Get the newest version from **[Releases](../../releases/latest)**:

| File | For |
|---|---|
| `Tempo-Windows.zip` | Windows app. Unzip and run `Tempo.exe`. |
| `Tempo-Mac.zip` | Mac app (Apple Silicon). Unzip, then right-click `Tempo.app` > Open the first time. |
| `Tempo-source.zip` | Python version for any Windows or Mac computer, including instrument splitting. See `README.txt` inside. |

Tempo checks for new versions itself: click **Updates** in the toolbar.

## Publishing a new version

1. Raise `__version__` in `tempo/__init__.py`.
2. Commit, then tag and push: `git tag v1.2.0 && git push --tags`.
3. GitHub Actions builds the apps and publishes the release (about 10–15 minutes).

## Credits

Time stretching by [Rubber Band Library](https://breakfastquay.com/rubberband/) via `pylibrb`. Lyrics from [LRCLIB](https://lrclib.net). Instrument separation by [Demucs](https://github.com/facebookresearch/demucs).
