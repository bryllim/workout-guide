#!/usr/bin/env python3
"""
Batch-generate looping exercise animations from one folder per exercise.

Expected layout:
  exercise-poses/
    bench_press/03.png  # bottom
    exercise-poses/bench_press/02.png  # middle
    exercise-poses/bench_press/01.png  # top
    squat/03.png
    squat/02.png
    squat/01.png

Example:
  python3 batch_exercise_animations.py \
    --root ./exercise-poses \
    --output ./output \
    --rife ~/Downloads/rife-metal-macos-arm64/bin/rife-metal \
    --model ~/Downloads/rife-metal-macos-arm64/share/rife-metal/rife-v4.25.rmw

Each exercise folder is processed independently. Existing outputs are skipped by
default. Failures are recorded in output/batch_failures.csv.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="Root folder containing one exercise folder per exercise")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output root folder")
    parser.add_argument("--rife", type=Path, required=True,
                        help="Path to the RifeMetal executable")
    parser.add_argument("--model", type=Path, required=True,
                        help="Path to the RifeMetal .rmw model")
    parser.add_argument("--script", type=Path,
                        default=Path(__file__).with_name("exercise_pose_interpolator.py"),
                        help="Path to exercise_pose_interpolator.py")
    parser.add_argument("--order", nargs=3, default=["03.png", "02.png", "01.png"],
                        metavar=("BOTTOM", "MIDDLE", "TOP"))
    parser.add_argument("--steps", type=int, default=5)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--bg-tolerance", type=int, default=35)
    parser.add_argument("--force", action="store_true",
                        help="Regenerate outputs even if they already exist")
    parser.add_argument("--webp-only", action="store_true",
                        help="Do not generate GIFs")
    args = parser.parse_args()

    if not args.root.is_dir():
        parser.error(f"Input root is not a directory: {args.root}")
    if not args.rife.is_file():
        parser.error(f"RifeMetal executable not found: {args.rife}")
    if not args.model.is_file():
        parser.error(f"RifeMetal model not found: {args.model}")
    if not args.script.is_file():
        parser.error(f"Interpolator script not found: {args.script}")
    if args.steps < 1 or args.fps < 1:
        parser.error("--steps and --fps must be positive")

    exercise_dirs = sorted(p for p in args.root.iterdir() if p.is_dir())
    if not exercise_dirs:
        print(f"No exercise subdirectories found in {args.root}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    failures_path = args.output / "batch_failures.csv"
    failures: list[tuple[str, str]] = []
    succeeded = 0
    skipped = 0

    for index, exercise_dir in enumerate(exercise_dirs, start=1):
        name = exercise_dir.name
        output_stem = args.output / name / name
        webp_path = output_stem.with_suffix(".webp")
        gif_path = output_stem.with_suffix(".gif")

        missing = [filename for filename in args.order
                   if not (exercise_dir / filename).is_file()]
        if missing:
            message = f"missing pose file(s): {', '.join(missing)}"
            failures.append((name, message))
            print(f"[{index}/{len(exercise_dirs)}] FAIL {name}: {message}")
            continue

        if not args.force and webp_path.is_file() and (
            args.webp_only or gif_path.is_file()
        ):
            skipped += 1
            print(f"[{index}/{len(exercise_dirs)}] SKIP {name}: output exists")
            continue

        command = [
            sys.executable, str(args.script),
            "--input", str(exercise_dir),
            "--output", str(output_stem),
            "--rife", str(args.rife),
            "--model", str(args.model),
            "--order", *args.order,
            "--steps", str(args.steps),
            "--fps", str(args.fps),
            "--bg-tolerance", str(args.bg_tolerance),
        ]
        if args.webp_only:
            command.append("--no-gif")

        print(f"\n[{index}/{len(exercise_dirs)}] START {name}")
        try:
            subprocess.run(command, check=True)
            succeeded += 1
            print(f"[{index}/{len(exercise_dirs)}] DONE {name}")
        except subprocess.CalledProcessError as exc:
            failures.append((name, f"interpolator exited with status {exc.returncode}"))
            print(f"[{index}/{len(exercise_dirs)}] FAIL {name}: exit {exc.returncode}")

    with failures_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["exercise", "error"])
        writer.writerows(failures)

    print("\nBatch summary")
    print(f"  succeeded: {succeeded}")
    print(f"  skipped:   {skipped}")
    print(f"  failed:    {len(failures)}")
    print(f"  log:       {failures_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
