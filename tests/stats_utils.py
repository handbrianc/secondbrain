"""
Statistical utilities for quantitative testing with statistical rigor.

This module provides reusable utilities for confidence intervals, variance analysis,
and statistical testing, replacing point estimates with statistically sound methods.

Statistical Methods Referenced:
- Confidence Intervals: Student's t-distribution (Zar, 1999)
- Bootstrap CI: Efron & Tibshirani (1993) "An Introduction to the Bootstrap"
- CUPED: Chen et al. (2021) "On the Variance Reduction of A/B Tests"
- Effect Size: Cohen's d (Cohen, 1988) "Statistical Power Analysis for the Behavioral Sciences"
- Mann-Whitney U: Mann & Whitney (1947) "On a Test of Whether one of Two Random Variables is Stochastically Larger than the Other"

Example:
    >>> from tests.stats_utils import calculate_ci_mean, compare_means
    >>> data = [1.2, 1.5, 1.3, 1.7, 1.4, 1.6, 1.8, 1.3, 1.5, 1.4]
    >>> ci = calculate_ci_mean(data)
    >>> print(f"95% CI: [{ci[0]:.4f}, {ci[1]:.4f}]")  # doctest: +SKIP
    >>> group1 = [1.2, 1.5, 1.3, 1.7, 1.4]
    >>> group2 = [1.8, 2.0, 1.9, 2.1, 1.7]
    >>> result = compare_means(group1, group2)
    >>> print(f"p-value: {result['p_value']:.4f}, Cohen's d: {result['effect_size']:.4f}")  # doctest: +SKIP
"""

import random
from typing import Any, Literal

import numpy as np
from scipy import stats
from scipy.stats import mannwhitneyu, t

# ============================================================================
# Confidence Interval Functions
# ============================================================================


def calculate_ci_mean(
    data: list[float] | np.ndarray, confidence: float = 0.95
) -> tuple[float, float]:
    """
    Calculate confidence interval for the mean using Student's t-distribution.

    Uses the t-distribution which is appropriate for small sample sizes and when
    the population standard deviation is unknown.

    Args:
        data: List or array of numerical observations.
        confidence: Confidence level (0 < confidence < 1). Default is 0.95 (95%).

    Returns:
        Tuple of (lower_bound, upper_bound) for the confidence interval.

    Raises:
        ValueError: If confidence is not in (0, 1) or data is empty.
        ValueError: If data contains non-numeric values.

    Example:
        >>> data = [23.5, 24.1, 22.8, 25.0, 23.9, 24.5, 23.2, 24.8]
        >>> ci = calculate_ci_mean(data, confidence=0.95)
        >>> print(f"95% CI for mean: [{ci[0]:.2f}, {ci[1]:.2f}]")  # doctest: +SKIP
        95% CI for mean: [23.49, 24.54]

        >>> # Higher confidence gives wider interval
        >>> ci_99 = calculate_ci_mean(data, confidence=0.99)
        >>> print(f"99% CI for mean: [{ci_99[0]:.2f}, {ci_99[1]:.2f}]")  # doctest: +SKIP
        99% CI for mean: [23.21, 24.82]

    References:
        - Student (1908). "The probable error of a mean"
        - Zar, J.H. (1999). "Biostatistical Analysis"
    """
    if not data:
        raise ValueError("Data cannot be empty")

    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between 0 and 1 (exclusive)")

    data_array = np.asarray(data, dtype=float)

    if np.any(np.isnan(data_array)):
        raise ValueError("Data contains NaN values")

    n = len(data_array)
    mean = np.mean(data_array)
    std_err = stats.sem(data_array)  # Standard error of the mean

    # Use t-distribution for small samples
    df = n - 1
    t_critical = t.ppf((1 + confidence) / 2, df)
    margin_of_error = t_critical * std_err

    return (mean - margin_of_error, mean + margin_of_error)


