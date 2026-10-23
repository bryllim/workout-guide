#!/usr/bin/env python3
"""
Create a looping exercise GIF/WebP from three PNG poses using RifeMetal.

Expected repository layout:
    project-root/
      assets/
        bench_press/
          frame1.png
          frame2.png
          frame3.png
        squat/
          frame1.png
          frame2.png
          frame3.png

Pose order is frame1 -> frame2 -> frame3, then reversed for a ping-pong loop.
RifeMetal generates in-between frames for each adjacent pair.

Install dependencies:
    python3 -m pip install pillow numpy opencv-python

Example:
    python3 scripts/exercise_pose_interpolator.py \
      --root . \
      --exercise bench_press \
      --output ./generated/bench_press \
      --rife ~/Downloads/rife-metal-macos-arm64/bin/rife-metal \
      --model ~/Downloads/rife-metal-macos-arm64/share/rife-metal/rife-v4.25.rmw \
      --steps 5 --fps 10

RifeMetal CLI:
    rife-metal -0 a.png -1 b.png --output prefix.png --model model.rmw \
      --timesteps 0.1667,0.3333,0.5,0.6667,0.8333
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


POSE_NAMES = ("frame-1.png", "frame-2.png", "frame-3.png")


def blacken_flat_edge_background(image: Image.Image, tolerance: int) -> Image.Image:
    """Turn a flat, edge-connected background black and composite transparency on black."""
    rgba = np.asarray(image.convert("RGBA")).copy()
    rgb = rgba[:, :, :3].astype(np.int16)
    h, w = rgb.shape[:2]
    corners = np.array(
        [rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]],
        dtype=np.float32,
    )
    bg = np.median(corners, axis=0)
    distance = np.max(np.abs(rgb - bg), axis=2)
    candidate = (distance <= tolerance).astype(np.uint8)

    count, labels = cv2.connectedComponents(candidate, connectivity=8)
    if count > 1:
        border_labels = np.unique(
            np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])
        )
        mask = np.isin(labels, border_labels) & (candidate == 1)
        rgba[mask, :3] = 0
        rgba[mask, 3] = 255

    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    out = rgba[:, :, :3].astype(np.float32) * alpha
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def load_pose(path: Path, size: tuple[int, int] | None, tolerance: int) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if size and image.size != size:
        image.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size, (0, 0, 0, 255))
        canvas.alpha_composite(
            image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2)
        )
        image = canvas
    # Preserve the source artwork; only composite transparency onto black.
    background = Image.new("RGBA", image.size, (0, 0, 0, 255))
    background.alpha_composite(image)
    return background.convert("RGB")

def interpolate_pair(
    executable: Path,
    model: Path,
    first: Path,
    second: Path,
    output_prefix: Path,
    timesteps: list[float],
) -> list[Path]:
    timestep_arg = ",".join(f"{t:.4f}".rstrip("0").rstrip(".") for t in timesteps)
    command = [
        str(executable), "-0", str(first), "-1", str(second),
        "--output", str(output_prefix), "--model", str(model),
        "--timesteps", timestep_arg,
    ]
    print(f"Interpolating {first.name} -> {second.name}")
    subprocess.run(command, check=True)

    # Match numeric timestamps because RifeMetal may round their filenames.
    pattern = re.compile(
        re.escape(output_prefix.stem) + r"_t([0-9.]+)" +
        re.escape(output_prefix.suffix) + r"$"
    )
    found: list[tuple[float, Path]] = []
    for path in output_prefix.parent.glob(output_prefix.stem + "_t*.png"):
        match = pattern.match(path.name)
        if match:
            found.append((float(match.group(1)), path))
    found.sort(key=lambda item: item[0])

    if len(found) != len(timesteps):
        names = ", ".join(path.name for _, path in found)
        raise RuntimeError(
            f"Expected {len(timesteps)} interpolated frames, found {len(found)}. "
            f"Matched files: {names}"
        )
    return [path for _, path in found]


def export_animation(
    frames: list[Image.Image], output: Path, fps: int, write_gif: bool
) -> None:
    if not frames:
        raise ValueError("No frames were generated.")

    output.parent.mkdir(parents=True, exist_ok=True)
    duration = max(20, round(1000 / fps))

    # Normalize frame dimensions and remove fully black frames.
    size = frames[0].size
    rgb_frames = []

    for frame in frames:
        frame = frame.convert("RGB")
        if frame.size != size:
            frame = frame.resize(size, Image.Resampling.LANCZOS)

        # Skip entirely black frames that cause blank flashes.
        if frame.getbbox() is None:
            print("Skipping completely black frame")
            continue

        rgb_frames.append(frame)

    if not rgb_frames:
        raise ValueError("All animation frames are blank.")

    # Ensure the first and last frames are visible.
    if rgb_frames[-1].tobytes() != rgb_frames[0].tobytes():
        rgb_frames.append(rgb_frames[0].copy())

    webp = output.with_suffix(".webp")
    rgb_frames[0].save(
        webp,
        format="WEBP",
        save_all=True,
        append_images=rgb_frames[1:],
        duration=duration,
        loop=0,
        lossless=True,
        method=6,
    )
    print(f"Saved animated WebP: {webp}")

    if write_gif:
        gif = output.with_suffix(".gif")

        # Create one palette for all frames.
        sample = Image.new("RGB", (size[0], size[1] * len(rgb_frames)))
        for i, frame in enumerate(rgb_frames):
            sample.paste(frame, (0, i * size[1]))

        palette_source = sample.quantize(
            colors=256, method=Image.Quantize.MEDIANCUT
        )
        palette_image = Image.new("P", (1, 1))
        palette_image.putpalette(palette_source.getpalette())

        palette_frames = [
            frame.quantize(
                palette=palette_image,
                dither=Image.Dither.NONE,
            )
            for frame in rgb_frames
        ]

        palette_frames[0].save(
            gif,
            format="GIF",
            save_all=True,
            append_images=palette_frames[1:],
            duration=duration,
            loop=0,
            optimize=False,
            disposal=1,
        )
        print(f"Saved animated GIF: {gif}")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path("."),
        help="Project root containing assets/<exercise-name>/ (default: current directory)",
    )
    parser.add_argument(
        "--exercise", required=True,
        help="Exercise directory name inside <root>/assets/, e.g. bench_press",
    )
    parser.add_argument(
        "--output", type=Path, required=True,
        help="Output filename without extension",
    )
    parser.add_argument("--rife", type=Path, required=True, help="Path to RifeMetal executable")
    parser.add_argument("--model", type=Path, required=True, help="Path to the .rmw model file")
    parser.add_argument("--steps", type=int, default=5, help="In-between frames per pose pair")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--bg-tolerance", type=int, default=35)
    parser.add_argument("--no-gif", action="store_true", help="Export animated WebP only")
    args = parser.parse_args()

    if args.steps < 1:
        parser.error("--steps must be at least 1")
    if args.fps < 1:
        parser.error("--fps must be at least 1")

    root = args.root.expanduser().resolve()
    exercise_dir = root / "assets" / args.exercise
    pose_paths = [exercise_dir / name for name in POSE_NAMES]

    if not root.is_dir():
        parser.error(f"Project root not found: {root}")
    if not exercise_dir.is_dir():
        parser.error(f"Exercise asset directory not found: {exercise_dir}")
    if not args.rife.expanduser().is_file():
        parser.error(f"RifeMetal executable not found: {args.rife}")
    if not args.model.expanduser().is_file():
        parser.error(f"Model file not found: {args.model}")

    missing = [str(path) for path in pose_paths if not path.is_file()]
    if missing:
        parser.error("Missing pose file(s): " + ", ".join(missing))

    args.rife = args.rife.expanduser().resolve()
    args.model = args.model.expanduser().resolve()
    output = args.output.expanduser()
    if not output.is_absolute():
        output = (Path.cwd() / output).resolve()

    with Image.open(pose_paths[0]) as first:
        size = first.size
    poses = [load_pose(path, size, args.bg_tolerance) for path in pose_paths]
    timesteps = [i / (args.steps + 1) for i in range(1, args.steps + 1)]

    with tempfile.TemporaryDirectory(prefix="rife_metal_") as temp:
        temp_dir = Path(temp)
        normalized_paths: list[Path] = []
        for index, pose in enumerate(poses, start=1):
            path = temp_dir / f"pose_{index}.png"
            pose.save(path)
            normalized_paths.append(path)

        forward: list[Image.Image] = [poses[0]]
        for pair_index in range(2):
            prefix = temp_dir / f"pair_{pair_index}.png"
            interpolated_paths = interpolate_pair(
                args.rife, args.model,
                normalized_paths[pair_index],
                normalized_paths[pair_index + 1],
                prefix, timesteps,
            )
            for frame_path in interpolated_paths:
                with Image.open(frame_path) as frame:
                    forward.append(
                        blacken_flat_edge_background(frame.convert("RGBA"), args.bg_tolerance)
                    )
            forward.append(poses[pair_index + 1])
 
        # Ping-pong loop: forward, then reverse without duplicating endpoints.
    loop_frames = forward + forward[-2:0:-1]

    # Remove consecutive identical frames only.
    deduplicated = []
    for frame in loop_frames:
        if not deduplicated or frame.tobytes() != deduplicated[-1].tobytes():
            deduplicated.append(frame)

    export_animation(deduplicated, output, args.fps, not args.no_gif)



if __name__ == "__main__":
    main()
