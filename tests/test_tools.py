"""Tests for MCP tool wrappers: validate bridge delegation."""

from __future__ import annotations

# Third-party
import pytest

# Internal
from fxhoudinimcp.errors import ConnectionError as HoudiniConnectionError
from fxhoudinimcp.tools.code import execute_python
from fxhoudinimcp.tools.materials import list_materials
from fxhoudinimcp.tools.nodes import create_node
from fxhoudinimcp.tools.scene import (
    get_houdini_connection_status,
    get_scene_info,
    new_scene,
)
from fxhoudinimcp.tools.workflows import setup_pyro_sim
from fxhoudinimcp.tools.karma import (
    create_karma_render_product,
    get_karma_engine_mode,
    get_karma_render_diagnostics,
    set_karma_engine_mode,
    setup_karma_cryptomatte,
    setup_karma_standard_aovs,
)


class TestSceneTools:
    @pytest.mark.asyncio
    async def test_get_scene_info(self, mock_ctx, mock_bridge):
        mock_bridge.execute.return_value = {"hip_file": "/tmp/test.hip"}
        result = await get_scene_info(mock_ctx)
        mock_bridge.execute.assert_called_once_with("scene.get_scene_info")
        assert result == {"hip_file": "/tmp/test.hip"}

    @pytest.mark.asyncio
    async def test_new_scene(self, mock_ctx, mock_bridge):
        mock_bridge.execute.return_value = {"created": True}
        result = await new_scene(mock_ctx, save_current=True)
        mock_bridge.execute.assert_called_once_with("scene.new_scene", {"save_current": True})

    @pytest.mark.asyncio
    async def test_connection_status_success(self, mock_ctx, mock_bridge):
        mock_bridge.base_url = "http://localhost:8100"
        mock_bridge.health_check.return_value = {"status": "ok", "pid": 123}
        result = await get_houdini_connection_status(mock_ctx)
        assert result == {
            "connected": True,
            "base_url": "http://localhost:8100",
            "health": {"status": "ok", "pid": 123},
        }

    @pytest.mark.asyncio
    async def test_connection_status_disconnect(self, mock_ctx, mock_bridge):
        mock_bridge.base_url = "http://localhost:8100"
        mock_bridge.health_check.side_effect = HoudiniConnectionError(
            "Cannot connect",
            details={"url": "http://localhost:8100"},
        )
        result = await get_houdini_connection_status(mock_ctx)
        assert result["connected"] is False
        assert result["base_url"] == "http://localhost:8100"
        assert result["details"] == {"url": "http://localhost:8100"}


class TestNodeTools:
    @pytest.mark.asyncio
    async def test_create_node_required_params(self, mock_ctx, mock_bridge):
        mock_bridge.execute.return_value = {"path": "/obj/geo1/box1"}
        result = await create_node(mock_ctx, parent_path="/obj/geo1", node_type="box")
        mock_bridge.execute.assert_called_once_with(
            "nodes.create_node",
            {"parent_path": "/obj/geo1", "node_type": "box"},
        )

    @pytest.mark.asyncio
    async def test_create_node_all_params(self, mock_ctx, mock_bridge):
        await create_node(
            mock_ctx,
            parent_path="/obj",
            node_type="geo",
            name="my_geo",
            position=[0, 0],
        )
        mock_bridge.execute.assert_called_once_with(
            "nodes.create_node",
            {"parent_path": "/obj", "node_type": "geo", "name": "my_geo", "position": [0, 0]},
        )


class TestCodeTools:
    @pytest.mark.asyncio
    async def test_execute_python_code_only(self, mock_ctx, mock_bridge):
        result = await execute_python(
            mock_ctx,
            code="print('hi')",
            justification="no dedicated tool prints to the console",
        )
        mock_bridge.execute.assert_called_once_with(
            "code.execute_python",
            {"code": "print('hi')"},
        )
        # The justification is echoed back, never forwarded to Houdini.
        assert result["justification"]

    @pytest.mark.asyncio
    async def test_execute_python_with_return(self, mock_ctx, mock_bridge):
        await execute_python(
            mock_ctx,
            code="x = 1 + 1",
            justification="no dedicated tool evaluates arbitrary Python",
            return_expression="x",
        )
        mock_bridge.execute.assert_called_once_with(
            "code.execute_python",
            {"code": "x = 1 + 1", "return_expression": "x"},
        )

    @pytest.mark.asyncio
    async def test_justification_required_in_schemas(self):
        """The schema must force clients to articulate why VEX/Python."""
        from fxhoudinimcp.server import mcp

        tools = {t.name: t for t in await mcp.list_tools()}
        for tool_name in ("execute_python", "create_wrangle"):
            schema = tools[tool_name].inputSchema
            assert "justification" in schema["required"], (
                f"{tool_name} must require a justification"
            )


