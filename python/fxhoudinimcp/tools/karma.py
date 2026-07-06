"""MCP tool wrappers for Karma/Solaris rendering operations.

Covers what the generic rendering/lops modules do not: Karma engine
(CPU/XPU) selection, render-graph AOV/render-product authoring, and a
render-diagnostics snapshot. Each tool delegates to the corresponding
handler running inside Houdini via the HTTP bridge.
"""

from __future__ import annotations

# Built-in
from typing import Optional

# Third-party
from mcp.server.fastmcp import Context

# Internal
from fxhoudinimcp.server import mcp, _get_bridge


@mcp.tool()
async def get_karma_engine_mode(ctx: Context, node_path: str) -> dict:
    """Read the CPU/XPU engine mode from a Karma ROP.

    Args:
        node_path: Path to a karma ROP node.
    """
    bridge = _get_bridge(ctx)
    return await bridge.execute("karma.get_engine_mode", {"node_path": node_path})


@mcp.tool()
async def set_karma_engine_mode(ctx: Context, node_path: str, engine: str) -> dict:
    """Set the CPU/XPU engine mode on a Karma ROP.

    XPU requires a supported GPU and is not automatically faster --
    it trades feature completeness for speed on scenes it fully
    supports. Check get_karma_engine_mode first if unsure which modes
    are available on this node.

    Args:
        node_path: Path to a karma ROP node.
        engine: "cpu" or "xpu".
    """
    bridge = _get_bridge(ctx)
    return await bridge.execute(
        "karma.set_engine_mode", {"node_path": node_path, "engine": engine}
    )


@mcp.tool()
async def get_karma_render_diagnostics(ctx: Context, node_path: str) -> dict:
    """Get a structured snapshot of a Karma ROP's render-affecting settings.

    Reports engine, resolution, sample counts, variance-AA thresholds,
    and denoiser configuration -- the inputs that determine
    speed/quality/noise tradeoffs. Does not measure actual render time;
    use this before rendering to reason about expected behavior, or
    after to check what settings produced a given result.

    Args:
        node_path: Path to a karma ROP node.
    """
    bridge = _get_bridge(ctx)
    return await bridge.execute(
        "karma.get_render_diagnostics", {"node_path": node_path}
    )


@mcp.tool()
async def create_karma_render_product(
    ctx: Context,
    parent_path: str,
    name: Optional[str] = None,
    product_name: Optional[str] = None,
    camera_path: Optional[str] = None,
) -> dict:
    """Create a karmarenderproducts LOP (the USD render-output node).

    This is the LOP-native render-output authoring path used in
    Solaris, distinct from the classic ROP-parameter approach.

    Args:
        parent_path: Parent LOP network (e.g. a /stage lopnet).
        name: Node name.
        product_name: Output file path for the render product.
        camera_path: USD camera prim path to render through.
    """
    bridge = _get_bridge(ctx)
    params: dict = {"parent_path": parent_path}
    if name is not None:
        params["name"] = name
    if product_name is not None:
        params["product_name"] = product_name
    if camera_path is not None:
        params["camera_path"] = camera_path
    return await bridge.execute("karma.create_render_product", params)


@mcp.tool()
async def setup_karma_standard_aovs(
    ctx: Context,
    parent_path: str,
    aovs: list[str],
    name: Optional[str] = None,
) -> dict:
    """Create a karmastandardrendervars LOP with the requested AOVs enabled.

    Args:
        parent_path: Parent LOP network.
        aovs: AOV names to enable. Common aliases accepted: "beauty",
            "shadow", "diffuse", "direct_diffuse", "indirect_diffuse".
            Any other string is tried as a literal toggle parm name on
            karmastandardrendervars (e.g. "directspecular", "volume").
        name: Node name.
    """
    bridge = _get_bridge(ctx)
    params: dict = {"parent_path": parent_path, "aovs": aovs}
    if name is not None:
        params["name"] = name
    return await bridge.execute("karma.setup_standard_aovs", params)


@mcp.tool()
async def setup_karma_cryptomatte(
    ctx: Context,
    parent_path: str,
    layers: Optional[list[str]] = None,
    name: Optional[str] = None,
) -> dict:
    """Create a karmacryptomatte LOP with the requested crypto layers enabled.

    Solaris has no literal "object" layer -- USD groups things by
    "kind" (component/group/assembly) instead, so "object" is accepted
    as an alias for that.

    Args:
        parent_path: Parent LOP network.
        layers: Which crypto layers to enable: any of "primitive",
            "material", "kind" (alias: "object"), "primvar". Defaults
            to primitive, material, and kind.
        name: Node name.
    """
    bridge = _get_bridge(ctx)
    params: dict = {"parent_path": parent_path}
    if layers is not None:
        params["layers"] = layers
    if name is not None:
        params["name"] = name
    return await bridge.execute("karma.setup_cryptomatte", params)
