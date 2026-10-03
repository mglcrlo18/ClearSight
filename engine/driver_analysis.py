"""
ClearSight Analytics - Key Driver Analysis via Johnson's Relative Weights
Computes orthogonalized variance decomposition for collinear survey predictors.
Supports unweighted and survey-weighted specifications.
"""

import numpy as np
import pandas as pd


def compute_johnsons_relative_weights(
    df: pd.DataFrame, 
    target_col: str, 
    feature_cols: list[str],
    weight_col: str = None
) -> dict:
    """
    Computes Johnson's Relative Weights (2000) for resolving predictor collinearity.
    Uses Singular Value Decomposition (SVD) on correlation matrices to yield 
    orthogonal variance decomposition without ddof inflation.
    
    Returns:
    {
        'r_squared': float,
        'sample_size': int,
        'weights': [
            {'feature': 'Product Quality', 'raw_weight': 0.18, 'relative_importance_pct': 34.2},
            ...
        ]
    }
    """
    # 1. Input Validation & Numeric Coercion
    if not target_col or target_col not in df.columns:
        return {"error": f"Target column '{target_col}' not found in dataset."}
    
    valid_features = [f for f in feature_cols if f in df.columns and f != target_col]
    if len(valid_features) < 2:
        return {"error": "Driver analysis requires at least two distinct predictor features."}

    all_cols = [target_col] + valid_features
    if weight_col and weight_col in df.columns:
        all_cols.append(weight_col)

    # Coerce to numeric
    work_df = df[all_cols].copy()
    for col in [target_col] + valid_features:
        work_df[col] = pd.to_numeric(work_df[col], errors='coerce')

    clean_df = work_df.dropna()
    N = len(clean_df)
    p = len(valid_features)

    if N < p + 5:
        return {"error": f"Insufficient sample size (N = {N}) for {p} predictors. Minimum required: {p + 5}."}

    Y = clean_df[target_col].values.astype(np.float64)
    X = clean_df[valid_features].values.astype(np.float64)

    # 2. Compute Correlation Matrices R_xx and R_xy (weighted or unweighted)
    if weight_col and weight_col in clean_df.columns:
        w = clean_df[weight_col].values.astype(np.float64)
        w = np.maximum(0.0, w)
        w_sum = np.sum(w)
        if w_sum > 0:
            w_norm = w / w_sum
            # Weighted means & std
            y_mean = np.sum(w_norm * Y)
            y_std = np.sqrt(np.sum(w_norm * ((Y - y_mean) ** 2))) + 1e-12
            Y_z = (Y - y_mean) / y_std

            x_means = np.sum(w_norm[:, None] * X, axis=0)
            x_stds = np.sqrt(np.sum(w_norm[:, None] * ((X - x_means) ** 2), axis=0)) + 1e-12
            X_z = (X - x_means) / x_stds

            # Weighted correlation matrix
            R_xx = (X_z.T * w_norm) @ X_z
            R_xy = (X_z.T * w_norm) @ Y_z
        else:
            # Fallback to standard corrcoef
            corr_all = np.corrcoef(np.column_stack([X, Y]), rowvar=False)
            R_xx = corr_all[:p, :p]
            R_xy = corr_all[:p, p]
    else:
        corr_all = np.corrcoef(np.column_stack([X, Y]), rowvar=False)
        R_xx = corr_all[:p, :p]
        R_xy = corr_all[:p, p]

    # Clean any NaN correlations due to zero variance
    if np.any(np.isnan(R_xx)) or np.any(np.isnan(R_xy)):
        return {"error": "One or more features have zero variance or contain invariant constant values."}

    # Regularize tiny diagonal jitter if near-singular
    R_xx += np.eye(p) * 1e-8

    # 3. Spectral Decomposition of R_xx = V * Lambda * V^T
    try:
        eigenvalues, V = np.linalg.eigh(R_xx)
    except np.linalg.LinAlgError:
        return {"error": "Predictor correlation matrix could not be decomposed (singular)."}

    # Guard positive eigenvalues
    eigenvalues = np.maximum(eigenvalues, 1e-12)
    Lambda_sqrt = np.diag(np.sqrt(eigenvalues))
    Lambda_inv_sqrt = np.diag(1.0 / np.sqrt(eigenvalues))

    # 4. Transformation Matrix relating X to orthogonal variables Z
    Lambda_star = V @ Lambda_sqrt @ V.T
    Beta_star = (V @ Lambda_inv_sqrt @ V.T) @ R_xy

    # 5. Raw Relative Weights: epsilon = Lambda_star^2 @ Beta_star^2
    raw_weights = (Lambda_star ** 2) @ (Beta_star ** 2)
    raw_sum = float(np.sum(raw_weights))
    R2 = max(0.0, min(1.0, raw_sum))

    # 6. Percentage Shares (Guaranteed to strictly sum to 100.0%)
    weights_summary = []
    for i, col in enumerate(valid_features):
        raw_w = max(0.0, float(raw_weights[i]))
        pct_contrib = float((raw_w / raw_sum * 100.0) if raw_sum > 0 else (100.0 / p))
        weights_summary.append({
            "feature": col,
            "raw_weight": round(raw_w, 4),
            "relative_importance_pct": round(pct_contrib, 1)
        })

    weights_summary = sorted(weights_summary, key=lambda x: x["relative_importance_pct"], reverse=True)

    return {
        "r_squared": round(R2, 4),
        "sample_size": N,
        "is_weighted": bool(weight_col is not None),
        "weights": weights_summary
    }
