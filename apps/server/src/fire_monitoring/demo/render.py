from __future__ import annotations

import numpy as np

from .geometry import DEPTH_M, HEIGHT_M, IMAGE_H, IMAGE_W, WIDTH_M, VirtualCamera

DESKS = (
    (np.array([3.35, 2.35, 0.0]), np.array([4.65, 3.05, 0.76])),
    (np.array([5.15, 2.35, 0.0]), np.array([6.45, 3.05, 0.76])),
    (np.array([3.35, 3.85, 0.0]), np.array([4.65, 4.55, 0.76])),
    (np.array([5.15, 3.85, 0.0]), np.array([6.45, 4.55, 0.76])),
)
CABINET = (np.array([6.20, 2.45, 0.0]), np.array([6.75, 3.65, 1.90]))
BOARD = (np.array([2.4, 5.92, 1.05]), np.array([5.6, 6.0, 2.15]))


def _rays(camera: VirtualCamera) -> np.ndarray:
    us = np.arange(IMAGE_W, dtype=float) + 0.5
    vs = np.arange(IMAGE_H, dtype=float) + 0.5
    uu, vv = np.meshgrid(us, vs)
    x = (uu - camera.intrinsics[0, 2]) / camera.intrinsics[0, 0]
    y = (vv - camera.intrinsics[1, 2]) / camera.intrinsics[1, 1]
    dirs = np.stack([x, y, np.ones_like(x)], axis=-1)
    dirs /= np.linalg.norm(dirs, axis=-1, keepdims=True)
    return dirs @ camera.rotation.T


def _paint(color: np.ndarray, depth: np.ndarray, hit: np.ndarray, distance: np.ndarray, shade: np.ndarray) -> None:
    closer = hit & (distance < depth)
    depth[closer] = distance[closer]
    color[closer] = shade[closer]


def _plane(eye: np.ndarray, dirs: np.ndarray, axis: int, value: float) -> tuple[np.ndarray, np.ndarray]:
    denom = dirs[..., axis]
    distance = np.full(dirs.shape[:2], np.inf)
    valid = np.abs(denom) > 1e-6
    distance[valid] = (value - eye[axis]) / denom[valid]
    return distance > 0.05, distance


