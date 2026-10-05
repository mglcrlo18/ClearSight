"""
ClearSight Survey Analytics Engine Package
Zero-cloud local processing for survey tabulation, rim weighting, and Taglish NLP.
"""

from .ingestion import autodetect_schema, run_hygiene_audit, resolve_google_forms_checkboxes, read_survey_file
from .stats_engine import (
    calculate_rim_weights,
    test_pairwise_proportions,
    test_vs_total_benchmark,
    test_means_significance,
    chi_square_independence,
    calculate_chi_square_df,
    rao_scott_second_order_mrcv,
    apply_fdr_benjamini_hochberg,
    apply_fdr_benjamini_yekutieli
)
from .driver_analysis import compute_johnsons_relative_weights
from .taglish_nlp import batch_code_open_ends, scrub_pii, normalize_taglish_affixes
from .export_engine import (
    generate_excel_banner_book,
    generate_customer_voice_snapshot_html,
    generate_thesis_chapter_4_package,
    generate_thesis_excel_tables
)
from .statistical_suite import (
    run_independent_ttest,
    run_paired_ttest,
    run_mann_whitney_u,
    run_wilcoxon_signed_rank,
    run_kruskal_wallis,
    run_correlation_matrix,
    run_chi_square_association,
    run_linear_regression,
    run_ordinal_logistic_regression,
    run_path_analysis_sem,
    run_kruskal_quadrant_analysis
)

__all__ = [
    "autodetect_schema",
    "run_hygiene_audit",
    "resolve_google_forms_checkboxes",
    "read_survey_file",
    "calculate_rim_weights",
    "test_pairwise_proportions",
    "test_vs_total_benchmark",
    "test_means_significance",
    "chi_square_independence",
    "calculate_chi_square_df",
    "rao_scott_second_order_mrcv",
    "apply_fdr_benjamini_hochberg",
    "apply_fdr_benjamini_yekutieli",
    "compute_johnsons_relative_weights",
    "batch_code_open_ends",
    "scrub_pii",
    "normalize_taglish_affixes",
    "generate_excel_banner_book",
    "generate_customer_voice_snapshot_html",
    "generate_thesis_chapter_4_package",
    "generate_thesis_excel_tables",
    "run_independent_ttest",
    "run_paired_ttest",
    "run_mann_whitney_u",
    "run_wilcoxon_signed_rank",
    "run_kruskal_wallis",
    "run_correlation_matrix",
    "run_chi_square_association",
    "run_linear_regression",
    "run_ordinal_logistic_regression",
    "run_path_analysis_sem",
    "run_kruskal_quadrant_analysis"
]
