#!/usr/bin/env python3
import copy
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CONTENT = ROOT / "content"


def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {path}: {exc}")


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fail(message: str):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        fail(f"Missing or empty {label}")


def require_version(value, label):
    try:
        number = int(value)
    except (TypeError, ValueError):
        fail(f"{label} must be an integer")
    if number <= 0:
        fail(f"{label} must be greater than zero")
    return number


def safe_asset_name(value, label):
    require_text(value, label)
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.name in {".", ".."}:
        fail(f"{label} must be a plain file name: {value}")
    return value


def walk_catalog_items(items):
    for item in items or []:
        yield item
        yield from walk_catalog_items(item.get("children", []))


def validate_catalog_ids(items, catalog_name):
    seen = set()
    for item in walk_catalog_items(items):
        item_id = item.get("id", "")
        require_text(item_id, f"{catalog_name} item id")
        if item_id in seen:
            fail(f"Duplicate {catalog_name} catalog id: {item_id}")
        seen.add(item_id)


def validate_unique_records(records, id_key, order_key, label):
    seen_ids = set()
    seen_orders = set()
    for index, record in enumerate(records, start=1):
        record_id = record.get(id_key, "")
        require_text(record_id, f"{label} #{index} {id_key}")
        if record_id in seen_ids:
            fail(f"Duplicate {label} id: {record_id}")
        seen_ids.add(record_id)
        if order_key:
            order = record.get(order_key)
            try:
                order = int(order)
            except (TypeError, ValueError):
                fail(f"{label} {record_id} has invalid order")
            if order <= 0 or order in seen_orders:
                fail(f"{label} {record_id} has duplicate or invalid order: {order}")
            seen_orders.add(order)


def build_words():
    source_path = CONTENT / "words" / "catalog.json"
    source = load_json(source_path)
    validate_catalog_ids(source.get("items", []), "word")
    result = copy.deepcopy(source)
    used_output_names = set()

    for item in walk_catalog_items(result.get("items", [])):
        source_data_value = item.pop("source_data", "")
        source_cover_value = item.pop("source_cover", "")
        if not source_data_value:
            continue

        if item.get("target") != "word":
            fail(f"Word leaf {item.get('id')} must use target=word")
        require_text(item.get("level"), f"word catalog level for {item.get('id')}")
        data_url = safe_asset_name(item.get("data_url"), f"data_url for {item.get('id')}")
        cover_url = safe_asset_name(item.get("cover_url"), f"cover_url for {item.get('id')}")
        require_version(item.get("cover_version"), f"cover_version for {item.get('id')}")

        for output_name in (data_url, cover_url):
            if output_name in used_output_names:
                fail(f"Duplicate release asset name: {output_name}")
            used_output_names.add(output_name)

        source_data = ROOT / source_data_value
        source_cover = ROOT / source_cover_value
        if not source_data.is_file():
            fail(f"Missing word pack: {source_data}")
        if not source_cover.is_file():
            fail(f"Missing word cover: {source_cover}")

        pack = load_json(source_data)
        items = pack.get("items")
        if not isinstance(items, list) or not items:
            fail(f"Empty word pack: {source_data}")
        if pack.get("categoryId") != item.get("level"):
            fail(f"Word pack categoryId must equal catalog level for {item.get('id')}")
        version = require_version(pack.get("version"), f"word pack version in {source_data}")
        validate_unique_records(items, "id", "order", f"word in {source_data.name}")

        for word in items:
            word_id = word.get("id")
            require_text(word.get("word"), f"word text for {word_id}")
            require_text(word.get("pinyin_override"), f"pinyin for {word_id}")
            require_text(word.get("meaning_my"), f"Myanmar meaning for {word_id}")
            require_text(word.get("example"), f"example for {word_id}")
            require_text(word.get("example_pinyin_override"), f"example pinyin for {word_id}")

        output_data = DIST / data_url
        output_cover = DIST / cover_url
        shutil.copy2(source_data, output_data)
        shutil.copy2(source_cover, output_cover)
        item["data_sha256"] = sha256(output_data)
        item["item_count"] = len(items)
        item["data_version"] = version

    write_json(DIST / "words-catalog.json", result)


