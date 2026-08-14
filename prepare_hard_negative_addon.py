#!/usr/bin/env python3
"""
Prepare reviewed hard-negative images as a YOLO detection dataset add-on.

This tool DOES NOT retrain the model and DOES NOT modify the original dataset.

It selects only:
    review_label == "true_negative"

and copies the full-frame images into:
    <output>/images/train/

No YOLO label file is created for these images because they contain no
Fire/Smoke objects. Ultralytics detection datasets support background images
without a corresponding .txt label file.

Example:
    python prepare_hard_negative_addon.py ^
      --run-dir "static\hard_negative_runs\preset4_false_positive_20260814_194439" ^
      --output "datasets\hard_negative_addon_v1"
"""

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


def load_records(run_dir: Path):
    jsonl_path = run_dir / "candidates.jsonl"
    manifest_path = run_dir / "review_export" / "manifest.json"

    if jsonl_path.exists():
        records = []
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records, "candidates.jsonl"

    if manifest_path.exists():
        records = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

        # Normalize manifest schema to candidates schema.
        normalized = []
        for r in records:
            normalized.append(
                {
                    "event_id": r.get("event_id"),
                    "review_label": r.get("review_label"),
                    "class": r.get("prediction"),
                    "confidence": r.get("confidence"),
                    "bbox": r.get("bbox"),
                    "full_image": r.get("source"),
                    "exported_image": r.get("exported_image"),
                }
            )
        return normalized, "review_export/manifest.json"

    raise FileNotFoundError(
        "ไม่พบ candidates.jsonl หรือ review_export/manifest.json"
    )


def sha1_file(path: Path):
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def resolve_source_image(run_dir: Path, record: dict):
    """
    Prefer reviewed export image if it exists, otherwise use the original
    full-frame candidate.
    """
    exported = record.get("exported_image")
    if exported:
        p = run_dir / "review_export" / Path(exported)
        if p.exists():
            return p

    full = record.get("full_image")
    if full:
        p = run_dir / Path(full)
        if p.exists():
            return p

    source = record.get("source")
    if source:
        p = run_dir / Path(source)
        if p.exists():
            return p

    return None


