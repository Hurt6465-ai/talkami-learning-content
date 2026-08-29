# Fixed Chinese word audio

Put the recorded Chinese word MP3 files here. The web client resolves recordings directly from the word `level` and numeric `id`; no audio URL is stored in the word JSON.

Examples:

- `audio/hsk1/1.mp3` -> HSK1 word id `1`
- `audio/hsk2/151.mp3` -> HSK2 word id `151`
- `audio/hsk3/301.mp3` -> HSK3 word id `301`

Keep IDs stable. Replacing an MP3 at the same path keeps the data format unchanged. The website caches these files locally after a pack is opened.
