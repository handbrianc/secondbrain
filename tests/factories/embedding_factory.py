"""Factory for generating deterministic fake embedding vectors in tests.

Provides lightweight, reproducible embedding vectors without requiring
the full MockEmbeddingGenerator machinery.
"""

from __future__ import annotations

import hashlib


def embedding_vector(dim: int = 1536, seed: int = 42) -> list[float]:
    """Generate a deterministic embedding vector of the given dimension.

    Uses a fixed seed combined with hashing so that calling
    ``embedding_vector(dim=n)`` twice yields identical results.  Vectors
    are normalised to unit length, making them suitable stand-ins for
    real embeddings in tests that only care about dimensionality and
    normalisation.

    Parameters
    ----------
    dim:
        Desired embedding dimensionality.  Defaults to 1536 (OpenAI
        text-embedding-3-small default).
    seed:
        Integer seed passed into the internal deterministic hash.
        Different seeds produce different vectors; the same seed always
        reproduces the same vector.  Default is 42.

    Returns
    -------
    list[float]
        A list of ``dim`` floats that sums to approximately 1.0 (L2-normalised).

    Examples
    --------
    >>> vec = embedding_vector(dim=384, seed=0)
    >>> len(vec)
    384
    >>> round(sum(v*v for v in vec)**0.5, 6)  # doctest: +ELLIPSIS
    1.0...

    Calling with the same arguments again gives an identical vector:

    >>> vec2 = embedding_vector(dim=384, seed=0)
    >>> vec == vec2
    True
    """
    import numpy as np

    # Deterministic bytes from seed – same seed → same bytes → same vector.
    hash_bytes = hashlib.sha256(str(seed).encode()).digest()

    # Unpack up to 32 uint8 values and rescale to [0, 1].
    unsigned_values = np.frombuffer(hash_bytes[:32], dtype=np.uint8).astype(np.float64)
    unsigned_values = unsigned_values / 255.0

    # Repeat the 32 values to fill the requested dimension.
    repeats_needed = (dim // 32) + 1
    tiled = np.tile(unsigned_values, repeats_needed)

    # Trim to exact dimension.
    vector = tiled[:dim].copy()

    # L2 normalise so the vector is unit-length.
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm

    return vector.tolist()


def zero_vector(dim: int = 1536) -> list[float]:
    """Return a zero-filled embedding vector of the requested dimension.

    Useful as a placeholder or for edge-case coverage where a neutral
    vector is required.

    Parameters
    ----------
    dim:
        Dimensionality of the returned vector.

    Returns
    -------
    list[float]
        A list of ``dim`` zeros.
    """
    return [0.0] * dim


def varied_embedding_vectors(
    count: int, dim: int = 1536, base_seed: int = 1
) -> list[list[float]]:
    """Generate ``count`` distinct deterministic embedding vectors.

    Each vector differs from the others because the underlying seed is
    incremented (``base_seed``, ``base_seed + 1``, …).  This is helpful
    when a test needs multiple *different* embeddings but still demands
    reproducibility across test runs.

    Parameters
    ----------
    count:
        How many distinct vectors to produce.
    dim:
        Dimensionality of each vector.
    base_seed:
        Seed for the first vector.  Subsequent vectors use
        ``base_seed + 1``, ``base_seed + 2``, …

    Returns
    -------
    list[list[float]]
        A list of ``count`` vectors, each of length ``dim``.
    """
    return [embedding_vector(dim=dim, seed=base_seed + i) for i in range(count)]


__all__ = [
    "embedding_vector",
    "varied_embedding_vectors",
    "zero_vector",
]
