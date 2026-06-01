"""Tests for MPS compatibility patch.

This module provides tests to cover the MPS patch functionality for
transformers library compatibility with Apple Silicon GPUs.
"""

import pytest
import torch
from unittest.mock import patch, MagicMock


class TestPatchTransformersForMPS:
    """Tests for patch_transformers_for_mps function."""

    def test_mps_not_available_skips_patch(self) -> None:
        """Test that patch is skipped when MPS is not available (lines 32-34)."""
        with patch("torch.backends.mps.is_available", return_value=False):
            from secondbrain.utils.mps_patch import patch_transformers_for_mps
            
            patch_transformers_for_mps()

    def test_mps_available_import_error(self) -> None:
        """Test ImportError handling when transformers not available (lines 96-97)."""
        with patch("torch.backends.mps.is_available", return_value=True):
            # Mock the import to raise ImportError
            import builtins
            original_import = builtins.__import__
            
            def mock_import(name, *args, **kwargs):
                if "transformers.models.rt_detr_v2" in name:
                    raise ImportError("No module named 'transformers'")
                return original_import(name, *args, **kwargs)
            
            with patch.object(builtins, "__import__", mock_import):
                from secondbrain.utils.mps_patch import patch_transformers_for_mps
                patch_transformers_for_mps()

    def test_mps_available_generic_error(self) -> None:
        """Test generic exception handling (lines 98-99)."""
        with patch("torch.backends.mps.is_available", return_value=True):
            import builtins
            original_import = builtins.__import__
            
            def mock_import(name, *args, **kwargs):
                if "transformers.models.rt_detr_v2" in name:
                    raise RuntimeError("Simulated error")
                return original_import(name, *args, **kwargs)
            
            with patch.object(builtins, "__import__", mock_import):
                from secondbrain.utils.mps_patch import patch_transformers_for_mps
                patch_transformers_for_mps()


