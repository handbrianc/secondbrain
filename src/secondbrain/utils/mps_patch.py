"""MPS compatibility patch for transformers library.

This module patches the transformers library to work around MPS float64
incompatibility issues in docling's layout model.

The issue: MPS (Apple Silicon GPU) doesn't support float64, but the
transformers library's build_2d_sinusoidal_position_embedding function
uses float64 for intermediate calculations.

Solution: Monkey-patch the function to use float32 throughout.
"""

import importlib.util
import logging

logger = logging.getLogger(__name__)

_mps_patched = False


def _mps_is_available_without_import() -> bool:
    """Detect MPS support WITHOUT importing torch (avoids ~1.7s import penalty)."""
    return importlib.util.find_spec("torch.backends.mps") is not None


def patch_transformers_for_mps() -> None:
    global _mps_patched
    if _mps_patched:
        return
    if not _mps_is_available_without_import():
        logger.debug("MPS not available (torch.backends.mps not found)")
        return
    import torch

    """Patch transformers library to avoid float64 on MPS.

    This must be called before any docling imports that use the
    RT-DETR layout model.

    The patch replaces build_2d_sinusoidal_position_embedding with
    a version that uses float32 for all intermediate calculations,
    avoiding the MPS float64 limitation while maintaining the same
    final output dtype (float32).

    Only applied when MPS is available.
    """
    if not torch.backends.mps.is_available():
        logger.debug("MPS not available, skipping transformers patch")
        return

    try:
        from transformers.models.rt_detr_v2 import modeling_rt_detr_v2

        # Create patched version using float32
        def patched_build_2d_sinusoidal_position_embedding(
            height: int,
            width: int,
            embed_dim: int = 256,
            temperature: float = 10000.0,
            cls_token: bool = False,
            device: torch.device | None = None,
            dtype: torch.dtype = torch.float32,
        ) -> torch.Tensor:
            """Patched version using float32 instead of float64.

            Args:
                height: Grid height in patches.
                width: Grid width in patches.
                embed_dim: Total embedding dimension (must be divisible by 4).
                temperature: Base for frequency decay.
                cls_token: If True, prepend zero row for CLS token.
                device: Target device.
                dtype: Output dtype.

            Returns:
                Position embedding tensor of shape (height * width [+1], embed_dim).
            """
            if embed_dim % 4 != 0:
                raise ValueError(f"`embed_dim` must be divisible by 4, got {embed_dim}")

            pos_dim = embed_dim // 4
            # Use float32 instead of float64 for MPS compatibility
            omega = torch.arange(pos_dim, dtype=torch.float32, device=device) / pos_dim
            omega = 1.0 / (temperature**omega)

            grid_h = torch.arange(height, dtype=torch.float32, device=device)
            grid_w = torch.arange(width, dtype=torch.float32, device=device)
            grid_h, grid_w = torch.meshgrid(grid_h, grid_w, indexing="ij")

            emb_h = grid_h.flatten().outer(omega)
            emb_w = grid_w.flatten().outer(omega)

            pos_embed = torch.cat(
                [emb_h.sin(), emb_h.cos(), emb_w.sin(), emb_w.cos()], dim=1
            )

            if cls_token:
                pos_embed = torch.cat(
                    [
                        torch.zeros(1, embed_dim, dtype=torch.float32, device=device),
                        pos_embed,
                    ],
                    dim=0,
                )

            return pos_embed.to(dtype)

        # Apply patch
        modeling_rt_detr_v2.build_2d_sinusoidal_position_embedding = (
            patched_build_2d_sinusoidal_position_embedding
        )

        logger.info("Applied MPS compatibility patch to transformers library")

    except ImportError:
        logger.debug("RT-DETR model not available, skipping patch")
    except Exception as e:
        logger.warning(f"Failed to apply MPS patch: {e}")
