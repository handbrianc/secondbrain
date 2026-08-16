"""Position-embedding float64→float32 patch for transformers library.

The transformers RT-DETR v2 model's ``build_2d_sinusoidal_position_embedding``
uses ``torch.float64`` for intermediate arithmetic, which crashes on Apple
MPS (no float64 support) and is unnecessarily expensive on CUDA/CPU.

Solution: Monkey-patch the function at import time to use ``float32``
throughout.  The patch is applied unconditionally because float32 is safe
on every device and the precision loss (1e-7 on a 0-1 range) is negligible
for position embeddings.

Also clears the `@lru_cache` on the class-level static method so any
pre-patch cached results are invalidated.
"""

import logging
from typing import Any, cast

logger = logging.getLogger(__name__)

_patch_applied = False


def _clear_lru_cache_on_static_method(klass: type, method_name: str) -> None:
    """Clear ``lru_cache`` from a ``@staticmethod`` if the wrapper exposes cache_clear."""
    method = getattr(klass, method_name, None)
    if method is None:
        return
    cache_clear = getattr(method, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
        logger.debug("Cleared LRU cache for %s.%s", klass.__name__, method_name)


def patch_transformers_for_mps() -> None:
    """Patch transformers RT-DETR to use float32 instead of float64 for position embeddings.

    Safe to call multiple times (idempotent).  Must be called before any
    docling imports that trigger the RT-DETR layout model.
    """
    global _patch_applied
    if _patch_applied:
        return
    _patch_applied = True

    try:
        import torch
        from transformers.models.rt_detr_v2 import modeling_rt_detr_v2

        # ---- patched implementation using float32 ---------------------------------
        def patched_build_2d_sinusoidal_position_embedding(
            height: int,
            width: int,
            embed_dim: int = 256,
            temperature: float = 10000.0,
            cls_token: bool = False,
            device: torch.device | None = None,
            dtype: torch.dtype = torch.float32,
        ) -> torch.Tensor:
            """Patched version using ``float32`` instead of ``float64``.

            Args:
                height: Grid height in patches.
                width: Grid width in patches.
                embed_dim: Total embedding dimension (must be divisible by 4).
                temperature: Base for frequency decay.
                cls_token: If True, prepend zero row for CLS token.
                device: Target device.
                dtype: Output dtype.

            Returns:
                Position embedding tensor of shape ``(height * width [+1], embed_dim)``.
            """
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

        # ---- apply the patch ------------------------------------------------------
        cast(
            Any, modeling_rt_detr_v2
        ).build_2d_sinusoidal_position_embedding = (
            patched_build_2d_sinusoidal_position_embedding
        )

        # Clear any pre-patch cached results on the class-level LRU cache
        _clear_lru_cache_on_static_method(
            modeling_rt_detr_v2.RTDetrV2SinePositionEmbedding,
            "_cached_build_2d_sinusoidal_position_embedding",
        )

        logger.info("Applied float32 patch to transformers RT-DETR position embeddings")

    except ImportError:
        logger.debug("RT-DETR model not available, skipping patch")
    except Exception as e:
        logger.warning("Failed to apply transformers float32 patch: %s", e)