class TestWorkflowTools:
    @pytest.mark.asyncio
    async def test_setup_pyro_defaults(self, mock_ctx, mock_bridge):
        await setup_pyro_sim(mock_ctx)
        mock_bridge.execute.assert_called_once_with(
            "workflow.setup_pyro_sim",
            {
                "source_geo": "/obj/geo1/sphere1",
                "container": "box",
                "res_scale": 1.0,
                "substeps": 1,
                "name": "pyro_sim",
            },
        )


class TestMaterialTools:
    @pytest.mark.asyncio
    async def test_list_materials_default(self, mock_ctx, mock_bridge):
        await list_materials(mock_ctx)
        mock_bridge.execute.assert_called_once_with(
            "materials.list_materials",
            {"root_path": "/mat"},
        )


class TestKarmaTools:
    @pytest.mark.asyncio
    async def test_get_karma_engine_mode(self, mock_ctx, mock_bridge):
        await get_karma_engine_mode(mock_ctx, node_path="/out/karma1")
        mock_bridge.execute.assert_called_once_with(
            "karma.get_engine_mode", {"node_path": "/out/karma1"}
        )

    @pytest.mark.asyncio
    async def test_set_karma_engine_mode(self, mock_ctx, mock_bridge):
        await set_karma_engine_mode(mock_ctx, node_path="/out/karma1", engine="xpu")
        mock_bridge.execute.assert_called_once_with(
            "karma.set_engine_mode", {"node_path": "/out/karma1", "engine": "xpu"}
        )

    @pytest.mark.asyncio
    async def test_get_karma_render_diagnostics(self, mock_ctx, mock_bridge):
        await get_karma_render_diagnostics(mock_ctx, node_path="/out/karma1")
        mock_bridge.execute.assert_called_once_with(
            "karma.get_render_diagnostics", {"node_path": "/out/karma1"}
        )

    @pytest.mark.asyncio
    async def test_create_karma_render_product_minimal(self, mock_ctx, mock_bridge):
        await create_karma_render_product(mock_ctx, parent_path="/stage")
        mock_bridge.execute.assert_called_once_with(
            "karma.create_render_product", {"parent_path": "/stage"}
        )

    @pytest.mark.asyncio
    async def test_create_karma_render_product_full(self, mock_ctx, mock_bridge):
        await create_karma_render_product(
            mock_ctx,
            parent_path="/stage",
            name="products1",
            product_name="$HIP/render/beauty.exr",
            camera_path="/cameras/cam1",
        )
        mock_bridge.execute.assert_called_once_with(
            "karma.create_render_product",
            {
                "parent_path": "/stage",
                "name": "products1",
                "product_name": "$HIP/render/beauty.exr",
                "camera_path": "/cameras/cam1",
            },
        )

    @pytest.mark.asyncio
    async def test_setup_karma_standard_aovs(self, mock_ctx, mock_bridge):
        await setup_karma_standard_aovs(
            mock_ctx, parent_path="/stage", aovs=["beauty", "diffuse"]
        )
        mock_bridge.execute.assert_called_once_with(
            "karma.setup_standard_aovs",
            {"parent_path": "/stage", "aovs": ["beauty", "diffuse"]},
        )

    @pytest.mark.asyncio
    async def test_setup_karma_cryptomatte_default(self, mock_ctx, mock_bridge):
        await setup_karma_cryptomatte(mock_ctx, parent_path="/stage")
        mock_bridge.execute.assert_called_once_with(
            "karma.setup_cryptomatte", {"parent_path": "/stage"}
        )

    @pytest.mark.asyncio
    async def test_setup_karma_cryptomatte_explicit_layers(self, mock_ctx, mock_bridge):
        await setup_karma_cryptomatte(
            mock_ctx, parent_path="/stage", layers=["object", "material"]
        )
        mock_bridge.execute.assert_called_once_with(
            "karma.setup_cryptomatte",
            {"parent_path": "/stage", "layers": ["object", "material"]},
        )
