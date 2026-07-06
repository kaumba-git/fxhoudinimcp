"""Karma/Solaris rendering handlers for FXHoudini-MCP.

Covers what the generic rendering/lops modules do not: Karma engine
(CPU/XPU) selection, render-graph AOV/render-product authoring via the
karma* convenience LOPs (karmarenderproducts, karmastandardrendervars,
karmacryptomatte), and a structured render-diagnostics snapshot.

Parameter names here were verified against a live Houdini 21.0.512
session (see fxhoudinimcp scratchpad probes), not guessed from docs.
"""

from __future__ import annotations

# Built-in
import logging

# Third-party
import hou

# Internal
from fxhoudinimcp_server.dispatcher import register_handler

logger = logging.getLogger(__name__)


def _get_node(node_path: str) -> "hou.Node":
    node = hou.node(node_path)
    if node is None:
        raise hou.OperationFailed(f"Node not found: {node_path}")
    return node


###### karma.get_engine_mode

def get_engine_mode(node_path: str) -> dict:
    """Read the CPU/XPU engine mode from a Karma ROP.

    Args:
        node_path: Path to a karma ROP node.
    """
    node = _get_node(node_path)
    parm = node.parm("engine")
    if parm is None:
        raise hou.OperationFailed(
            f"Node {node_path} has no 'engine' parameter -- is it a karma ROP?"
        )
    return {
        "node_path": node_path,
        "engine": parm.evalAsString(),
        "available_engines": list(parm.menuItems()),
        "available_labels": list(parm.menuLabels()),
    }


###### karma.set_engine_mode

def set_engine_mode(node_path: str, engine: str) -> dict:
    """Set the CPU/XPU engine mode on a Karma ROP.

    Args:
        node_path: Path to a karma ROP node.
        engine: "cpu" or "xpu".
    """
    node = _get_node(node_path)
    parm = node.parm("engine")
    if parm is None:
        raise hou.OperationFailed(
            f"Node {node_path} has no 'engine' parameter -- is it a karma ROP?"
        )
    valid = list(parm.menuItems())
    if engine not in valid:
        raise hou.OperationFailed(
            f"Unknown engine '{engine}' for {node_path}. Valid options: {valid}"
        )
    parm.set(engine)
    return {
        "success": True,
        "node_path": node_path,
        "engine": parm.evalAsString(),
    }


###### karma.get_render_diagnostics

def get_render_diagnostics(node_path: str) -> dict:
    """Read a structured snapshot of a Karma ROP's render-affecting settings.

    This does not parse render logs or measure actual render time --
    it reports the *configuration* (engine, resolution, sampling,
    denoiser) so an agent can reason about expected speed/quality
    tradeoffs before rendering.

    Args:
        node_path: Path to a karma ROP node.
    """
    node = _get_node(node_path)

    def _parm(name, default=None):
        p = node.parm(name)
        return p.eval() if p is not None else default

    engine_parm = node.parm("engine")

    return {
        "node_path": node_path,
        "engine": engine_parm.evalAsString() if engine_parm else None,
        "resolution": [_parm("resolutionx"), _parm("resolutiony")],
        "samples_per_pixel": _parm("samplesperpixel"),
        "variance_aa": {
            "min_samples": _parm("varianceaa_minsamples"),
            "max_samples": _parm("varianceaa_maxsamples"),
            "threshold": _parm("varianceaa_thresh"),
        },
        "denoiser": {
            "enabled": bool(_parm("denoiser", 0)),
            "use_albedo": bool(_parm("denoise_usealbedo", 0)),
            "use_normal": bool(_parm("denoise_useN", 0)),
        },
    }


###### karma.create_render_product

def create_render_product(
    parent_path: str,
    name: str | None = None,
    product_name: str | None = None,
    camera_path: str | None = None,
) -> dict:
    """Create a karmarenderproducts LOP and configure its first product entry.

    Args:
        parent_path: Parent LOP network (e.g. a /stage lopnet).
        name: Node name for the new karmarenderproducts node.
        product_name: Output file path/name for the render product
            (Karma's "Product Name" -- typically an image path).
        camera_path: USD camera prim path to render through.
    """
    parent = _get_node(parent_path)
    node = parent.createNode("karmarenderproducts", name or "renderproducts1")

    products_parm = node.parm("products")
    if products_parm is not None and products_parm.eval() < 1:
        products_parm.set(1)

    if product_name is not None:
        parm = node.parm("productName_0")
        if parm is not None:
            parm.set(product_name)
    if camera_path is not None:
        docam = node.parm("docamera_0")
        if docam is not None:
            docam.set(True)
        cam_parm = node.parm("camera_0")
        if cam_parm is not None:
            cam_parm.set(camera_path)

    node.moveToGoodPosition()
    return {
        "success": True,
        "node_path": node.path(),
        "node_type": "karmarenderproducts",
        "product_name": product_name,
        "camera_path": camera_path,
    }