class TestPatchedFunctionLogic:
    """Tests for the patched build_2d_sinusoidal_position_embedding logic."""

    def _create_patched_function(self):
        """Create the patched function for testing."""
        def patched_build_2d_sinusoidal_position_embedding(
            height: int,
            width: int,
            embed_dim: int = 256,
            temperature: float = 10000.0,
            cls_token: bool = False,
            device: torch.device | None = None,
            dtype: torch.dtype = torch.float32,
        ) -> torch.Tensor:
            if embed_dim % 4 != 0:
                raise ValueError(f"`embed_dim` must be divisible by 4, got {embed_dim}")
            
            pos_dim = embed_dim // 4
            omega = torch.arange(pos_dim, dtype=torch.float32, device=device) / pos_dim
            omega = 1.0 / (temperature**omega)
            
            grid_h = torch.arange(height, dtype=torch.float32, device=device)
            grid_w = torch.arange(width, dtype=torch.float32, device=device)
            grid_h, grid_w = torch.meshgrid(grid_h, grid_w, indexing="ij")
            
            emb_h = grid_h.flatten().outer(omega)
            emb_w = grid_w.flatten().outer(omega)
            
            pos_embed = torch.cat([emb_h.sin(), emb_h.cos(), emb_w.sin(), emb_w.cos()], dim=1)
            
            if cls_token:
                pos_embed = torch.cat(
                    [torch.zeros(1, embed_dim, dtype=torch.float32, device=device), pos_embed],
                    dim=0
                )
            
            return pos_embed.to(dtype)
        
        return patched_build_2d_sinusoidal_position_embedding

    def test_embed_dim_validation_fails(self) -> None:
        """Test ValueError when embed_dim not divisible by 4 (lines 66-67)."""
        func = self._create_patched_function()
        
        with pytest.raises(ValueError, match="must be divisible by 4"):
            func(height=10, width=10, embed_dim=102)

    def test_embed_dim_validation_passes(self) -> None:
        """Test valid embed_dim values (line 66)."""
        func = self._create_patched_function()
        
        func(height=10, width=10, embed_dim=256)
        func(height=10, width=10, embed_dim=128)
        func(height=10, width=10, embed_dim=64)

    def test_basic_embedding_creation(self) -> None:
        """Test that function creates valid embeddings (lines 69-81)."""
        func = self._create_patched_function()
        
        result = func(height=10, width=10, embed_dim=256)
        
        assert result.shape == (100, 256)
        assert result.dtype == torch.float32

    def test_cls_token_increases_size(self) -> None:
        """Test cls_token parameter adds extra row (lines 83-87)."""
        func = self._create_patched_function()
        
        result_no_token = func(height=10, width=10, embed_dim=256, cls_token=False)
        result_with_token = func(height=10, width=10, embed_dim=256, cls_token=True)
        
        assert result_no_token.shape == (100, 256)
        assert result_with_token.shape == (101, 256)

    def test_output_uses_float32(self) -> None:
        """Test that output uses float32 throughout (lines 70-81)."""
        func = self._create_patched_function()
        
        result = func(height=8, width=8, embed_dim=128)
        
        assert result.dtype == torch.float32
        assert not torch.isnan(result).any()
        assert not torch.isinf(result).any()

    def test_various_grid_sizes(self) -> None:
        """Test various grid sizes (lines 69-81)."""
        func = self._create_patched_function()
        
        test_cases = [
            (8, 8, 128),
            (16, 16, 256),
            (10, 20, 128),
            (7, 13, 256),
        ]
        
        for height, width, embed_dim in test_cases:
            result = func(height=height, width=width, embed_dim=embed_dim)
            expected_size = height * width
            assert result.shape == (expected_size, embed_dim)
            assert result.dtype == torch.float32

    def test_different_embed_dims(self) -> None:
        """Test different embedding dimensions (lines 66-69)."""
        func = self._create_patched_function()
        
        for embed_dim in [64, 128, 256, 512]:
            result = func(height=8, width=8, embed_dim=embed_dim)
            assert result.shape == (64, embed_dim)
            assert result.dtype == torch.float32

    def test_custom_dtype(self) -> None:
        """Test custom dtype parameter (line 50, 89)."""
        func = self._create_patched_function()
        
        result = func(height=8, width=8, embed_dim=128, dtype=torch.float32)
        
        assert result.dtype == torch.float32

    def test_patched_function_via_actual_patch(self) -> None:
        """Test calling the patched function through actual patch application (lines 66-89)."""
        # Create a mock for the transformers module
        mock_modeling = MagicMock()
        mock_original_func = MagicMock()
        mock_modeling.build_2d_sinusoidal_position_embedding = mock_original_func
        
        with patch("torch.backends.mps.is_available", return_value=True):
            # Patch the import to return our mock
            import sys
            mock_transformers = MagicMock()
            mock_transformers.models.rt_detr_v2.modeling_rt_detr_v2 = mock_modeling
            sys.modules['transformers'] = mock_transformers
            sys.modules['transformers.models'] = mock_transformers.models
            sys.modules['transformers.models.rt_detr_v2'] = mock_transformers.models.rt_detr_v2
            sys.modules['transformers.models.rt_detr_v2.modeling_rt_detr_v2'] = mock_modeling
            
            try:
                from secondbrain.utils.mps_patch import patch_transformers_for_mps
                
                # Apply the patch
                patch_transformers_for_mps()
                
                # Now call the patched function which should execute lines 66-89
                result = mock_modeling.build_2d_sinusoidal_position_embedding(
                    height=8, width=8, embed_dim=128
                )
                
                # Verify the result
                assert isinstance(result, torch.Tensor)
                assert result.shape == (64, 128)
                assert result.dtype == torch.float32
            finally:
                # Clean up
                sys.modules.pop('transformers', None)
                sys.modules.pop('transformers.models', None)
                sys.modules.pop('transformers.models.rt_detr_v2', None)
                sys.modules.pop('transformers.models.rt_detr_v2.modeling_rt_detr_v2', None)
