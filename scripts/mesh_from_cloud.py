"""Open3D Poisson meshing fallback from an existing reconstructed point cloud.

Used when the COLMAP dense/mesh stages are unavailable but a genuine point
cloud (COLMAP sparse or the OpenCV SfM cloud) exists. The mesh is an
interpolation of that cloud, not a measured surface, and this is recorded in
the returned report so callers can label it honestly.
"""
import argparse
import json
from pathlib import Path

import numpy as np


def mesh_from_cloud(cloud_path, mesh_path, depth=8, trim=5, density_threshold=None):
    """Reconstruct a triangle mesh from a PLY cloud with Open3D Poisson meshing."""
    try:
        import open3d as o3d
    except (ImportError, OSError) as exc:  # pragma: no cover - depends on runtime
        raise RuntimeError(f'Open3D is unavailable in this runtime ({exc})') from exc
    cloud_path, mesh_path = Path(cloud_path), Path(mesh_path)
    if not cloud_path.is_file():
        raise RuntimeError(f'Point cloud is missing: {cloud_path}')
    cloud = o3d.io.read_point_cloud(str(cloud_path))
    points = np.asarray(cloud.points)
    if not len(points) or not np.isfinite(points).all():
        raise RuntimeError('Point cloud is empty or has nonfinite coordinates')
    if len(points) < 50:
        raise RuntimeError('Fewer than 50 reconstructed points; meshing would be meaningless')
    cloud = cloud.voxel_down_sample(voxel_size=float(np.median(np.ptp(points, axis=0)) / 200.0) or 0.01)
    cloud.estimate_normals()
    cloud.orient_normals_consistent_tangent_plane(10)
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(cloud, depth=depth)
    densities = np.asarray(densities)
    if density_threshold is None:
        density_threshold = float(np.quantile(densities, 0.03))
    mesh.remove_vertices_by_mask(densities < density_threshold)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_unreferenced_vertices()
    if not len(mesh.triangles):
        raise RuntimeError('Poisson meshing produced no triangles for this cloud')
    mesh.compute_vertex_normals()
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(mesh_path), mesh):
        raise RuntimeError(f'Could not write mesh to {mesh_path}')
    report = dict(vertices=int(len(mesh.vertices)), triangles=int(len(mesh.triangles)),
                  source_cloud=str(cloud_path), method='open3d_poisson', poisson_depth=depth,
                  density_trim=float(density_threshold),
                  caution='Interpolated surface from a reconstructed cloud; faces are estimates, not surveyed geometry.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Input PLY point cloud')
    parser.add_argument('--output', type=Path, required=True, help='Output mesh PLY')
    parser.add_argument('--depth', type=int, default=8)
    parser.add_argument('--trim', type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(mesh_from_cloud(args.input, args.output, args.depth, args.trim), indent=2))


if __name__ == '__main__':
    main()