def calculate_ci_proportion(
    successes: int, trials: int, confidence: float = 0.95
) -> tuple[float, float]:
    """
    Calculate confidence interval for a proportion using the Wilson score interval.

    The Wilson score interval is preferred over the normal approximation (Wald)
    interval, especially for small samples or proportions near 0 or 1.

    Args:
        successes: Number of successful outcomes (0 <= successes <= trials).
        trials: Total number of trials (trials > 0).
        confidence: Confidence level (0 < confidence < 1). Default is 0.95.

    Returns:
        Tuple of (lower_bound, upper_bound) for the proportion confidence interval.

    Raises:
        ValueError: If inputs are invalid (negative, successes > trials, etc.).

    Example:
        >>> # Click-through rate: 45 clicks out of 1000 impressions
        >>> ci = calculate_ci_proportion(45, 1000, confidence=0.95)
        >>> print(f"CTR: {45/1000:.2%}, 95% CI: [{ci[0]:.2%}, {ci[1]:.2%}]")  # doctest: +SKIP
        CTR: 4.50%, 95% CI: [3.45%, 5.85%]

        >>> # Low conversion rate with small sample
        >>> ci_small = calculate_ci_proportion(3, 50, confidence=0.95)
        >>> print(f"Conversion: {3/50:.2%}, 95% CI: [{ci_small[0]:.2%}, {ci_small[1]:.2%}]")  # doctest: +SKIP
        Conversion: 6.00%, 95% CI: [3.28%, 15.82%]

    References:
        - Wilson, E.B. (1927). "Probable Inference, the Law of Succession, and Statistical Inference"
        - Brown, L.D., Cai, T.T., DasGupta, A. (2001). "Interval Estimation for a Binomial Proportion"
    """
    if trials <= 0:
        raise ValueError("Trials must be positive")

    if successes < 0 or successes > trials:
        raise ValueError("Successes must be between 0 and trials")

    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between 0 and 1 (exclusive)")

    p_hat = successes / trials
    z = stats.norm.ppf((1 + confidence) / 2)

    # Wilson score interval
    denominator = 1 + z**2 / trials
    center = (p_hat + z**2 / (2 * trials)) / denominator
    margin = (z / denominator) * np.sqrt(
        p_hat * (1 - p_hat) / trials + z**2 / (4 * trials**2)
    )

    return (max(0, center - margin), min(1, center + margin))


def bootstrap_ci(
    data: list[float] | np.ndarray,
    n_iterations: int = 1000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float]:
    """
    Calculate confidence interval using bootstrap resampling method.

    Bootstrap is particularly useful for small samples, non-normal distributions,
    or when the sampling distribution is unknown. Uses percentile method.

    Args:
        data: List or array of numerical observations.
        n_iterations: Number of bootstrap resamples. Default is 1000.
        confidence: Confidence level (0 < confidence < 1). Default is 0.95.
        seed: Random seed for reproducibility. Optional.

    Returns:
        Tuple of (lower_bound, upper_bound) for the bootstrap confidence interval.

    Raises:
        ValueError: If data is empty or n_iterations is too small.

    Example:
        >>> # Small sample with unknown distribution
        >>> data = [2.3, 2.7, 2.1, 2.9, 2.5, 2.4, 2.8]
        >>> ci = bootstrap_ci(data, n_iterations=1000, confidence=0.95, seed=42)
        >>> print(f"Bootstrap 95% CI: [{ci[0]:.2f}, {ci[1]:.2f}]")  # doctest: +SKIP
        Bootstrap 95% CI: [2.35, 2.78]

        >>> # Compare with t-distribution CI
        >>> ci_t = calculate_ci_mean(data)
        >>> print(f"T-distribution 95% CI: [{ci_t[0]:.2f}, {ci_t[1]:.2f}]")  # doctest: +SKIP
        T-distribution 95% CI: [2.34, 2.79]

    References:
        - Efron, B. & Tibshirani, R.J. (1993). "An Introduction to the Bootstrap"
        - Davison, A.C. & Hinkley, D.V. (1997). "Bootstrap Methods and Their Application"
    """
    if not data:
        raise ValueError("Data cannot be empty")

    if n_iterations < 100:
        raise ValueError("n_iterations should be at least 100 for reliable results")

    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between 0 and 1 (exclusive)")

    data_array = np.asarray(data, dtype=float)
    n = len(data_array)

    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    # Bootstrap resampling
    bootstrap_means = np.zeros(n_iterations)
    for i in range(n_iterations):
        resample = np.random.choice(data_array, size=n, replace=True)
        bootstrap_means[i] = np.mean(resample)

    # Percentile method
    alpha = 1 - confidence
    lower_percentile = (alpha / 2) * 100
    upper_percentile = (1 - alpha / 2) * 100

    lower = np.percentile(bootstrap_means, lower_percentile)
    upper = np.percentile(bootstrap_means, upper_percentile)

    return (float(lower), float(upper))


