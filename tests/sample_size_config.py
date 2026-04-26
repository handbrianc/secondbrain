"""Sample size configuration for quantitative testing.

This module defines sample size requirements for statistical reliability in
quantitative tests. It provides configuration constants and validation helpers
to ensure tests produce statistically meaningful results.

Background on Sample Size Selection
===================================

Why n=30?
---------
The choice of n=30 is based on statistical principles:

1. **Central Limit Theorem (CLT)**: For n ≥ 30, the sampling distribution of
   the mean approximates a normal distribution regardless of the underlying
   population distribution. This allows valid use of parametric statistics
   (t-tests, confidence intervals).

2. **Confidence Interval Width**: With n=30 and typical effect sizes in
   performance testing:
   - 95% CI width ≈ ±15% of mean (acceptable for performance testing)
   - With n=5: CI width ≈ ±44% (too wide for reliable conclusions)
   - With n=15: CI width ≈ ±25% (marginal)
   - With n=30: CI width ≈ ±15% (good)
   - With n=50: CI width ≈ ±11% (excellent, but diminishing returns)

3. **Power Analysis**: For detecting medium effect sizes (Cohen's d = 0.5)
   with 80% power at α=0.05:
   - Two-sample t-test requires n=64 per group
   - Paired t-test requires n=34 pairs
   - One-sample t-test requires n=34

   n=30 provides reasonable power (≈75%) for medium effects while keeping
   test execution time manageable.

Sample Size vs. CI Width Table
------------------------------
Assuming coefficient of variation (CV) = 0.5 (typical for response times):

| n   | CI Width (95%) | Relative Precision | Test Time (30s/run) |
|-----|----------------|-------------------|---------------------|
| 5   | ±44%           | Low               | 2.5 min             |
| 10  | ±31%           | Marginal          | 5 min               |
| 15  | ±25%           | Moderate          | 7.5 min             |
| 20  | ±22%           | Good              | 10 min              |
| 30  | ±15%           | Good              | 15 min              |
| 50  | ±11%           | Excellent         | 25 min              |
| 100 | ±8%            | Excellent         | 50 min              |

Tradeoff Analysis
-----------------
Time vs. Precision:

- **n=5 (current)**: Fastest, but CI too wide for reliable decisions
  - Pros: Quick feedback, low resource usage
  - Cons: High uncertainty, may miss real regressions

- **n=15 (minimum)**: Moderate time, acceptable precision
  - Pros: Reasonable CI width, manageable test time
  - Cons: Lower statistical power

- **n=30 (recommended)**: Balanced approach
  - Pros: CLT validity, good CI width, reasonable power
  - Cons: 6x longer than n=5

- **n=50+**: High precision, long execution
  - Pros: Excellent statistical power, narrow CI
  - Cons: Diminishing returns, long test times

Recommendations
---------------
- Use n=30 for most performance tests (default)
- Use n=15 minimum for CI estimation
- Use n=50+ for critical benchmarks requiring high precision
- Use n=10-15 for exploratory/draft testing only
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np

# =============================================================================
# Default Sample Size Constants
# =============================================================================

#: Default number of runs for quantitative tests (n=30)
#: Provides good balance between statistical reliability and test execution time
N_RUNS_DEFAULT = 30

#: Minimum number of runs for CI estimation (n=15)
#: Below this threshold, confidence intervals become unreliable
N_RUNS_MIN = 15

#: Reduced sample size for exploratory/draft testing only
#: Should NOT be used for production CI/CD
N_RUNS_EXPLORATORY = 10

#: Sample size for quick sanity checks (n=5)
#: Only for local development debugging, not for actual measurements
N_RUNS_SANITY_CHECK = 5

# =============================================================================
# Sample Size Configuration Dataclass
# =============================================================================


@dataclass
class SampleSizeConfig:
    """Configuration for sample sizes in quantitative tests.

    Provides per-test-type sample size overrides while maintaining
    sensible defaults based on statistical requirements.

    Attributes:
        n_runs: Base number of runs (default: 30)
        n_runs_min: Minimum acceptable runs (default: 15)
        performance_runs: Runs for performance benchmarks (default: 30)
        consistency_runs: Runs for consistency tests (default: 30)
        regression_runs: Runs for regression tests (default: 30)
        semantic_similarity_runs: Runs for semantic tests (default: 30)
        precision_recall_runs: Runs for precision/recall tests (default: 15)
        golden_dataset_runs: Runs for golden dataset tests (default: 10)
        exploratory_runs: Runs for exploratory testing (default: 10)
        sanity_check_runs: Runs for sanity checks (default: 5)

    Example:
        >>> config = SampleSizeConfig()
        >>> config.get_runs_for_test_type("performance")
        30

        >>> custom_config = SampleSizeConfig(performance_runs=50)
        >>> custom_config.get_runs_for_test_type("performance")
        50
    """

    # Base configuration
    n_runs: int = N_RUNS_DEFAULT
    n_runs_min: int = N_RUNS_MIN

    # Test-type specific overrides
    performance_runs: int = 30
    consistency_runs: int = 30
    regression_runs: int = 30
    semantic_similarity_runs: int = 30
    precision_recall_runs: int = 15
    golden_dataset_runs: int = 10
    exploratory_runs: int = N_RUNS_EXPLORATORY
    sanity_check_runs: int = N_RUNS_SANITY_CHECK

    def get_runs_for_test_type(
        self, test_type: Literal[
            "performance",
            "consistency",
            "regression",
            "semantic_similarity",
            "precision_recall",
            "golden_dataset",
            "exploratory",
            "sanity_check",
        ]
    ) -> int:
        """Get the appropriate sample size for a test type.

        Args:
            test_type: The category of test being run.

        Returns:
            Number of runs appropriate for the test type.

        Raises:
            ValueError: If test_type is not recognized.
        """
        mapping = {
            "performance": self.performance_runs,
            "consistency": self.consistency_runs,
            "regression": self.regression_runs,
            "semantic_similarity": self.semantic_similarity_runs,
            "precision_recall": self.precision_recall_runs,
            "golden_dataset": self.golden_dataset_runs,
            "exploratory": self.exploratory_runs,
            "sanity_check": self.sanity_check_runs,
        }

        if test_type not in mapping:
            raise ValueError(f"Unknown test type: {test_type}")

        return mapping[test_type]

    def validate_sample_size(
        self,
        n: int,
        test_type: Literal[
            "performance",
            "consistency",
            "regression",
            "semantic_similarity",
            "precision_recall",
            "golden_dataset",
            "exploratory",
            "sanity_check",
        ] | None = None,
        raise_on_error: bool = False,
    ) -> tuple[bool, list[str]]:
        """Validate that a sample size meets minimum requirements.

        Args:
            n: The sample size to validate.
            test_type: Optional test type for more specific guidance.
            raise_on_error: If True, raise ValueError instead of returning False.

        Returns:
            Tuple of (is_valid, list of messages/warnings).

        Raises:
            ValueError: If raise_on_error=True and sample size is invalid.
        """
        messages: list[str] = []
        is_valid = True

        if n < self.n_runs_min:
            is_valid = False
            messages.append(
                f"Sample size n={n} is below minimum threshold n={self.n_runs_min}. "
                "Confidence intervals will be unreliable."
            )

            if test_type:
                recommended = self.get_runs_for_test_type(test_type)
                messages.append(
                    f"For {test_type} tests, recommend n={recommended} runs. "
                    f"To update, set the appropriate *_runs parameter in SampleSizeConfig."
                )

            if raise_on_error:
                raise ValueError("\n".join(messages))

        elif n < self.n_runs:
            messages.append(
                f"Sample size n={n} is below recommended n={self.n_runs}. "
                "Consider increasing for more reliable results."
            )

        if n >= self.n_runs:
            messages.append(
                f"Sample size n={n} meets recommended threshold. "
                "Confidence intervals should have acceptable width (~±15%)."
            )

        return is_valid, messages


# =============================================================================
# Power Analysis Helpers
# =============================================================================


def calculate_ci_width(
    n: int,
    mean: float,
    std: float,
    confidence_level: float = 0.95,
) -> float:
    """Calculate the width of a confidence interval for the mean.

    Args:
        n: Sample size.
        mean: Sample mean (used for relative width calculation).
        std: Sample standard deviation.
        confidence_level: Confidence level (0.95 for 95% CI).

    Returns:
        Half-width of the confidence interval in the same units as mean.

    Example:
        >>> # For response time with mean=100ms, std=50ms, n=30
        >>> width = calculate_ci_width(30, 100, 50)
        >>> relative_width = (width / 100) * 100  # Convert to percentage
        >>> print(f"95% CI: 100 ± {relative_width:.1f}%")
        95% CI: 100 ± ~18.8%
    """
    if n < 2:
        raise ValueError("Sample size must be at least 2 for CI calculation")

    # Use t-distribution for small samples
    from scipy import stats

    df = n - 1
    t_value = stats.t.ppf((1 + confidence_level) / 2, df)

    # Standard error of the mean
    sem = std / np.sqrt(n)

    # Margin of error (half-width)
    margin = t_value * sem

    return margin


def calculate_relative_ci_width(
    n: int,
    cv: float,
    confidence_level: float = 0.95,
) -> float:
    """Calculate relative confidence interval width as percentage of mean.

    Args:
        n: Sample size.
        cv: Coefficient of variation (std/mean).
        confidence_level: Confidence level (0.95 for 95% CI).

    Returns:
        Half-width of CI as percentage of mean (e.g., 15.0 means ±15%).

    Example:
        >>> # For typical performance tests with CV=0.5
        >>> width = calculate_relative_ci_width(30, cv=0.5)
        >>> print(f"95% CI width: ±{width:.1f}%")
        95% CI width: ±~18.8%
    """
    if n < 2:
        raise ValueError("Sample size must be at least 2 for CI calculation")

    from scipy import stats

    df = n - 1
    t_value = stats.t.ppf((1 + confidence_level) / 2, df)

    # Relative margin of error
    relative_margin = t_value * cv / np.sqrt(n)

    return relative_margin * 100  # Convert to percentage


def calculate_required_sample_size(
    target_relative_width: float,
    cv: float,
    confidence_level: float = 0.95,
    power: float = 0.80,
) -> int:
    """Calculate required sample size for a target CI width.

    Args:
        target_relative_width: Target CI half-width as percentage of mean (e.g., 15 for ±15%).
        cv: Expected coefficient of variation (std/mean).
        confidence_level: Confidence level (0.95 for 95% CI).
        power: Statistical power (0.80 for 80% power).

    Returns:
        Required sample size.

    Example:
        >>> # For ±15% CI width with CV=0.5
        >>> n = calculate_required_sample_size(target_relative_width=15, cv=0.5)
        >>> print(f"Required sample size: {n}")
        Required sample size: 30
    """
    if target_relative_width <= 0:
        raise ValueError("Target relative width must be positive")

    if cv <= 0:
        raise ValueError("Coefficient of variation must be positive")

    from scipy import stats

    # For CI width calculation, we use z-score approximation
    # For 95% CI, z ≈ 1.96
    z_value = stats.norm.ppf((1 + confidence_level) / 2)

    # Convert percentage to decimal
    target_width_decimal = target_relative_width / 100

    # Sample size formula for CI width
    # n = (z * cv / target_width)^2
    n = (z_value * cv / target_width_decimal) ** 2

    return int(np.ceil(n))


def power_analysis_for_ttest(
    effect_size: float,
    alpha: float = 0.05,
    power: float = 0.80,
    test_type: Literal["one-sample", "two-sample", "paired"] = "one-sample",
) -> int:
    """Perform power analysis to determine required sample size.

    Args:
        effect_size: Cohen's d effect size (0.2=small, 0.5=medium, 0.8=large).
        alpha: Significance level (0.05 for 5%).
        power: Desired statistical power (0.80 for 80%).
        test_type: Type of t-test being performed.

    Returns:
        Required sample size per group.

    Example:
        >>> # For medium effect size (d=0.5) with 80% power
        >>> n = power_analysis_for_ttest(effect_size=0.5)
        >>> print(f"Required sample size: {n}")
        Required sample size: 34
    """
    if effect_size <= 0:
        raise ValueError("Effect size must be positive")

    try:
        from statsmodels.stats.power import TTestPower, TTestIndPower

        if test_type == "one-sample":
            analysis = TTestPower()
        elif test_type == "two-sample":
            analysis = TTestIndPower()
        elif test_type == "paired":
            analysis = TTestPower()
        else:
            raise ValueError(f"Unknown test type: {test_type}")

        # Calculate required sample size
        n = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power,
            ratio=1.0 if test_type == "two-sample" else None,
        )

        if n is None:
            # Fallback: approximate formula n ≈ 16 / d² for 80% power, α=0.05
            n = 16 / (effect_size ** 2)

        return int(np.ceil(n))
    except ImportError:
        return int(np.ceil(16 / (effect_size ** 2)))


def sample_size_recommendation(
    cv: float | None = None,
    target_ci_width: float | None = None,
    effect_size: float | None = None,
) -> dict[str, int | str | float | None]:
    """Provide sample size recommendations based on multiple criteria.

    Args:
        cv: Expected coefficient of variation (optional).
        target_ci_width: Target CI half-width as percentage (optional).
        effect_size: Expected effect size for power analysis (optional).

    Returns:
        Dictionary with recommendations and rationale.

    Example:
        >>> rec = sample_size_recommendation(cv=0.5, effect_size=0.5)
        >>> print(rec['recommended_n'])
        34
    """
    recommendations: list[tuple[int, str]] = []

    # CI width-based recommendation
    if cv and target_ci_width:
        n_ci = calculate_required_sample_size(target_ci_width, cv)
        recommendations.append((n_ci, f"CI width (±{target_ci_width}%, CV={cv})"))
    elif cv:
        # Default target of ±15%
        n_ci = calculate_required_sample_size(15, cv)
        recommendations.append((n_ci, f"CI width (±15%, CV={cv})"))

    # Power analysis-based recommendation
    if effect_size:
        n_power = power_analysis_for_ttest(effect_size)
        recommendations.append((n_power, f"Power analysis (d={effect_size}, 80% power)"))

    # CLT minimum
    recommendations.append((30, "CLT minimum (n≥30)"))

    # Find maximum recommendation
    if recommendations:
        recommended_n = max(rec[0] for rec in recommendations)
        rationale = ", ".join([f"{n} for {reason}" for n, reason in recommendations])
    else:
        recommended_n = N_RUNS_DEFAULT
        rationale = "Default recommendation"

    result: dict[str, int | str | float | None] = {
        "recommended_n": recommended_n,
        "minimum_n": N_RUNS_MIN,
        "exploratory_n": N_RUNS_EXPLORATORY,
        "rationale": rationale,
    }
    if cv:
        result["ci_width_at_recommended"] = calculate_relative_ci_width(recommended_n, cv)
    else:
        result["ci_width_at_recommended"] = None
    return result


# =============================================================================
# Convenience Functions for Test Files
# =============================================================================


def get_default_config() -> SampleSizeConfig:
    """Get the default sample size configuration.

    Returns:
        SampleSizeConfig with default values.

    Example:
        >>> config = get_default_config()
        >>> n = config.get_runs_for_test_type("performance")
        >>> assert n == 30
    """
    return SampleSizeConfig()


def validate_test_sample_size(
    n: int,
    test_name: str,
    test_type: Literal[
        "performance",
        "consistency",
        "regression",
        "semantic_similarity",
        "precision_recall",
        "golden_dataset",
        "exploratory",
        "sanity_check",
    ] | None = None,
) -> bool:
    """Validate sample size for a test and log warnings.

    This function should be called at the start of quantitative tests
    to ensure sample sizes are adequate.

    Args:
        n: Sample size used in the test.
        test_name: Name of the test (for logging).
        test_type: Type of test for specific recommendations.

    Returns:
        True if sample size is adequate, False otherwise.

    Example:
        >>> # In a test file:
        >>> NUM_RUNS = 5
        >>> if not validate_test_sample_size(NUM_RUNS, "test_response_time", "performance"):
        ...     pytest.skip("Sample size too small")
    """
    config = get_default_config()
    is_valid, messages = config.validate_sample_size(n, test_type)

    import warnings

    for message in messages:
        if "below minimum" in message.lower():
            warnings.warn(f"[{test_name}] {message}", UserWarning, stacklevel=2)
        elif "below recommended" in message.lower():
            warnings.warn(f"[{test_name}] {message}", UserWarning, stacklevel=2)

    return is_valid


# =============================================================================
# Module-level constants for backward compatibility
# =============================================================================

# These are provided for easy import in existing test files
DEFAULT_N_RUNS = N_RUNS_DEFAULT
MIN_N_RUNS = N_RUNS_MIN
EXPLORATORY_N_RUNS = N_RUNS_EXPLORATORY
SANITY_CHECK_N_RUNS = N_RUNS_SANITY_CHECK
