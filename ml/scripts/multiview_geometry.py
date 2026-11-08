from itertools import combinations

import cv2
import numpy as np
from scipy.optimize import minimize


def calibrate(world, pixels, intrinsics, distortion, sigma):
    poses, covariances = [], []
    for xyz, uv, k, d in zip(world, pixels, intrinsics, distortion, strict=True):
        ok, r, t, indices = cv2.solvePnPRansac(
            xyz, uv, k, d, iterationsCount=300, reprojectionError=3 * sigma,
            confidence=0.999, flags=cv2.SOLVEPNP_EPNP,
        )
        if not ok:
            raise ValueError('Static landmark pose estimation failed')
        keep = indices[:, 0]
        r, t = cv2.solvePnPRefineLM(xyz[keep], uv[keep], k, d, r, t)
        _, jacobian = cv2.projectPoints(xyz[keep], r, t, k, d)
        j = jacobian[:, :6]
        covariances.append(sigma ** 2 * np.linalg.inv(j.T @ j))
        poses.append(np.r_[r.ravel(), t.ravel()])
    return np.array(poses), np.array(covariances)


def project(point, intrinsics, distortion, poses):
    values, pose_jacobians, source_jacobians = [], [], []
    for k, d, pose in zip(intrinsics, distortion, poses, strict=True):
        uv, jacobian = cv2.projectPoints(point.reshape(1, 3), pose[:3], pose[3:], k, d)
        rotation = cv2.Rodrigues(pose[:3])[0]
        values.append(uv.reshape(2))
        pose_jacobians.append(jacobian[:, :6])
        source_jacobians.append(jacobian[:, 3:6] @ rotation)
    return np.array(values), np.array(pose_jacobians), np.array(source_jacobians)


def triangulate(pixels, intrinsics, distortion, poses):
    centers, directions = [], []
    for uv, k, d, pose in zip(pixels, intrinsics, distortion, poses, strict=True):
        rotation = cv2.Rodrigues(pose[:3])[0]
        normalized = cv2.undistortPoints(uv.reshape(1, 1, 2), k, d).reshape(2)
        direction = rotation.T @ np.r_[normalized, 1.0]
        directions.append(direction / np.linalg.norm(direction))
        centers.append(-rotation.T @ pose[3:])
    directions, centers = np.array(directions), np.array(centers)
    a = np.eye(3) - directions[:, :, None] * directions[:, None, :]
    return np.linalg.lstsq(a.sum(axis=0), np.einsum('vij,vj->i', a, centers), rcond=None)[0]


def locate(pixels, intrinsics, distortion, poses, pose_covariance, pixel_covariance,
           image_area, reliability):
    def evidence(point):
        predicted, pose_j, source_j = project(point, intrinsics, distortion, poses)
        covariance = pixel_covariance + pose_j @ pose_covariance @ pose_j.transpose(0, 2, 1)
        inverse = np.linalg.inv(covariance)
        residual = predicted - pixels
        squared = np.einsum('vi,vij,vj->v', residual, inverse, residual)
        log_signal = (np.log(reliability * image_area / (2 * np.pi))
                      - 0.5 * np.linalg.slogdet(covariance)[1] - 0.5 * squared)
        mixture = np.logaddexp(log_signal, np.log1p(-reliability))
        return mixture, np.exp(log_signal - mixture), inverse, source_j

    candidates = []
    for pair in combinations(range(len(pixels)), 2):
        selected = np.array(pair)
        candidates.append(triangulate(pixels[selected], intrinsics[selected],
                                      distortion[selected], poses[selected]))
    candidates.sort(key=lambda point: -evidence(point)[0].sum())
    solutions = [minimize(lambda point: -evidence(point)[0].sum(), initial,
                          method='Nelder-Mead', options={'maxiter': 800, 'xatol': 1e-7})
                 for initial in candidates[:2]]
    for solution in solutions:
        if not solution.success:
            raise RuntimeError(solution.message)
    point = min(solutions, key=lambda solution: solution.fun).x
    rotations = np.array([cv2.Rodrigues(pose[:3])[0] for pose in poses])
    depth = np.einsum('vij,j->vi', rotations, point)[:, 2] + poses[:, 5]
    _, responsibility, inverse, source_j = evidence(point)
    supported = (responsibility >= 0.5) & (depth > 0)
    information = np.einsum('v,vji,vjk,vkl->il', responsibility * supported,
                             source_j, inverse, source_j)
    # Local covariance conditions on a single mode and independent fixed landmarks.
    eigenvalues = np.linalg.eigvalsh(information)
    if supported.sum() < 2 or eigenvalues[0] <= 1e-10 * eigenvalues[-1]:
        return {'status': 'UNOBSERVABLE', 'support': supported.tolist()}
    return {'status': 'ESTIMATED', 'xyz': point.tolist(),
            'covariance': np.linalg.inv(information).tolist(),
            'condition_number': float(eigenvalues[-1] / eigenvalues[0]),
            'support': supported.tolist()}