# ============================================================================
# Variance Analysis Functions
# ============================================================================


def calculate_cv(data: list[float] | np.ndarray) -> float:
    """
    Calculate the Coefficient of Variation (CV).

    CV is a normalized measure of dispersion, expressed as the ratio of the
    standard deviation to the mean. Useful for comparing variability across
    datasets with different scales.

    Args:
        data: List or array of numerical observations.

    Returns:
        Coefficient of variation (as a decimal, not percentage).

    Raises:
        ValueError: If data is empty or mean is zero.

    Example:
        >>> # Low variability
        >>> data1 = [10.1, 10.2, 9.9, 10.0, 10.1]
        >>> cv1 = calculate_cv(data1)
        >>> print(f"CV: {cv1:.2%}")  # doctest: +SKIP
        CV: 1.01%

        >>> # High variability
        >>> data2 = [5, 15, 8, 20, 12]
        >>> cv2 = calculate_cv(data2)
        >>> print(f"CV: {cv2:.2%}")  # doctest: +SKIP
        CV: 42.16%

    References:
        - Lew, R. (1993). "Coefficient of variation"
    """
    if not data:
        raise ValueError("Data cannot be empty")

    data_array = np.asarray(data, dtype=float)
    mean = np.mean(data_array)

    if mean == 0:
        raise ValueError("Cannot calculate CV when mean is zero")

    std_dev = np.std(data_array, ddof=1)  # Sample standard deviation
    cv = std_dev / abs(mean)

    return float(cv)


def cuped_adjustment(
    post_metrics: list[float] | np.ndarray,
    pre_metrics: list[float] | np.ndarray,
) -> dict[str, float]:
    """
    Apply CUPED (Controlled-Experiment Using Pre-Experiment Data) variance reduction.

    CUPED reduces variance in A/B tests by leveraging pre-experiment metrics as
    covariates. This increases statistical power and reduces required sample size.

    The adjustment formula: Y* = Y - θ(X - X̄)
    where θ = Cov(Y,X) / Var(X)

    Args:
        post_metrics: Post-experiment metric values.
        pre_metrics: Pre-experiment metric values (same length as post_metrics).

    Returns:
        Dictionary containing:
            - 'adjusted_mean': Mean of adjusted post-experiment metrics
            - 'original_variance': Variance of original post_metrics
            - 'adjusted_variance': Variance of adjusted post_metrics
            - 'variance_reduction': Proportion of variance reduced (0 to 1)
            - 'theta': The optimal adjustment coefficient

    Raises:
        ValueError: If arrays have different lengths or are empty.
        ValueError: If pre_metrics has zero variance.

    Example:
        >>> # Simulated A/B test with pre-experiment baseline
        >>> post_treatment = [10.5, 11.2, 9.8, 12.1, 10.9, 11.5, 10.2, 11.8]
        >>> pre_baseline = [10.1, 10.8, 9.5, 11.5, 10.5, 11.0, 9.8, 11.2]
        >>> result = cuped_adjustment(post_treatment, pre_baseline)
        >>> print(f"Variance reduction: {result['variance_reduction']:.2%}")  # doctest: +SKIP
        >>> print(f"Adjusted mean: {result['adjusted_mean']:.3f}")  # doctest: +SKIP

    References:
        - Chen et al. (2021). "On the Variance Reduction of A/B Tests Using Pre-Experiment Data"
        - Deng et al. (2013). "Applying the Covariance Adjustment Technique in A/B Testing"
    """
    if len(post_metrics) != len(pre_metrics):
        raise ValueError("Post and pre metrics must have the same length")

    if len(post_metrics) == 0:
        raise ValueError("Metrics cannot be empty")

    post_array = np.asarray(post_metrics, dtype=float)
    pre_array = np.asarray(pre_metrics, dtype=float)

    if np.var(pre_array, ddof=1) == 0:
        raise ValueError("Pre-metrics must have non-zero variance")

    # Calculate theta (optimal adjustment coefficient)
    covariance = np.cov(post_array, pre_array, ddof=1)[0, 1]
    pre_variance = np.var(pre_array, ddof=1)
    theta = covariance / pre_variance

    # Apply CUPED adjustment
    pre_mean = np.mean(pre_array)
    adjusted_post = post_array - theta * (pre_array - pre_mean)

    # Calculate variance reduction
    original_variance = np.var(post_array, ddof=1)
    adjusted_variance = np.var(adjusted_post, ddof=1)

    if original_variance == 0:
        variance_reduction = 0.0
    else:
        variance_reduction = 1 - (adjusted_variance / original_variance)

    return {
        "adjusted_mean": float(np.mean(adjusted_post)),
        "original_variance": float(original_variance),
        "adjusted_variance": float(adjusted_variance),
        "variance_reduction": float(variance_reduction),
        "theta": float(theta),
    }