def unique_name(record: dict, src: Path):
    event_id = int(record.get("event_id") or 0)
    pred = str(
        record.get("class")
        or record.get("prediction")
        or "unknown"
    ).lower()

    conf = record.get("confidence")
    try:
        conf_text = f"{float(conf):.3f}"
    except Exception:
        conf_text = "na"

    return (
        f"hardneg_event_{event_id:04d}_"
        f"pred_{pred}_conf_{conf_text}{src.suffix.lower()}"
    )


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Prepare reviewed true-negative images "
            "as a YOLO hard-negative add-on."
        )
    )
    ap.add_argument(
        "--run-dir",
        required=True,
        help="Hard-negative run directory",
    )
    ap.add_argument(
        "--output",
        default="datasets/hard_negative_addon_v1",
        help="Output directory",
    )
    ap.add_argument(
        "--copy-mode",
        choices=("copy", "link"),
        default="copy",
        help="copy=copy image files, link=hard-link if possible",
    )
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    output = Path(args.output).resolve()

    if not run_dir.exists():
        raise SystemExit(f"❌ ไม่พบ run directory: {run_dir}")

    try:
        records, source_name = load_records(run_dir)
    except Exception as e:
        raise SystemExit(f"❌ โหลด review records ไม่สำเร็จ: {e}")

    reviewed = [
        r for r in records
        if r.get("review_label") == "true_negative"
    ]

    actual_fire = [
        r for r in records
        if r.get("review_label") == "actual_fire"
    ]
    actual_smoke = [
        r for r in records
        if r.get("review_label") == "actual_smoke"
    ]
    discarded = [
        r for r in records
        if r.get("review_label") == "discard"
    ]
    unreviewed = [
        r for r in records
        if not r.get("review_label")
    ]

    image_dir = output / "images" / "train"
    image_dir.mkdir(parents=True, exist_ok=True)

    # Background images intentionally have no corresponding YOLO txt label.
    label_dir = output / "labels" / "train"
    label_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    hashes = {}
    copied = 0
    missing = 0
    exact_duplicates = 0

    by_prediction = {
        "fire": 0,
        "smoke": 0,
        "other": 0,
    }

    for record in reviewed:
        src = resolve_source_image(run_dir, record)

        if src is None:
            missing += 1
            print(
                f"⚠️ event={record.get('event_id')} "
                "ไม่พบไฟล์ภาพ"
            )
            continue

        try:
            digest = sha1_file(src)
        except OSError as e:
            missing += 1
            print(f"⚠️ อ่านภาพไม่ได้: {src} | {e}")
            continue

        if digest in hashes:
            exact_duplicates += 1
            print(
                f"↪ skip exact duplicate: {src.name} "
                f"== {hashes[digest]}"
            )
            continue

        hashes[digest] = src.name

        dst_name = unique_name(record, src)
        dst = image_dir / dst_name

        if args.copy_mode == "link":
            try:
                if dst.exists():
                    dst.unlink()
                dst.hardlink_to(src)
            except OSError:
                shutil.copy2(src, dst)
        else:
            shutil.copy2(src, dst)

        pred = str(
            record.get("class")
            or record.get("prediction")
            or "other"
        ).lower()

        if pred not in by_prediction:
            pred = "other"

        by_prediction[pred] += 1
        copied += 1

        manifest_rows.append(
            {
                "event_id": record.get("event_id"),
                "review_label": "true_negative",
                "model_prediction": (
                    record.get("class")
                    or record.get("prediction")
                ),
                "confidence": record.get("confidence"),
                "source_image": str(src),
                "dataset_image": str(
                    dst.relative_to(output)
                ),
                "sha1": digest,
                "bbox_false_positive": json.dumps(
                    record.get("bbox")
                ),
            }
        )

    manifest_csv = output / "hard_negative_manifest.csv"
    with manifest_csv.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        fields = [
            "event_id",
            "review_label",
            "model_prediction",
            "confidence",
            "source_image",
            "dataset_image",
            "sha1",
            "bbox_false_positive",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary = {
        "source_run": str(run_dir),
        "review_source": source_name,
        "records_total": len(records),
        "review_counts": {
            "true_negative": len(reviewed),
            "actual_fire": len(actual_fire),
            "actual_smoke": len(actual_smoke),
            "discard": len(discarded),
            "unreviewed": len(unreviewed),
        },
        "copied_true_negative_images": copied,
        "missing_images": missing,
        "exact_duplicates_skipped": exact_duplicates,
        "copied_by_original_prediction": by_prediction,
        "split": "train",
        "note": (
            "This add-on intentionally contains background images only. "
            "No YOLO object label file is created for true-negative images."
        ),
    }

    summary_path = output / "summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    readme = output / "README.txt"
    readme.write_text(
        "\n".join(
            [
                "Smart Fire Detection v2 - Hard Negative Add-on",
                "",
                "Purpose:",
                "  Reviewed background images that the current model",
                "  incorrectly or suspiciously predicted as Fire/Smoke.",
                "",
                "Structure:",
                "  images/train/   reviewed true-negative full frames",
                "  labels/train/   intentionally empty directory",
                "",
                "IMPORTANT:",
                "  Do not train this add-on by itself.",
                "  Merge it with the existing Fire/Smoke positive dataset.",
                "  Keep this same-scene capture in TRAIN only to avoid",
                "  train/validation leakage.",
                "",
                f"Source run: {run_dir}",
            ]
        ),
        encoding="utf-8",
    )

    print("=" * 76)
    print("Hard Negative Add-on Prepared")
    print("=" * 76)
    print(f"Review records       : {len(records)}")
    print(f"True negatives       : {len(reviewed)}")
    print(f"Actual fire          : {len(actual_fire)}")
    print(f"Actual smoke         : {len(actual_smoke)}")
    print(f"Discard              : {len(discarded)}")
    print(f"Unreviewed           : {len(unreviewed)}")
    print("")
    print(f"Images copied        : {copied}")
    print(f"Exact dup skipped    : {exact_duplicates}")
    print(f"Missing images       : {missing}")
    print(f"Originally Fire pred : {by_prediction['fire']}")
    print(f"Originally Smoke pred: {by_prediction['smoke']}")
    print("")
    print(f"Output               : {output}")
    print(f"Manifest             : {manifest_csv}")
    print(f"Summary              : {summary_path}")
    print("")
    print("✅ Hard-negative add-on ready for Dataset v2 merge")
    print("=" * 76)


if __name__ == "__main__":
    main()