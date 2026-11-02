"""The design overview's models and builder (spec 2026-11-02 §9, §18.10)."""
from codetortoise.config import AnalysisConfig, ComponentRule
from codetortoise.design import ReadingDesign, Walk, WalkStep


def test_the_design_keys_default_to_layers_two_calls_six_walks_and_on():
    a = AnalysisConfig()
    assert (a.components, a.walk_depth, a.max_walks, a.design) == ([], 2, 6, True)
    b = AnalysisConfig.model_validate({"components": [{"name": "HAL", "globs": ["hal/**", "include/hal/**"]}],
                                       "walk_depth": 1, "max_walks": 2, "design": False})
    assert b.components == [ComponentRule(name="HAL", globs=["hal/**", "include/hal/**"])]
    assert (b.walk_depth, b.max_walks, b.design) == (1, 2, False)


def test_a_reading_design_survives_its_json_round_trip():
    step = WalkStep(kind="return", src="N10", dst="N3", label="-2", status="new", ref="flow", story="S1", flow="FL1",
                    flow_n=1, keys=["result|service/logger.c|logger_flush|uart_send"], path="driver/uart.c", line=18)
    d = ReadingDesign(walks=[Walk(id="W1", title="When `len > 64`", connection=("T1", "T2"), condition="G1", case=True,
                                  parts=["N7", "N3", "N10"], stories=["S1"], steps=[step])])
    back = ReadingDesign.model_validate(d.model_dump(mode="json"))
    assert back == d and back.walks[0].connection == ("T1", "T2")
    assert ReadingDesign().model_dump()["walks"] == [] and ReadingDesign().nodes == {}
