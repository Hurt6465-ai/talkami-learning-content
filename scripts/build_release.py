#!/usr/bin/env python3
import copy
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CONTENT = ROOT / "content"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def build_words():
    source = load_json(CONTENT / "words" / "catalog.json")
    result = copy.deepcopy(source)
    for item in result.get("items", []):
        source_data = ROOT / item.pop("source_data", "")
        source_cover = ROOT / item.pop("source_cover", "")
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
        output_data = DIST / item["data_url"]
        output_cover = DIST / item["cover_url"]
        shutil.copy2(source_data, output_data)
        shutil.copy2(source_cover, output_cover)
        item["data_sha256"] = sha256(output_data)
        item["item_count"] = len(items)
        item["data_version"] = int(pack.get("version", item.get("data_version", 1)))
    write_json(DIST / "words-catalog.json", result)


def package_metadata():
    packages = {}
    packages_root = CONTENT / "packages"
    for directory in sorted(p for p in packages_root.iterdir() if p.is_dir()):
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            fail(f"Missing package manifest: {manifest_path}")
        manifest = load_json(manifest_path)
        package_id = manifest.get("package_id", "")
        version = int(manifest.get("version", 0))
        if not package_id or version <= 0:
            fail(f"Invalid package manifest: {manifest_path}")
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