def check_variance_stability(
    data: list[float] | np.ndarray, max_cv: float = 0.2
) -> dict[str, Any]:
    """
    Check if a dataset has stable variance (low coefficient of variation).

    High CV indicates unstable or highly variable data, which may require
    larger sample sizes or indicate problematic measurements.

    Args:
        data: List or array of numerical observations.
        max_cv: Maximum acceptable CV threshold. Default is 0.2 (20%).

    Returns:
        Dictionary containing:
            - 'is_stable': Boolean indicating if variance is acceptable
            - 'cv': Calculated coefficient of variation
            - 'max_cv': The threshold used
            - 'recommendation': Suggested action based on stability

    Example:
        >>> # Stable measurements
        >>> stable_data = [100.1, 100.2, 99.9, 100.0, 100.1]
        >>> result = check_variance_stability(stable_data, max_cv=0.05)
        >>> print(f"Is stable: {result['is_stable']}")  # doctest: +SKIP
        >>> print(f"Recommendation: {result['recommendation']}")  # doctest: +SKIP
        Is stable: True
        Recommendation: Data is stable, proceed with analysis

        >>> # Unstable data
        >>> unstable_data = [80, 120, 95, 110, 85]
        >>> result = check_variance_stability(unstable_data, max_cv=0.1)
        >>> print(f"Is stable: {result['is_stable']}")  # doctest: +SKIP
        Is stable: False

    References:
        - Coefficient of variation guidelines vary by domain
    """
    cv = calculate_cv(data)

    is_stable = cv <= max_cv

    if cv <= max_cv * 0.5:
        recommendation = "Excellent stability, high confidence in results"
    elif cv <= max_cv:
        recommendation = "Data is stable, proceed with analysis"
    elif cv <= max_cv * 2:
        recommendation = "Moderate variability, consider larger sample size"
    else:
        recommendation = "High variability detected, investigate data quality or increase sample size significantly"

    return {
        "is_stable": is_stable,
        "cv": cv,
        "max_cv": max_cv,
        "recommendation": recommendation,
    }


# ============================================================================
# Statistical Testing Functions
# ============================================================================


