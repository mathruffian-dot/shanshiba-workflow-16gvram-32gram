"""Per-person colored SAM 3D Body mesh render ("white model" with one fixed color per tracked person)  (added 2026-10-15).

Idea from Aiden_0 (youtu.be/7Re7it90iqM): give every tracked person a fixed color (1 blue, 2 red, 3 green, 4 magenta, 5 cyan, 6 yellow)
so H3 can tell which mannequin is which character ("the blue mannequin is Afu").
Implementation: reuses ComfyUI's own SAM3DBody_Render (mesh, default lit shader). The rasterizer gives person k (track order) a
pastel mix of 1 - falloff**k; with falloff 0.5 those values are distinct, so a temporary wrapper around rasterizer._make_shade_fn maps
the pastel value back to k and swaps in that person's base color (pastel 0). Install: copy this folder into ComfyUI/custom_nodes."""
import comfy_extras.sam3d_body.rasterizer as R
from comfy_api.latest import ComfyExtension, io
from comfy_extras.nodes_sam3d_body import MHRPoseData, SAM3DBody_Render
from typing_extensions import override

COLORS = {"blue": (0.12, 0.28, 1.0), "red": (1.0, 0.12, 0.12), "green": (0.1, 0.85, 0.2), "magenta": (0.9, 0.15, 0.9),
          "cyan": (0.1, 0.85, 0.95), "yellow": (1.0, 0.85, 0.1), "white": (0.85, 0.85, 0.88)}
FALLOFF = 0.5


class SAM3DBody_RenderColored(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SAM3DBody_RenderColored",
            display_name="Render 3D Body Pose (per-person colors)",
            category="image/detection",
            inputs=[
                MHRPoseData.Input("pose_data"),
                io.Image.Input("background", optional=True),
                io.Int.Input("width", default=0, min=0, max=16384, step=8),
                io.Int.Input("height", default=0, min=0, max=16384, step=8),
                io.String.Input("colors", default="blue,red,green,magenta,cyan,yellow",
                                tooltip="Color per tracked person, in SAM 3 track order (object 0, 1, ...)."),
            ],
            outputs=[io.Image.Output("image")],
        )

    @classmethod
    def execute(cls, pose_data, width, height, colors, background=None) -> io.NodeOutput:
        cols = [COLORS.get(c.strip().lower(), COLORS["white"]) for c in colors.split(",") if c.strip()]
        pastel = [0.0 if k == 0 else 1.0 - FALLOFF ** k for k in range(16)]
        orig = R._make_shade_fn

        def patched(shader_preset, composite, view_normals_v, view_pos_v, vcolor_v, faces, base_color, light_dir, pastel_mix):
            k = min(range(16), key=lambda i: abs(pastel[i] - float(pastel_mix)))
            return orig(shader_preset, composite, view_normals_v, view_pos_v, vcolor_v, faces, cols[k % len(cols)], light_dir, 0.0)

        R._make_shade_fn = patched
        try:
            return SAM3DBody_Render.execute(pose_data=pose_data, background=background, width=width, height=height, camera_info=None,
                                            render_style={"render_style": "mesh", "shader": {"shader": "default"}, "opacity": 1.0,
                                                          "person_palette_falloff": FALLOFF, "region": "full_body"})
        finally:
            R._make_shade_fn = orig


class _Ext(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SAM3DBody_RenderColored]


async def comfy_entrypoint():
    return _Ext()