###### karma.setup_standard_aovs

# Curated subset of karmastandardrendervars toggle parms an artist actually
# reaches for; the node has 100+ (every light-path-expression combination),
# most never used directly. Anything not in this map still works if the
# caller passes the exact parm name -- we validate against the live node
# rather than hard-fail on an unrecognized name.
_COMMON_AOV_ALIASES = {
    "beauty": "beauty",
    "shadow": "shadow",
    "diffuse": "combineddiffuse",
    "direct_diffuse": "directdiffuse",
    "indirect_diffuse": "indirectdiffuse",
}


def setup_standard_aovs(
    parent_path: str,
    aovs: list[str],
    name: str | None = None,
) -> dict:
    """Create a karmastandardrendervars LOP with the requested AOVs enabled.

    Args:
        parent_path: Parent LOP network.
        aovs: AOV names to enable. Common aliases (diffuse, direct_diffuse,
            indirect_diffuse, shadow, beauty) are accepted; any other
            string is tried as a literal parm name on the node (e.g.
            "directspecular", "volume", "combinedreflect").
        name: Node name for the new karmastandardrendervars node.
    """
    parent = _get_node(parent_path)
    node = parent.createNode("karmastandardrendervars", name or "standardrendervars1")

    enabled: list[str] = []
    unknown: list[str] = []
    for aov in aovs:
        parm_name = _COMMON_AOV_ALIASES.get(aov, aov)
        parm = node.parm(parm_name)
        if parm is None:
            unknown.append(aov)
            continue
        parm.set(True)
        enabled.append(parm_name)

    node.moveToGoodPosition()
    result = {
        "success": True,
        "node_path": node.path(),
        "node_type": "karmastandardrendervars",
        "enabled_aovs": enabled,
    }
    if unknown:
        result["unknown_aovs"] = unknown
        result["note"] = (
            "These were not found as parameters on karmastandardrendervars "
            "and were skipped -- check the exact toggle name in the node's "
            "parameter interface."
        )
    return result


###### karma.setup_cryptomatte

def setup_cryptomatte(
    parent_path: str,
    layers: list[str] | None = None,
    name: str | None = None,
) -> dict:
    """Create a karmacryptomatte LOP with the requested crypto layers enabled.

    Solaris cryptomatte has no literal "object" layer -- USD groups
    things by "kind" (component/group/assembly) instead, so "object" is
    accepted as an alias for that.

    Args:
        parent_path: Parent LOP network.
        layers: Which crypto layers to enable: any of "primitive",
            "material", "kind" (alias: "object"), "primvar". Defaults
            to primitive, material, and kind.
        name: Node name for the new karmacryptomatte node.
    """
    parent = _get_node(parent_path)
    node = parent.createNode("karmacryptomatte", name or "cryptomatte1")

    layers = layers if layers is not None else ["primitive", "material", "kind"]
    layer_toggle_parms = {
        "object": "dokindcrypto",
        "kind": "dokindcrypto",
        "material": "domtlcrypto",
        "primitive": "doprimcrypto",
        "primvar": "doprimvarcrypto",
    }

    enabled: list[str] = []
    unknown: list[str] = []
    for layer in layers:
        parm_name = layer_toggle_parms.get(layer)
        if parm_name is None:
            unknown.append(layer)
            continue
        parm = node.parm(parm_name)
        if parm is None:
            unknown.append(layer)
            continue
        parm.set(True)
        enabled.append(layer)

    node.moveToGoodPosition()
    result = {
        "success": True,
        "node_path": node.path(),
        "node_type": "karmacryptomatte",
        "enabled_layers": enabled,
    }
    if unknown:
        result["unknown_layers"] = unknown
        result["note"] = "Valid layers are: primitive, material, kind (alias: object), primvar."
    return result


register_handler("karma.get_engine_mode", get_engine_mode)
register_handler("karma.set_engine_mode", set_engine_mode)
register_handler("karma.get_render_diagnostics", get_render_diagnostics)
register_handler("karma.create_render_product", create_render_product)
register_handler("karma.setup_standard_aovs", setup_standard_aovs)
register_handler("karma.setup_cryptomatte", setup_cryptomatte)