def _aabb(eye: np.ndarray, dirs: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    safe = np.where(np.abs(dirs) < 1e-8, np.sign(dirs) * 1e-8 + 1e-8, dirs)
    inv = 1.0 / safe
    t0 = (lo - eye) * inv
    t1 = (hi - eye) * inv
    near = np.max(np.minimum(t0, t1), axis=-1)
    far = np.min(np.maximum(t0, t1), axis=-1)
    return (far >= near) & (near > 0.02), near


def static_scene(camera: VirtualCamera) -> tuple[np.ndarray, np.ndarray]:
    dirs = _rays(camera)
    eye = camera.eye
    color = np.zeros((IMAGE_H, IMAGE_W, 3), dtype=np.float32)
    depth = np.full((IMAGE_H, IMAGE_W), np.inf, dtype=np.float32)
    sky = np.zeros_like(color)
    sky[..., 0] = 214
    sky[..., 1] = 206
    sky[..., 2] = 196
    color[:] = sky

    hit, distance = _plane(eye, dirs, 2, 0.0)
    point = eye + distance[..., None] * dirs
    inside = hit & (point[..., 0] >= 0) & (point[..., 0] <= WIDTH_M) & (point[..., 1] >= 0) & (point[..., 1] <= DEPTH_M)
    tile = (np.floor(point[..., 0] * 2) + np.floor(point[..., 1] * 2)) % 2
    shade = np.empty_like(color)
    base = 168 - tile * 10
    shade[..., 0] = base
    shade[..., 1] = base - 4
    shade[..., 2] = base - 12
    _paint(color, depth, inside, distance, shade)

    walls = (
        (0, 0.0, (214, 206, 196)),
        (0, WIDTH_M, (206, 198, 188)),
        (1, 0.0, (220, 214, 204)),
        (1, DEPTH_M, (198, 192, 182)),
    )
    for axis, value, tone in walls:
        hit, distance = _plane(eye, dirs, axis, value)
        point = eye + distance[..., None] * dirs
        span = (
            (point[..., 1] >= 0)
            & (point[..., 1] <= DEPTH_M)
            & (point[..., 2] >= 0)
            & (point[..., 2] <= HEIGHT_M)
            if axis == 0
            else (point[..., 0] >= 0)
            & (point[..., 0] <= WIDTH_M)
            & (point[..., 2] >= 0)
            & (point[..., 2] <= HEIGHT_M)
        )
        shade = np.empty_like(color)
        shade[..., 0] = tone[2]
        shade[..., 1] = tone[1]
        shade[..., 2] = tone[0]
        _paint(color, depth, hit & span & (distance < 40), distance, shade)

    ceiling_hit, ceiling_t = _plane(eye, dirs, 2, HEIGHT_M)
    point = eye + ceiling_t[..., None] * dirs
    inside = (
        ceiling_hit
        & (point[..., 0] >= 0)
        & (point[..., 0] <= WIDTH_M)
        & (point[..., 1] >= 0)
        & (point[..., 1] <= DEPTH_M)
    )
    shade = np.empty_like(color)
    shade[..., 0] = 228
    shade[..., 1] = 224
    shade[..., 2] = 216
    _paint(color, depth, inside, ceiling_t, shade)

    boxes = (
        *(((lo, hi), (92, 112, 142)) for lo, hi in DESKS),
        (CABINET, (58, 64, 72)),
        (BOARD, (48, 62, 56)),
    )
    for (lo, hi), tone in boxes:
        hit, distance = _aabb(eye, dirs, lo, hi)
        shade = np.empty_like(color)
        shade[..., 0] = tone[0]
        shade[..., 1] = tone[1]
        shade[..., 2] = tone[2]
        _paint(color, depth, hit, distance, shade)
    return np.clip(color, 0, 255).astype(np.uint8), depth


def _sprite(height: int, width: int, kind: str) -> np.ndarray:
    ys = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    xs = np.linspace(-1, 1, width, dtype=np.float32)[None, :]
    if kind == "flame":
        half = 0.18 + 0.82 * ys
        taper = np.clip(np.sin(np.clip(ys, 0, 1) * np.pi), 0, 1) ** 0.65
        body = np.clip(1 - np.abs(xs) / np.maximum(half, 1e-3), 0, 1) * taper
        phase = np.sin(xs * 9 + ys * 18) * 0.08
        alpha = np.clip(body + phase, 0, 1)
        red = 40 + 180 * ys + 35 * (1 - np.abs(xs))
        green = 30 + 150 * ys * (1 - np.abs(xs) * 0.6)
        blue = 20 + 40 * ys + np.zeros_like(xs)
    else:
        alpha = np.clip(1 - xs * xs * 0.8 - ((ys - 0.4) * 1.2) ** 2, 0, 1) * 0.82
        red = np.full_like(alpha, 128)
        green = np.full_like(alpha, 128)
        blue = np.full_like(alpha, 126)
    image = np.stack([blue, green, red, alpha * 255], axis=-1)
    return np.clip(image, 0, 255).astype(np.uint8)


def _blit(canvas: np.ndarray, sprite: np.ndarray, x0: int, y0: int) -> None:
    height, width = sprite.shape[:2]
    x1 = min(IMAGE_W, x0 + width)
    y1 = min(IMAGE_H, y0 + height)
    sx0 = max(0, -x0)
    sy0 = max(0, -y0)
    x0 = max(0, x0)
    y0 = max(0, y0)
    if x0 >= x1 or y0 >= y1:
        return
    patch = sprite[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
    alpha = patch[..., 3:4].astype(np.float32) / 255
    dest = canvas[y0:y1, x0:x1].astype(np.float32)
    canvas[y0:y1, x0:x1] = np.clip(dest * (1 - alpha) + patch[..., :3].astype(np.float32) * alpha, 0, 255).astype(
        np.uint8
    )


def _place(canvas: np.ndarray, camera: VirtualCamera, corners: np.ndarray, kind: str) -> None:
    from .geometry import box_of

    box = box_of(camera, corners)
    if box is None:
        return
    x0, y0, x1, y1 = box
    left, top = int(np.floor(x0)), int(np.floor(y0))
    width = max(2, int(np.ceil(x1)) - left)
    height = max(2, int(np.ceil(y1)) - top)
    if kind == "person":
        sprite = np.zeros((height, width, 4), dtype=np.uint8)
        sprite[..., 0] = 46
        sprite[..., 1] = 52
        sprite[..., 2] = 64
        sprite[..., 3] = 230
        radius = max(2, width // 5)
        yy, xx = np.ogrid[:height, :width]
        sprite[(xx - width // 2) ** 2 + (yy - radius * 2) ** 2 <= radius**2, 3] = 240
        _blit(canvas, sprite, left, top)
        return
    _blit(canvas, _sprite(height, width, kind), left, top)


def composite(
    camera: VirtualCamera,
    background: np.ndarray,
    *,
    flame: tuple[np.ndarray, float, float] | None,
    smoke: tuple[np.ndarray, float] | None,
    person: np.ndarray | None,
) -> np.ndarray:
    from .geometry import billboard

    canvas = background.copy()
    if person is not None:
        _place(canvas, camera, billboard(camera, person, 1.7, 0.44), "person")
    if smoke is not None:
        origin, size = smoke
        _place(canvas, camera, billboard(camera, origin, size * 0.7, size * 2), "smoke")
    if flame is not None:
        base, height_m, diameter = flame
        _place(canvas, camera, billboard(camera, base, height_m, diameter), "flame")
    return canvas
