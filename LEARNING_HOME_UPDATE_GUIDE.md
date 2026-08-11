# Learning home remote update

The learning-home hero follows the same source/build/release pipeline as words, speaking, books and learning packages.

## Source files you edit

- `content/home/catalog.json`
- `content/home/assets/learning-home-hero-v1.webp`

Do not hand-edit `dist/`. `scripts/build_release.py` deletes and rebuilds `dist/` every release.

## Generated Release assets

The build creates:

- `learning-home.json`
- `learning-home-hero-v1.webp`

The Android app downloads `learning-home.json`, caches it in `files/learning/catalogs/home.json`, and caches the verified hero image under the app cache directory.

## Updating the hero image

1. Add a new source image, for example `content/home/assets/learning-home-hero-v2.webp`.
2. Change `image_url` to `learning-home-hero-v2.webp`.
3. Increase `image_version`.
4. Increase the top-level `version` and update `updated_at`.
5. Run the normal Publish learning content Action with a new Release version.

`image_size` and `image_sha256` are generated automatically.

## Updating hero text

Edit the `slides` in `content/home/catalog.json`. Supported localized keys are:

- `title`, `title_en`, `title_my`
- `subtitle`, `subtitle_en`, `subtitle_my`
- `price`, `price_en`, `price_my`
- `note`, `note_en`, `note_my`

Increase the top-level `version`, update `updated_at`, and publish a new Release.