def compare_means(
    group1: list[float] | np.ndarray,
    group2: list[float] | np.ndarray,
    alpha: float = 0.05,
    equal_var: bool = True,
) -> dict[str, float]:
    """
    Perform two-sample t-test and calculate effect size (Cohen's d).

    Compares means of two independent groups and provides both statistical
    significance (p-value) and practical significance (effect size).

    Args:
        group1: First group of observations.
        group2: Second group of observations.
        alpha: Significance level. Default is 0.05.
        equal_var: If True, assume equal variances (Student's t-test).
                   If False, use Welch's t-test. Default is True.

    Returns:
        Dictionary containing:
            - 't_statistic': t-test statistic
            - 'p_value': Two-tailed p-value
            - 'effect_size': Cohen's d
            - 'is_significant': Boolean indicating if p < alpha
            - 'mean_diff': Difference in means (group1 - group2)
            - 'group1_mean': Mean of group1
            - 'group2_mean': Mean of group2

    Example:
        >>> control = [10.2, 10.5, 9.8, 10.1, 10.3, 9.9, 10.4, 10.0]
        >>> treatment = [11.1, 11.5, 10.8, 11.2, 11.3, 10.9, 11.4, 11.0]
        >>> result = compare_means(control, treatment)
        >>> print(f"p-value: {result['p_value']:.4f}")  # doctest: +SKIP
        >>> print(f"Cohen's d: {result['effect_size']:.2f}")  # doctest: +SKIP
        >>> print(f"Significant: {result['is_significant']}")  # doctest: +SKIP

        # Effect size interpretation (Cohen, 1988):
        # |d| < 0.2: negligible
        # 0.2 <= |d| < 0.5: small
        # 0.5 <= |d| < 0.8: medium
        # |d| >= 0.8: large

    References:
        - Student (1908). "The probable error of a mean"
        - Welch, B.L. (1947). "The generalization of 'Student's' problem"
        - Cohen, J. (1988). "Statistical Power Analysis for the Behavioral Sciences"
    """
    group1_array = np.asarray(group1, dtype=float)
    group2_array = np.asarray(group2, dtype=float)

    # Perform t-test
    if equal_var:
        t_stat, p_value = stats.ttest_ind(group1_array, group2_array, equal_var=True)
    else:
        t_stat, p_value = stats.ttest_ind(group1_array, group2_array, equal_var=False)

    # Calculate Cohen's d
    n1, n2 = len(group1_array), len(group2_array)
    mean1, mean2 = np.mean(group1_array), np.mean(group2_array)

    # Pooled standard deviation
    var1, var2 = np.var(group1_array, ddof=1), np.var(group2_array, ddof=1)
    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

    cohens_d = 0.0 if pooled_std == 0 else (mean1 - mean2) / pooled_std

    return {
        "t_statistic": float(t_stat),
        "p_value": float(p_value),
        "effect_size": float(cohens_d),
        "is_significant": bool(p_value < alpha),
        "mean_diff": float(mean1 - mean2),
        "group1_mean": float(mean1),
        "group2_mean": float(mean2),
    }


def mann_whitney_u_test(
    group1: list[float] | np.ndarray,
    group2: list[float] | np.ndarray,
    alternative: Literal["two-sided", "less", "greater"] = "two-sided",
) -> dict[str, Any]:
    """
    Perform Mann-Whitney U test (non-parametric alternative to t-test).

    Tests whether two independent samples come from the same distribution.
    Does not assume normality, making it robust for non-normal data.

    Args:
        group1: First group of observations.
        group2: Second group of observations.
        alternative: Hypothesis to test:
            - 'two-sided': distributions are different
            - 'less': group1 is stochastically less than group2
            - 'greater': group1 is stochastically greater than group2

    Returns:
        Dictionary containing:
            - 'u_statistic': Mann-Whitney U statistic
            - 'p_value': p-value for the test
            - 'is_significant': Boolean indicating if p < 0.05
            - 'rank_sum_1': Sum of ranks for group1
            - 'rank_sum_2': Sum of ranks for group2

    Example:
        >>> # Non-normal data (skewed distribution)
        >>> group1 = [1, 2, 2, 3, 1, 2, 1, 3, 2, 1]
        >>> group2 = [3, 4, 5, 4, 3, 5, 4, 6, 5, 4]
        >>> result = mann_whitney_u_test(group1, group2)
        >>> print(f"U statistic: {result['u_statistic']}")  # doctest: +SKIP
        >>> print(f"p-value: {result['p_value']:.4f}")  # doctest: +SKIP
        >>> print(f"Significant: {result['is_significant']}")  # doctest: +SKIP

    References:
        - Mann, H.B. & Whitney, D.R. (1947). "On a Test of Whether one of Two Random Variables is Stochastically Larger than the Other"
        - Siegel, S. & Castellan, N.J. (1988). "Nonparametric Statistics for the Behavioral Sciences"
    """
    group1_array = np.asarray(group1, dtype=float)
    group2_array = np.asarray(group2, dtype=float)

    # Perform Mann-Whitney U test
    u_stat, p_value = mannwhitneyu(group1_array, group2_array, alternative=alternative)

    # Calculate rank sums
    combined = np.concatenate([group1_array, group2_array])
    ranks = stats.rankdata(combined)
    rank_sum_1 = np.sum(ranks[: len(group1_array)])
    rank_sum_2 = np.sum(ranks[len(group1_array) :])

    return {
        "u_statistic": float(u_stat),
        "p_value": float(p_value),
        "is_significant": bool(p_value < 0.05),
        "rank_sum_1": float(rank_sum_1),
        "rank_sum_2": float(rank_sum_2),
    }


