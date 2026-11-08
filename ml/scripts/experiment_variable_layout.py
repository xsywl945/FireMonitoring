import json
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from multiview_geometry import calibrate, locate, project, triangulate

rng = np.random.default_rng(20261108)
cv2.setRNGSeed(20261108)
errors = {name: [] for name in ['stale_pose', 'current_pose_linear', 'current_pose_robust', 'oracle_pose']}
covered, failures, pose_errors = [], 0, []
world = rng.uniform([-1, -1, 0], [1, 1, 2], (60, 3))
reference = None
visible_counts = []
for event in range(120):
    angles = np.arange(4) * np.pi / 2 + rng.uniform(-0.5, 0.5, 4)
    radius = rng.uniform(3.0, 6.0, 4)
    centers = np.column_stack([radius * np.cos(angles), radius * np.sin(angles),
                               rng.uniform(0.6, 3.6, 4)])
    poses = []
    for center in centers:
        forward = np.array([0, 0, 1.0]) - center
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        rotation = np.stack([right, np.cross(forward, right), forward])
        rotation = Rotation.from_euler('xyz', [*rng.uniform(-0.16, 0.16, 2),
                                               rng.uniform(-0.8, 0.8)]).as_matrix() @ rotation
        poses.append(np.r_[cv2.Rodrigues(rotation)[0].ravel(), -rotation @ center])
    poses = np.array(poses)
    focal = rng.uniform(650, 950, 4)
    intrinsics = np.array([[[f, 0, 640], [0, f, 360], [0, 0, 1.0]] for f in focal])
    distortion = np.zeros((4, 5))
    observations, landmarks = [], []
    for k, pose in zip(intrinsics, poses, strict=True):
        uv = cv2.projectPoints(world, pose[:3], pose[3:], k, None)[0].reshape(-1, 2)
        keep = ((uv > [0, 0]) & (uv < [1280, 720])).all(axis=1)
        landmarks.append(world[keep])
        measured = uv[keep] + rng.normal(0, 1.0, (keep.sum(), 2))
        measured[:3] += rng.normal(0, 20, (3, 2))
        observations.append(measured)
    estimated, covariance = calibrate(landmarks, observations, intrinsics, distortion, 1.0)
    estimated_centers = np.array([-cv2.Rodrigues(p[:3])[0].T @ p[3:] for p in estimated])
    pose_errors.extend(np.linalg.norm(estimated_centers - centers, axis=1))
    source = rng.uniform([-0.5, -0.5, 0.2], [0.5, 0.5, 1.8])
    truth_pixels = project(source, intrinsics, distortion, poses)[0]
    visible = ((truth_pixels > [0, 0]) & (truth_pixels < [1280, 720])).all(axis=1)
    visible_counts.append(int(visible.sum()))
    assert visible.all(), 'This controlled experiment requires all four source projections in view'
    pixels = truth_pixels + rng.normal(0, 2, (4, 2))
    if event % 2 == 0:
        angle = rng.uniform(0, 2 * np.pi)
        pixels[rng.integers(4)] += 80 * np.array([np.cos(angle), np.sin(angle)])
    if reference is None:
        reference = poses.copy()
    estimates = {'stale_pose': triangulate(pixels, intrinsics, distortion, reference),
                 'current_pose_linear': triangulate(pixels, intrinsics, distortion, estimated)}
    for name, camera_pose, pose_cov in [('current_pose_robust', estimated, covariance),
                                       ('oracle_pose', poses, np.zeros((4, 6, 6)))]:
        result = locate(pixels, intrinsics, distortion, camera_pose, pose_cov,
                        np.tile(4 * np.eye(2), (4, 1, 1)), np.full(4, 1280 * 720),
                        np.full(4, 0.95))
        if result['status'] == 'UNOBSERVABLE':
            failures += 1
            continue
        estimates[name] = np.array(result['xyz'])
        if name == 'current_pose_robust':
            delta = estimates[name] - source
            covered.append(float(delta @ np.linalg.solve(np.array(result['covariance']), delta)) <= 7.8147279)
    for name, estimate in estimates.items():
        errors[name].append(float(np.linalg.norm(estimate - source)))

metrics = {name: {'n': len(values), 'mean_m': float(np.mean(values)),
                  'p90_m': float(np.quantile(values, 0.9)), 'max_m': float(np.max(values))}
           for name, values in errors.items()}
result = {'seed': 20261108, 'layouts': 120, 'gross_error_events': 60,
          'camera_height_m': [0.6, 3.6], 'radius_m': [3, 6], 'root_height_m': [0.2, 1.8],
          'pitch_yaw_perturbation_rad': [-0.16, 0.16], 'roll_rad': [-0.8, 0.8],
          'pixel_noise_std': 2, 'landmark_noise_std': 1, 'metrics': metrics,
          'pose_center_error_mean_m': float(np.mean(pose_errors)),
          'conditional_95_ellipsoid_coverage': float(np.mean(covered)),
          'unobservable_outputs': failures, 'minimum_visible_views': min(visible_counts),
          'scope': 'Synthetic known metric landmarks and noisy oracle source projections; no image matching or YOLO inference.'}
output = Path(__file__).resolve().parents[2] / 'docs/experiments/2026-11-08-variable-layout.json'
output.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
