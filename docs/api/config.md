# Configuration

Configuration is a single `Config` object assembled from mixins and loaded
from `SECONDBRAIN_*` environment variables (12-factor style). The `config()`
helper returns a cached singleton; a `.env` file in the working directory is
honored, and environment variables take precedence.

::: secondbrain.config