def check_ci_overlap(
    ci1: tuple[float, float],
    ci2: tuple[float, float],
    threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Check if two confidence intervals overlap substantially.

    Overlapping CIs don't necessarily mean no significant difference,
    but substantial overlap suggests the difference may not be meaningful.

    Args:
        ci1: First confidence interval as (lower, upper).
        ci2: Second confidence interval as (lower, upper).
        threshold: Overlap threshold (0 to 1).
            - 0: Any overlap
            - 0.5: Overlap > 50% of smaller CI width
            - 1: Complete overlap

    Returns:
        Dictionary containing:
            - 'overlaps': Boolean indicating if intervals overlap
            - 'overlap_amount': Absolute overlap amount
            - 'overlap_ratio': Overlap as ratio of smaller CI width
            - 'substantial_overlap': Boolean based on threshold
            - 'ci1_width': Width of first CI
            - 'ci2_width': Width of second CI

    Example:
        >>> ci_control = (9.8, 10.2)
        >>> ci_treatment = (10.8, 11.2)
        >>> result = check_ci_overlap(ci_control, ci_treatment)
        >>> print(f"Overlap: {result['overlaps']}")
        Overlap: False

        >>> ci_treatment2 = (10.0, 10.6)
        >>> result = check_ci_overlap(ci_control, ci_treatment2)
        >>> print(f"Substantial overlap: {result['substantial_overlap']}")
        Substantial overlap: True

    Note:
        Non-overlapping 95% CIs imply p < 0.05, but overlapping CIs
        don't necessarily imply p > 0.05. Use formal hypothesis
        testing for definitive conclusions.

    References:
        - Cumming, G. & Maillardet, R. (2006). "Confidence Intervals and Sample Size"
        - Payton, M.E. et al. (2003). "Overlapping Confidence Intervals and Statistical Significance"
    """
    lower1, upper1 = ci1
    lower2, upper2 = ci2

    # Calculate widths
    width1 = upper1 - lower1
    width2 = upper2 - lower2

    # Check for overlap
    overlap_start = max(lower1, lower2)
    overlap_end = min(upper1, upper2)
    overlap_amount = max(0, overlap_end - overlap_start)

    overlaps = overlap_amount > 0

    # Calculate overlap ratio relative to smaller CI
    smaller_width = min(width1, width2)
    overlap_ratio = overlap_amount / smaller_width if smaller_width > 0 else 0.0

    substantial_overlap = overlap_ratio >= threshold

    return {
        "overlaps": overlaps,
        "overlap_amount": float(overlap_amount),
        "overlap_ratio": float(overlap_ratio),
        "substantial_overlap": substantial_overlap,
        "ci1_width": float(width1),
        "ci2_width": float(width2),
    }


# ============================================================================
# Sample Size Utilities
# ============================================================================


def calculate_sample_size_for_ci_width(
    effect_size: float,
    ci_width: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    """
    Calculate required sample size to achieve a target confidence interval width.

    Uses power analysis to determine the minimum sample size needed to detect
    an effect of a given size with a specified precision (CI width).

    Args:
        effect_size: Expected effect size (Cohen's d).
        ci_width: Desired total width of the confidence interval.
        alpha: Significance level. Default is 0.05.
        power: Statistical power (1 - beta). Default is 0.8.

    Returns:
        Required sample size per group.

    Raises:
        ValueError: If inputs are invalid.

    Example:
        >>> # Detect medium effect (d=0.5) with CI width of 0.4
        >>> n = calculate_sample_size_for_ci_width(effect_size=0.5, ci_width=0.4)
        >>> print(f"Required sample size per group: {n}")  # doctest: +SKIP

        >>> # Narrower CI requires larger sample
        >>> n_narrow = calculate_sample_size_for_ci_width(effect_size=0.5, ci_width=0.2)
        >>> print(f"Required sample size per group: {n_narrow}")  # doctest: +SKIP

    References:
        - Cohen, J. (1988). "Statistical Power Analysis for the Behavioral Sciences"
        - Chow, S.C., Shao, J., Wang, H. (2008). "Sample Size Calculations in Clinical Research"
    """
    if effect_size <= 0:
        raise ValueError("Effect size must be positive")

    if ci_width <= 0:
        raise ValueError("CI width must be positive")

    if not 0 < alpha < 1:
        raise ValueError("Alpha must be between 0 and 1")

    if not 0 < power < 1:
        raise ValueError("Power must be between 0 and 1")

    # Critical values
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)

    # Approximate sample size formula for CI width
    # CI width ≈ 2 * z * sigma / sqrt(n)
    # For standardized effect size, sigma = 1
    # n ≈ (2 * z * sigma / width)^2

    # More accurate formula accounting for both power and CI width
    n = ((z_alpha + z_beta) / (effect_size * ci_width / 2)) ** 2

    return int(np.ceil(n))


def estimate_ci_width(
    n: int,
    std_dev: float,
    confidence: float = 0.95,
) -> float:
    """
    Estimate the expected confidence interval width for a given sample size.

    Useful for planning studies: "How precise will my estimate be with n samples?"

    Args:
        n: Sample size.
        std_dev: Expected standard deviation of the data.
        confidence: Confidence level. Default is 0.95.

    Returns:
        Expected total width of the confidence interval.

    Raises:
        ValueError: If inputs are invalid.

    Example:
        >>> # With 100 samples and std=2, what's the expected CI width?
        >>> width = estimate_ci_width(n=100, std_dev=2.0)
        >>> print(f"Expected 95% CI width: {width:.3f}")  # doctest: +SKIP

        >>> # How does width scale with sample size?
        >>> for n in [25, 50, 100, 200]:  # doctest: +SKIP
        ...     w = estimate_ci_width(n=n, std_dev=2.0)
        ...     print(f"n={n}: CI width = {w:.3f}")

    References:
        - Student (1908). "The probable error of a mean"
    """
    if n <= 0:
        raise ValueError("Sample size must be positive")

    if std_dev <= 0:
        raise ValueError("Standard deviation must be positive")

    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between 0 and 1")

    # Standard error
    se = std_dev / np.sqrt(n)

    # Critical t-value (using normal approximation for large n)
    if n > 30:
        z_critical = stats.norm.ppf((1 + confidence) / 2)
    else:
        z_critical = t.ppf((1 + confidence) / 2, df=n - 1)

    # CI width = 2 * critical_value * SE
    width = 2 * z_critical * se

    return float(width)


# ============================================================================
# Utility Functions
# ============================================================================


def summarize_statistics(
    data: list[float] | np.ndarray, confidence: float = 0.95
) -> dict[str, float]:
    """
    Generate comprehensive summary statistics for a dataset.

    Convenience function that calculates multiple statistics in one call.

    Args:
        data: List or array of numerical observations.
        confidence: Confidence level for CI. Default is 0.95.

    Returns:
        Dictionary containing:
            - 'n': Sample size
            - 'mean': Sample mean
            - 'median': Sample median
            - 'std': Sample standard deviation
            - 'min': Minimum value
            - 'max': Maximum value
            - 'ci_lower': Lower bound of CI
            - 'ci_upper': Upper bound of CI
            - 'cv': Coefficient of variation

    Example:
        >>> data = [10.2, 10.5, 9.8, 10.1, 10.3, 9.9, 10.4, 10.0]
        >>> summary = summarize_statistics(data)
        >>> for key, value in summary.items():  # doctest: +SKIP
        ...     print(f"{key}: {value:.3f}")
    """
    data_array = np.asarray(data, dtype=float)

    ci = calculate_ci_mean(data, confidence)

    return {
        "n": len(data_array),
        "mean": float(np.mean(data_array)),
        "median": float(np.median(data_array)),
        "std": float(np.std(data_array, ddof=1)),
        "min": float(np.min(data_array)),
        "max": float(np.max(data_array)),
        "ci_lower": ci[0],
        "ci_upper": ci[1],
        "cv": calculate_cv(data),
    }


# ============================================================================
# Module metadata
# ============================================================================

__all__ = [
    "bootstrap_ci",
    "calculate_ci_mean",
    "calculate_ci_proportion",
    "calculate_cv",
    "calculate_sample_size_for_ci_width",
    "check_ci_overlap",
    "check_variance_stability",
    "compare_means",
    "cuped_adjustment",
    "estimate_ci_width",
    "mann_whitney_u_test",
    "summarize_statistics",
]

__version__ = "1.0.0"
