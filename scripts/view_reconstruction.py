"""Interactive inspection of real COLMAP output and camera centers."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import open3d as o3d


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--mode', choices=['sparse', 'dense', 'mesh'], default='sparse')
    parser.add_argument('--snapshot', type=Path, help='Render a hidden-window PNG for verification instead of opening the viewer')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    run = args.run or Path(json.loads((project / 'output/reconstruction/latest.json').read_text())['run_directory'])
    target = run / {'sparse':'sparse.ply', 'dense':'dense/fused.ply', 'mesh':'dense/mesh.ply'}[args.mode]
    if not target.exists():
        parser.error(f'Requested real reconstruction output does not exist: {target}')
    if args.mode == 'mesh':
        geometry = o3d.io.read_triangle_mesh(str(target))
        geometry.compute_vertex_normals()
        if not len(geometry.triangles):
            parser.error('Mesh has no triangles')
    else:
        geometry = o3d.io.read_point_cloud(str(target))
        if not len(geometry.points):
            parser.error('Point cloud is empty')
    with (run / 'camera_trajectory.csv').open() as f:
        rows = list(csv.DictReader(f))
    centers = np.array([[float(r[k]) for k in ('x','y','z')] for r in rows])
    cameras = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(centers))
    cameras.paint_uniform_color([1, 0.35, 0.05])
    lines = o3d.geometry.LineSet(o3d.utility.Vector3dVector(centers),
        o3d.utility.Vector2iVector([[i,i+1] for i in range(len(centers)-1)]))
    lines.paint_uniform_color([1, 0.35, 0.05])
    print('Arbitrary reconstruction units; not georeferenced. Orange: camera centers in filename order.')
    print('Mesh surfaces are interpolated estimates; gaps/hidden surfaces are not validated.')
    objects = [geometry, cameras, lines]
    if args.snapshot:
        import time
        vis = o3d.visualization.Visualizer()
        if not vis.create_window(width=1200, height=800, visible=False):
            raise RuntimeError('Open3D could not create a rendering context')
        try:
            for obj in objects:
                vis.add_geometry(obj)
            vis.get_render_option().point_size = 2
            vis.get_render_option().mesh_show_back_face = True
            vis.get_render_option().background_color = np.array([0.06, 0.08, 0.11])
            for _ in range(10):
                vis.poll_events()
                vis.update_renderer()
                time.sleep(0.1)
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            vis.capture_screen_image(str(args.snapshot), do_render=True)
        finally:
            vis.destroy_window()
    else:
        o3d.visualization.draw_geometries(objects,
            window_name='AeroSphere | ' + args.mode + ' | arbitrary units, not georeferenced', width=1200, height=800,
            mesh_show_back_face=True)


if __name__ == '__main__':
    main()
