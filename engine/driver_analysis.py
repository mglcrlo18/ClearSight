"""
Multicollinearity-Proof Key Driver Analysis Engine (Johnson's Relative Weights) for ClearSight.

Features:
1. Singular Value Decomposition (SVD) orthogonalization resolving severe multicollinearity.
2. Exact R-squared variance decomposition summing to 100%.
3. Condition number monitoring with automated Tikhonov regularization guard (kappa > 1e5).
4. Survey weight integration for representative population key driver rankings.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


def johnsons_relative_weights(
    X: Union[np.ndarray, List[List[float]]],
    y: Union[np.ndarray, List[float]],
    feature_names: List[str],
    weights: Optional[Union[np.ndarray, List[float]]] = None,
    tikhonov_ridge: float = 1e-6
) -> Dict[str, Any]:
    """
    Computes Johnson's Relative Weights for a set of correlated predictors against a criterion variable.
    """
    X_mat = np.asarray(X, dtype=float)
    y_vec = np.asarray(y, dtype=float)
    n, p = X_mat.shape

    if len(y_vec) != n:
        raise ValueError(f"y length ({len(y_vec)}) must match X rows ({n}).")
    if len(feature_names) != p:
        raise ValueError(f"feature_names length ({len(feature_names)}) must match X columns ({p}).")

    if weights is None:
        w = np.ones(n, dtype=float)
    else:
        w = np.asarray(weights, dtype=float)

    # Filter out NaNs
    valid = ~np.isnan(y_vec) & ~np.any(np.isnan(X_mat), axis=1) & (w > 0)
    X_mat = X_mat[valid]
    y_vec = y_vec[valid]
    w = w[valid]
    n = len(y_vec)

    if n <= p:
        raise ValueError(f"Sample size ({n}) must be greater than number of predictors ({p}).")

    w_sum = float(np.sum(w))
    # Weighted standardization of y and X
    y_mean = float(np.sum(w * y_vec) / w_sum)
    y_std = float(np.sqrt(np.sum(w * ((y_vec - y_mean) ** 2)) / w_sum))
    if y_std <= 0:
        raise ValueError("Criterion y has zero variance.")
    y_stdzd = (y_vec - y_mean) / y_std

    X_mean = np.sum(w[:, np.newaxis] * X_mat, axis=0) / w_sum
    X_std = np.sqrt(np.sum(w[:, np.newaxis] * ((X_mat - X_mean) ** 2), axis=0) / w_sum)
    zero_var_idx = np.where(X_std <= 0)[0]
    if len(zero_var_idx) > 0:
        bad_feats = [feature_names[i] for i in zero_var_idx]
        raise ValueError(f"Predictors with zero variance detected: {bad_feats}")

    X_stdzd = (X_mat - X_mean) / X_std

    # Compute weighted correlation matrices
    # R_xx = (X^T W X) / w_sum
    # R_xy = (X^T W y) / w_sum
    W_diag = np.sqrt(w)[:, np.newaxis]
    X_weighted = X_stdzd * W_diag
    y_weighted = y_stdzd * np.sqrt(w)

    R_xx = (X_weighted.T @ X_weighted) / w_sum
    R_xy = (X_weighted.T @ y_weighted) / w_sum

    # Eigen-decomposition of R_xx
    eigenvals, Q = np.linalg.eigh(R_xx)

    # Condition number check
    max_eval = float(np.max(eigenvals))
    min_eval = float(np.min(eigenvals))
    is_regularized = False

    if min_eval <= 0 or (min_eval > 0 and (max_eval / min_eval) > 1e5):
        # Tikhonov regularization guard
        R_xx_reg = R_xx + (tikhonov_ridge * np.eye(p))
        eigenvals, Q = np.linalg.eigh(R_xx_reg)
        min_eval = float(np.min(eigenvals))
        is_regularized = True

    # Ensure strictly positive eigenvalues for sqrt
    eigenvals = np.clip(eigenvals, 1e-12, None)
    diag_sqrt = np.sqrt(eigenvals)
    diag_inv_sqrt = 1.0 / diag_sqrt

    # P matrix: orthogonal mapping transformation
    # P = Q @ diag(sqrt(evals)) @ Q^T
    P = (Q * diag_sqrt) @ Q.T
    # P_inv = Q @ diag(1/sqrt(evals)) @ Q^T
    P_inv = (Q * diag_inv_sqrt) @ Q.T

    # Regression of y on orthogonal variables Z:
    # beta_star = P_inv @ R_xy
    beta_star = P_inv @ R_xy

    # Raw relative weight: epsilon_j = sum_k (P_jk^2 * beta_star_k^2)
    P_sq = P ** 2
    beta_star_sq = beta_star ** 2
    raw_weights = P_sq @ beta_star_sq

    # Model R-squared
    r_squared = float(np.sum(raw_weights))
    r_squared = max(0.0, min(1.0, r_squared))

    # Normalized relative weights (percentage of R^2)
    if r_squared > 0:
        norm_weights = (raw_weights / r_squared) * 100.0
    else:
        norm_weights = np.zeros(p)

    # Format sorted driver ranking
    ranked_drivers = []
    order = np.argsort(-raw_weights)
    for rank_idx, feat_idx in enumerate(order, start=1):
        ranked_drivers.append({
            "rank": rank_idx,
            "feature": feature_names[feat_idx],
            "relative_weight_raw": round(float(raw_weights[feat_idx]), 6),
            "relative_importance_pct": round(float(norm_weights[feat_idx]), 2)
        })

    return {
        "analysis": "Key Driver Analysis (Johnson's Relative Weights)",
        "model_r_squared": round(r_squared, 4),
        "total_sample_size": n,
        "predictors_count": p,
        "is_tikhonov_regularized": is_regularized,
        "condition_number": round(float(max_eval / max(1e-12, min_eval)), 2),
        "drivers": ranked_drivers
    }


def compute_johnsons_relative_weights(
    data: Union[Any, np.ndarray, List[List[float]]],
    criterion: Union[str, np.ndarray, List[float]],
    predictors: Optional[List[str]] = None,
    weights: Optional[Union[np.ndarray, List[float], str]] = None,
    tikhonov_ridge: float = 1e-6
) -> Dict[str, Any]:
    """
    Universal wrapper accepting either (DataFrame, y_col, [x_cols]) or raw numpy arrays.
    Returns standardized keys matching both legacy test assertions and the analytical UI.
    """
    import pandas as pd
    if isinstance(data, pd.DataFrame):
        df = data
        if not isinstance(criterion, str) or criterion not in df.columns:
            raise ValueError(f"Criterion column '{criterion}' not found in DataFrame.")
        if not predictors or not all(p in df.columns for p in predictors):
            missing = [p for p in (predictors or []) if p not in df.columns]
            raise ValueError(f"Predictor columns missing from DataFrame: {missing}")

        X_mat = df[predictors].apply(pd.to_numeric, errors='coerce').to_numpy()
        y_vec = pd.to_numeric(df[criterion], errors='coerce').to_numpy()
        feat_names = list(predictors)

        w_vec = None
        if isinstance(weights, str) and weights in df.columns:
            w_vec = pd.to_numeric(df[weights], errors='coerce').fillna(1.0).to_numpy()
        elif weights is not None and not isinstance(weights, str):
            w_vec = np.asarray(weights, dtype=float)
    else:
        X_mat = np.asarray(data, dtype=float)
        y_vec = np.asarray(criterion, dtype=float)
        feat_names = predictors if predictors is not None else [f"X{i+1}" for i in range(X_mat.shape[1])]
        w_vec = np.asarray(weights, dtype=float) if weights is not None else None

    # Call mathematical SVD engine
    res = johnsons_relative_weights(
        X=X_mat,
        y=y_vec,
        feature_names=feat_names,
        weights=w_vec,
        tikhonov_ridge=tikhonov_ridge
    )

    # Bridge schema keys for full backward and forward compatibility
    res["weights"] = res["drivers"]
    res["r_squared"] = res["model_r_squared"]
    return res