def build_speaking():
    source_path = CONTENT / "speaking" / "catalog.json"
    source = load_json(source_path)
    validate_catalog_ids(source.get("items", []), "speaking")
    result = copy.deepcopy(source)
    used_output_names = set()

    for item in walk_catalog_items(result.get("items", [])):
        source_value = item.pop("source_data", "")
        if not source_value:
            continue

        if item.get("target") != "study":
            fail(f"Speaking leaf {item.get('id')} must use target=study")
        data_url = safe_asset_name(item.get("data_url"), f"data_url for {item.get('id')}")
        if data_url in used_output_names:
            fail(f"Duplicate release asset name: {data_url}")
        used_output_names.add(data_url)

        source_data = ROOT / source_value
        if not source_data.is_file():
            fail(f"Missing speaking pack: {source_data}")
        pack = load_json(source_data)
        phrases = pack.get("phrases", pack.get("items"))
        if not isinstance(phrases, list) or not phrases:
            fail(f"Empty speaking pack: {source_data}")
        if pack.get("pack_id") != item.get("id"):
            fail(f"Speaking pack_id must equal catalog id for {item.get('id')}")
        version = require_version(pack.get("version"), f"speaking pack version in {source_data}")
        validate_unique_records(phrases, "id", None, f"phrase in {source_data.name}")

        for entry in phrases:
            phrase_id = entry.get("id")
            require_text(entry.get("text"), f"phrase text for {phrase_id}")
            require_text(entry.get("pinyin"), f"phrase pinyin for {phrase_id}")
            require_text(entry.get("meaning_my"), f"Myanmar meaning for {phrase_id}")
            if "meaning_ny" in entry:
                fail(f"Typo meaning_ny found in phrase {phrase_id}; use meaning_my")

        output_data = DIST / data_url
        shutil.copy2(source_data, output_data)
        item["data_sha256"] = sha256(output_data)
        item["item_count"] = len(phrases)
        item["data_version"] = version

    write_json(DIST / "speaking-catalog.json", result)


def package_metadata():
    packages = {}
    packages_root = CONTENT / "packages"
    if not packages_root.is_dir():
        return packages
    for directory in sorted(p for p in packages_root.iterdir() if p.is_dir()):
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            fail(f"Missing package manifest: {manifest_path}")
        manifest = load_json(manifest_path)
        package_id = manifest.get("package_id", "")
        version = require_version(manifest.get("version"), f"package version in {manifest_path}")
        require_text(package_id, f"package_id in {manifest_path}")
        zip_name = f"{package_id}-v{version}.zip"
        zip_path = DIST / zip_name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path in sorted(p for p in directory.rglob("*") if p.is_file()):
                zf.write(path, path.relative_to(directory).as_posix())
        packages[package_id] = {
            "version": version,
            "url": zip_name,
            "sha256": sha256(zip_path),
            "size": zip_path.stat().st_size,
            "manifest": manifest,
            "directory": directory,
        }
    return packages


def build_learning_path(packages):
    catalog = load_json(CONTENT / "learning_path" / "catalog.json")
    seen_lessons = set()
    for course in catalog.get("courses", []):
        course_id = course.get("id", "")
        for unit in course.get("units", []):
            unit_id = unit.get("id", "")
            for lesson in unit.get("lessons", []):
                lesson_id = lesson.get("id", "")
                if not lesson_id or lesson_id in seen_lessons:
                    fail(f"Invalid or duplicate lesson id: {lesson_id}")
                seen_lessons.add(lesson_id)
                package_id = lesson.get("package_id", "")
                meta = packages.get(package_id)
                if not meta:
                    fail(f"Lesson {lesson_id} references missing package {package_id}")
                manifest = meta["manifest"]
                if manifest.get("course_id") != course_id or manifest.get("unit_id") != unit_id:
                    fail(f"Package {package_id} course/unit does not match catalog")
                if int(lesson.get("package_version", 0)) != meta["version"]:
                    fail(f"Package version mismatch for lesson {lesson_id}")
                lesson_file = lesson.get("lesson_file", "")
                source_lesson = meta["directory"] / lesson_file
                if not source_lesson.is_file():
                    fail(f"Missing lesson file: {source_lesson}")
                lesson_json = load_json(source_lesson)
                if lesson_json.get("lesson_id") != lesson_id:
                    fail(f"lesson_id mismatch in {source_lesson}")
                lesson["package_url"] = meta["url"]
                lesson["package_sha256"] = meta["sha256"]
                lesson["package_size"] = meta["size"]
    write_json(DIST / "learning-path-catalog.json", catalog)


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    build_words()
    build_speaking()
    packages = package_metadata()
    build_learning_path(packages)

    metadata = {
        "release_version": os.environ.get("RELEASE_VERSION", "local-test"),
        "assets": []
    }
    for path in sorted(p for p in DIST.iterdir() if p.is_file()):
        metadata["assets"].append({
            "name": path.name,
            "size": path.stat().st_size,
            "sha256": sha256(path)
        })
    write_json(DIST / "content-metadata.json", metadata)

    print("Build succeeded. Release assets:")
    for path in sorted(DIST.iterdir()):
        print(f"  {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
