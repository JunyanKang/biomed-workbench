from biomed_workbench.visualization import (
    ANALYSIS_FIGURE_PROFILES,
    PLOT_CONTRACTS,
    STYLE_VERSION,
    scientific_figure_standard,
)


EXPECTED_PROFILES = {
    "trajectory-topology",
    "trajectory-velocity",
    "fate-mapping",
    "regulatory-velocity",
    "spatial-platform-qc",
    "spatial-core-analysis",
    "spatial-deconvolution",
    "spatial-domain-benchmark",
    "spatial-communication",
    "spatial-image-analysis",
    "spatial-multislice",
}


def test_trajectory_and_spatial_profiles_are_complete_and_unique():
    assert STYLE_VERSION == "1.2.0"
    assert EXPECTED_PROFILES <= set(ANALYSIS_FIGURE_PROFILES)
    for name in EXPECTED_PROFILES:
        profile = ANALYSIS_FIGURE_PROFILES[name]
        assert len(profile["required"]) >= 6
        assert len(profile["required"]) == len(set(profile["required"]))
        assert not set(profile["required"]) & set(profile["optional"])


def test_spatial_and_trajectory_plot_contracts_preserve_geometry_and_direction():
    assert "physical coordinate unit" in PLOT_CONTRACTS["spatial_map"]["required_elements"]
    assert "distance threshold or neighborhood rule" in PLOT_CONTRACTS["spatial_vector_field"]["required_elements"]
    assert "root and terminal states" in PLOT_CONTRACTS["embedding_trajectory"]["required_elements"]
    assert "velocity confidence" in PLOT_CONTRACTS["velocity_field"]["required_elements"]
    assert "quantitative registration error" in PLOT_CONTRACTS["registration_overlay"]["required_elements"]
    assert "inter-section spacing and unit" in PLOT_CONTRACTS["three_dimensional_spatial"]["required_elements"]


def test_every_new_profile_exports_a_nature_ready_vector_contract():
    for name in EXPECTED_PROFILES:
        contract = scientific_figure_standard(name, "nature")
        assert contract["required_plots"] == ANALYSIS_FIGURE_PROFILES[name]["required"]
        assert contract["style"]["journal"]["ready_for_submission_export"]
        assert {"pdf", "svg"} <= set(contract["style"]["export"]["primary"])
        assert contract["style"]["export"]["raster_dpi"] == 600
