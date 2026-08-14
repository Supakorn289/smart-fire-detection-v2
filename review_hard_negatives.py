#!/usr/bin/env python3
r"""
Local review UI for hard-negative candidates.

Usage:
    python review_hard_negatives.py --run-dir static\hard_negative_runs\preset4_false_positive_YYYYMMDD_HHMMSS

Then open:
    http://127.0.0.1:5055

Review labels:
    true_negative  -> confirmed non-fire/non-smoke hard negative
    actual_fire    -> actually contains fire
    actual_smoke   -> actually contains smoke
    discard        -> unusable/duplicate/ambiguous
"""

import argparse
import csv
import json
import mimetypes
import os
import shutil
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file


HTML = r"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hard Negative Review</title>
<style>
:root {
  color-scheme: dark;
  --bg:#0f1115;
  --panel:#171a21;
  --border:#2b303b;
  --muted:#9aa4b2;
  --good:#3ddc97;
  --warn:#ffcc66;
  --danger:#ff6b6b;
  --blue:#65a9ff;
}
* { box-sizing:border-box; }
body {
  margin:0;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  background:var(--bg);
  color:#f2f4f8;
}
header {
  padding:14px 18px;
  border-bottom:1px solid var(--border);
  background:#12151b;
  position:sticky;
  top:0;
  z-index:2;
}
h1 { margin:0 0 5px; font-size:20px; }
.small { color:var(--muted); font-size:13px; }
main {
  display:grid;
  grid-template-columns:minmax(0,1fr) 330px;
  min-height:calc(100vh - 72px);
}
.viewer {
  padding:16px;
  min-width:0;
}
.image-wrap {
  min-height:65vh;
  display:flex;
  align-items:center;
  justify-content:center;
  background:#080a0d;
  border:1px solid var(--border);
  border-radius:10px;
  overflow:hidden;
}
.image-wrap img {
  max-width:100%;
  max-height:76vh;
  object-fit:contain;
}
.thumb-row {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:10px;
  margin-top:10px;
}
.thumb {
  background:#080a0d;
  border:1px solid var(--border);
  border-radius:8px;
  overflow:hidden;
  min-height:130px;
  display:flex;
  align-items:center;
  justify-content:center;
}
.thumb img {
  max-width:100%;
  max-height:240px;
  object-fit:contain;
}
aside {
  border-left:1px solid var(--border);
  background:var(--panel);
  padding:16px;
}
.meta {
  font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
  font-size:13px;
  line-height:1.55;
  background:#101319;
  border:1px solid var(--border);
  border-radius:8px;
  padding:12px;
  white-space:pre-wrap;
  margin-bottom:14px;
}
button {
  width:100%;
  border:0;
  border-radius:8px;
  padding:12px 10px;
  margin:5px 0;
  font-size:15px;
  font-weight:700;
  cursor:pointer;
}
.neg { background:var(--good); color:#07150f; }
.fire { background:#ff7448; color:#1c0802; }
.smoke { background:#b6c4d8; color:#101720; }
.discard { background:#4a5260; color:#fff; }
.nav {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:8px;
  margin-top:12px;
}
.nav button {
  background:#272d38;
  color:#fff;
}
.progress {
  height:8px;
  background:#242a33;
  border-radius:999px;
  overflow:hidden;
  margin:10px 0 14px;
}
.progress > div {
  height:100%;
  background:var(--blue);
}
kbd {
  padding:2px 6px;
  border-radius:4px;
  background:#303744;
  border:1px solid #46505f;
  font-size:12px;
}
.stats {
  margin-top:14px;
  color:var(--muted);
  font-size:13px;
  line-height:1.6;
}
@media (max-width:900px) {
  main { grid-template-columns:1fr; }
  aside { border-left:0; border-top:1px solid var(--border); }
}
</style>
</head>
<body>
<header>
  <h1>Smart Fire Detection v2 — Candidate Review</h1>
  <div id="runinfo" class="small">Loading...</div>
</header>

<main>
<section class="viewer">
  <div class="image-wrap">
    <img id="annotated" alt="annotated candidate">
  </div>
  <div class="thumb-row">
    <div class="thumb"><img id="crop" alt="crop"></div>
    <div class="thumb"><img id="full" alt="full frame"></div>
  </div>
</section>

<aside>
  <div id="counter"></div>
  <div class="progress"><div id="bar"></div></div>
  <div id="meta" class="meta"></div>

  <button class="neg" onclick="review('true_negative')">
    N — TRUE NEGATIVE
  </button>
  <button class="fire" onclick="review('actual_fire')">
    F — ACTUAL FIRE
  </button>
  <button class="smoke" onclick="review('actual_smoke')">
    S — ACTUAL SMOKE
  </button>
  <button class="discard" onclick="review('discard')">
    X — DISCARD
  </button>

  <div class="nav">
    <button onclick="move(-1)">← Previous</button>
    <button onclick="move(1)">Next →</button>
  </div>

  <div class="stats" id="stats"></div>
  <div class="stats">
    Keyboard:
    <kbd>N</kbd> negative,
    <kbd>F</kbd> fire,
    <kbd>S</kbd> smoke,
    <kbd>X</kbd> discard,
    <kbd>←</kbd>/<kbd>→</kbd> navigate
  </div>
</aside>
</main>

<script>
let data = [];
let index = 0;
let summary = {};

async function load() {
  const r = await fetch('/api/candidates');
  const payload = await r.json();
  data = payload.candidates;
  summary = payload.summary || {};
  document.getElementById('runinfo').textContent =
    `${payload.run_dir} | ${data.length} candidates`;
  index = Math.max(0, data.findIndex(x => !x.review_label));
  if (index < 0) index = 0;
  render();
}

function imgUrl(path) {
  if (!path) return '';
  return '/image?path=' + encodeURIComponent(path);
}

function render() {
  if (!data.length) {
    document.getElementById('counter').textContent = 'No candidates';
    return;
  }

  const c = data[index];
  document.getElementById('annotated').src = imgUrl(c.annotated_image);
  document.getElementById('crop').src = imgUrl(c.crop_image);
  document.getElementById('full').src = imgUrl(c.full_image);

  document.getElementById('counter').textContent =
    `Candidate ${index + 1} / ${data.length}`;

  const reviewed = data.filter(x => x.review_label).length;
  document.getElementById('bar').style.width =
    `${(reviewed / data.length) * 100}%`;

  document.getElementById('meta').textContent =
`event_id: ${c.event_id}
prediction: ${c.class}
confidence: ${Number(c.confidence).toFixed(3)}
production pass: ${c.production_pass}
preset: ${c.preset}
sample: ${c.sample_no}
bbox: ${JSON.stringify(c.bbox)}
current review: ${c.review_label ?? 'UNREVIEWED'}`;

  const counts = {};
  for (const x of data) {
    const k = x.review_label || 'unreviewed';
    counts[k] = (counts[k] || 0) + 1;
  }

  document.getElementById('stats').innerHTML =
    `Reviewed: ${reviewed}/${data.length}<br>` +
    `True negative: ${counts.true_negative || 0}<br>` +
    `Actual fire: ${counts.actual_fire || 0}<br>` +
    `Actual smoke: ${counts.actual_smoke || 0}<br>` +
    `Discard: ${counts.discard || 0}`;
}

async function review(label) {
  const c = data[index];

  const r = await fetch('/api/review', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({event_id:c.event_id, review_label:label})
  });

  if (!r.ok) {
    alert('Save failed');
    return;
  }

  c.review_label = label;

  if (index < data.length - 1) index++;
  render();
}

function move(delta) {
  index = Math.max(0, Math.min(data.length - 1, index + delta));
  render();
}

document.addEventListener('keydown', e => {
  if (e.key === 'n' || e.key === 'N') review('true_negative');
  if (e.key === 'f' || e.key === 'F') review('actual_fire');
  if (e.key === 's' || e.key === 'S') review('actual_smoke');
  if (e.key === 'x' || e.key === 'X') review('discard');
  if (e.key === 'ArrowLeft') move(-1);
  if (e.key === 'ArrowRight') move(1);
});

load();
</script>
</body>
</html>
"""


def load_jsonl(path: Path):
    records = []

    if not path.exists():
        raise FileNotFoundError(path)

    for raw in path.read_text(
        encoding="utf-8",
    ).splitlines():
        raw = raw.strip()

        if not raw:
            continue

        records.append(
            json.loads(raw)
        )

    return records


def save_jsonl(path: Path, records):
    temp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temp.open(
        "w",
        encoding="utf-8",
    ) as f:
        for item in records:
            f.write(
                json.dumps(
                    item,
                    ensure_ascii=False,
                )
                + "\n"
            )

    os.replace(
        temp,
        path,
    )


def save_csv(path: Path, records):
    if not records:
        path.write_text(
            "",
            encoding="utf-8",
        )
        return

    fields = [
        "event_id",
        "timestamp_local",
        "scene_label",
        "preset",
        "center_bearing_deg",
        "sample_no",
        "frame_seq",
        "frame_age_ms",
        "inference_ms",
        "class",
        "model_class",
        "confidence",
        "production_threshold",
        "production_pass",
        "bbox",
        "full_image",
        "crop_image",
        "annotated_image",
        "review_label",
        "review_notes",
    ]

    temp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temp.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )
        writer.writeheader()

        for item in records:
            row = {
                k: item.get(k, "")
                for k in fields
            }
            row["bbox"] = json.dumps(
                item.get("bbox")
            )
            writer.writerow(row)

    os.replace(
        temp,
        path,
    )


def export_reviewed_dataset(
    run_dir: Path,
    records,
):
    """
    Create a review export only.
    This does not generate YOLO labels automatically because true negatives
    intentionally contain no Fire/Smoke annotations.
    """
    export_dir = (
        run_dir
        / "review_export"
    )

    true_negative_dir = (
        export_dir
        / "true_negative"
    )
    actual_fire_dir = (
        export_dir
        / "actual_fire"
    )
    actual_smoke_dir = (
        export_dir
        / "actual_smoke"
    )

    for folder in (
        true_negative_dir,
        actual_fire_dir,
        actual_smoke_dir,
    ):
        folder.mkdir(
            parents=True,
            exist_ok=True,
        )

    manifest = []

    for item in records:
        label = item.get(
            "review_label"
        )

        if label not in {
            "true_negative",
            "actual_fire",
            "actual_smoke",
        }:
            continue

        src_rel = item.get(
            "full_image"
        )

        if not src_rel:
            continue

        src = (
            run_dir
            / Path(src_rel)
        )

        if not src.exists():
            continue

        if label == "true_negative":
            dst_dir = true_negative_dir
        elif label == "actual_fire":
            dst_dir = actual_fire_dir
        else:
            dst_dir = actual_smoke_dir

        dst = (
            dst_dir
            / src.name
        )

        shutil.copy2(
            src,
            dst,
        )

        manifest.append(
            {
                "event_id": item.get(
                    "event_id"
                ),
                "review_label": label,
                "source": str(src_rel),
                "exported_image": str(
                    dst.relative_to(
                        export_dir
                    )
                ),
                "prediction": item.get(
                    "class"
                ),
                "confidence": item.get(
                    "confidence"
                ),
                "bbox": item.get(
                    "bbox"
                ),
            }
        )

    manifest_path = (
        export_dir
        / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return export_dir


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Review hard-negative candidates "
            "with a local Flask web UI."
        )
    )

    ap.add_argument(
        "--run-dir",
        required=True,
        help=(
            "Path to one hard_negative_runs/"
            "<run> directory"
        ),
    )

    ap.add_argument(
        "--host",
        default="127.0.0.1",
    )

    ap.add_argument(
        "--port",
        type=int,
        default=5055,
    )

    ap.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open browser automatically",
    )

    args = ap.parse_args()

    run_dir = Path(
        args.run_dir
    ).resolve()

    if not run_dir.exists():
        raise SystemExit(
            f"❌ ไม่พบ run directory: {run_dir}"
        )

    jsonl_path = (
        run_dir
        / "candidates.jsonl"
    )

    csv_path = (
        run_dir
        / "candidates.csv"
    )

    summary_path = (
        run_dir
        / "summary.json"
    )

    try:
        records = load_jsonl(
            jsonl_path
        )
    except Exception as e:
        raise SystemExit(
            f"❌ โหลด candidates ไม่สำเร็จ: {e}"
        )

    summary = {}

    if summary_path.exists():
        try:
            summary = json.loads(
                summary_path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            summary = {}

    lock = threading.Lock()

    app = Flask(
        __name__
    )

    @app.get("/")
    def index():
        return HTML

    @app.get("/api/candidates")
    def api_candidates():
        with lock:
            return jsonify(
                {
                    "run_dir": str(
                        run_dir
                    ),
                    "summary": summary,
                    "candidates": records,
                }
            )

    @app.get("/image")
    def image():
        rel = request.args.get(
            "path",
            "",
        )

        if not rel:
            return (
                "missing path",
                400,
            )

        candidate_path = (
            run_dir
            / Path(rel)
        ).resolve()

        # Prevent directory traversal.
        try:
            candidate_path.relative_to(
                run_dir
            )
        except ValueError:
            return (
                "invalid path",
                403,
            )

        if not candidate_path.exists():
            return (
                "not found",
                404,
            )

        return send_file(
            candidate_path
        )

    @app.post("/api/review")
    def api_review():
        payload = request.get_json(
            silent=True
        ) or {}

        event_id = payload.get(
            "event_id"
        )
        label = payload.get(
            "review_label"
        )

        valid_labels = {
            "true_negative",
            "actual_fire",
            "actual_smoke",
            "discard",
        }

        if label not in valid_labels:
            return jsonify(
                {
                    "ok": False,
                    "error": "invalid label",
                }
            ), 400

        with lock:
            target = next(
                (
                    item
                    for item in records
                    if item.get("event_id")
                    == event_id
                ),
                None,
            )

            if target is None:
                return jsonify(
                    {
                        "ok": False,
                        "error": "event not found",
                    }
                ), 404

            target[
                "review_label"
            ] = label

            save_jsonl(
                jsonl_path,
                records,
            )

            save_csv(
                csv_path,
                records,
            )

            export_dir = (
                export_reviewed_dataset(
                    run_dir,
                    records,
                )
            )

        return jsonify(
            {
                "ok": True,
                "event_id": event_id,
                "review_label": label,
                "export_dir": str(
                    export_dir
                ),
            }
        )

    url = (
        f"http://{args.host}:"
        f"{args.port}"
    )

    print("=" * 76)
    print(
        "Smart Fire Detection v2 - Hard Negative Review"
    )
    print(f"Run dir    : {run_dir}")
    print(
        f"Candidates : {len(records)}"
    )
    print(f"URL        : {url}")
    print("")
    print(
        "Labels:"
    )
    print(
        "  N = TRUE NEGATIVE "
        "(ไม่มี Fire/Smoke จริง)"
    )
    print(
        "  F = ACTUAL FIRE"
    )
    print(
        "  S = ACTUAL SMOKE"
    )
    print(
        "  X = DISCARD"
    )
    print("")
    print(
        "ผล review จะถูกเขียนกลับ candidates.jsonl/csv"
    )
    print(
        "และคัดลอกภาพไป review_export/"
    )
    print("=" * 76)

    if not args.no_browser:
        timer = threading.Timer(
            1.0,
            lambda: webbrowser.open(
                url
            ),
        )
        timer.daemon = True
        timer.start()

    app.run(
        host=args.host,
        port=args.port,
        debug=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()