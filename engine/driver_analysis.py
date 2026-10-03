"""
Sukat by Lunsad - Key Driver Analysis via Johnson's Relative Weights
Resolves multicollinearity without the exponential O(2^k) complexity of Shapley regression.
"""

import numpy as np
import pandas as pd

def compute_johnsons_relative_weights(df: pd.DataFrame, target_col: str, feature_cols: list[str]) -> dict:
    """
    Computes Johnson's Relative Weights (2000) for resolving predictor collinearity.
    Uses Singular Value Decomposition (SVD) on correlation matrices to yield 
    orthogonal variance decomposition in milliseconds.
    
    Returns:
    {
        'r_squared': float,
        'weights': [
            {'feature': 'Product Quality', 'raw_weight': 0.18, 'relative_pct': 34.2},
            ...
        ]
    }
    """
    # Clean complete cases
    cols = [target_col] + feature_cols
    clean_df = df[cols].dropna()
    N = len(clean_df)
    p = len(feature_cols)
    
    if N < p + 5 or p < 2:
        return {"error": "Insufficient sample size or feature count for driver analysis."}
        
    # Standardize data (Z-scores)
    Y = clean_df[target_col].values.astype(np.float64)
    Y_std = (Y - np.mean(Y)) / (np.std(Y) + 1e-12)
    
    X = clean_df[feature_cols].values.astype(np.float64)
    X_means = np.mean(X, axis=0)
    X_stds = np.std(X, axis=0) + 1e-12
    X_std = (X - X_means) / X_stds
    
    # 1. Correlation Matrix R_xx (p x p) and R_xy (p x 1)
    R_xx = (X_std.T @ X_std) / (N - 1.0)
    R_xy = (X_std.T @ Y_std) / (N - 1.0)
    
    # Regularize tiny diagonal jitter if matrix is near-singular
    R_xx += np.eye(p) * 1e-7
    
    # 2. Spectral decomposition of R_xx = V * Lambda * V^T
    try:
        eigenvalues, V = np.linalg.eigh(R_xx)
    except np.linalg.LinAlgError:
        return {"error": "Correlation matrix could not be inverted."}
        
    # Ensure positive eigenvalues
    eigenvalues = np.maximum(eigenvalues, 1e-12)
    Lambda_sqrt = np.diag(np.sqrt(eigenvalues))
    Lambda_inv_sqrt = np.diag(1.0 / np.sqrt(eigenvalues))
    
    # 3. Transformation matrix relating X to orthogonal variables Z
    # Lambda_star = V * Lambda^(1/2) * V^T (correlations between X and Z)
    Lambda_star = V @ Lambda_sqrt @ V.T
    
    # Beta_star (correlations between Z and Y) = V * Lambda^(-1/2) * V^T * R_xy
    Beta_star = (V @ Lambda_inv_sqrt @ V.T) @ R_xy
    
    # 4. Raw Relative Weights: epsilon = Lambda_star^2 @ Beta_star^2
    raw_weights = (Lambda_star ** 2) @ (Beta_star ** 2)
    R2 = float(np.sum(raw_weights))
    
    # Bounded R2 validation
    R2 = max(0.0, min(1.0, R2))
    
    # 5. Percentage contribution
    weights_summary = []
    for i, col in enumerate(feature_cols):
        raw_w = float(raw_weights[i])
        pct_contrib = float((raw_w / R2 * 100.0) if R2 > 0 else (100.0 / p))
        weights_summary.append({
            "feature": col,
            "raw_weight": round(raw_w, 4),
            "relative_importance_pct": round(pct_contrib, 1)
        })
        
    # Sort descending by importance
    weights_summary = sorted(weights_summary, key=lambda x: x["relative_importance_pct"], reverse=True)
    
    return {
        "r_squared": round(R2, 4),
        "sample_size": N,
        "weights": weights_summary
    }
