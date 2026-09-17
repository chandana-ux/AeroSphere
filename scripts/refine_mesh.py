"""Conservative derived mesh cleanup and appearance; original mesh is untouched."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

def refine(run):
    run=Path(run); source=run/'dense/mesh.ply'; cloud_path=run/'dense/fused.ply'
    mesh=o3d.io.read_triangle_mesh(str(source))
    cloud=o3d.io.read_point_cloud(str(cloud_path))
    if not len(mesh.triangles) or not len(cloud.points):
        raise ValueError('A real mesh and fused cloud are required')
    if not np.isfinite(np.asarray(mesh.vertices)).all() or not np.isfinite(np.asarray(cloud.points)).all():
        raise ValueError('Nonfinite input geometry')
    before=len(mesh.triangles)
    mesh.remove_duplicated_vertices();mesh.remove_duplicated_triangles();mesh.remove_degenerate_triangles();mesh.remove_unreferenced_vertices()
    # No smoothing, hole filling, new triangles or position changes.
    distance,indices=cKDTree(np.asarray(cloud.points)).query(np.asarray(mesh.vertices),workers=2)
    if cloud.has_colors():
        mesh.vertex_colors=o3d.utility.Vector3dVector(np.asarray(cloud.colors)[indices])
    mesh.compute_triangle_normals();mesh.compute_vertex_normals()
    dest=run/'dense/mesh_display.ply'
    if not o3d.io.write_triangle_mesh(str(dest),mesh):
        raise IOError('Could not write derived mesh')
    report={'original_triangles':before,'display_triangles':len(mesh.triangles),
            'vertices':len(mesh.vertices),'original_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'color_distance_median_model_units':float(np.median(distance)),
            'color_distance_max_model_units':float(distance.max()),
            'operations':['Remove duplicate/degenerate elements','Compute normals','Nearest fused-point vertex color'],
            'limitations':'No new geometry. No UV texture or per-surface image lineage. Nearest colors do not establish surface support. Existing interpolation gaps remain.'}
    (run/'dense/mesh_display.json').write_text(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path)
    print(json.dumps(refine(p.parse_args().run),indent=2))
