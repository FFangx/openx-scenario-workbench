from openx_workbench.synonyms import expand_query, query_terms


def test_everyday_words_bring_in_the_library_terms():
    assert expand_query("急刹超车场景") == "急刹超车场景 制动 换道 ALCA"
    assert query_terms("鬼探头") == ["横穿"]
    assert query_terms("自动泊车") == ["APA"]
    assert expand_query("前方行人横穿") == "前方行人横穿"  # the library's own words need nothing added


def test_the_vehicle_under_test_is_no_target_and_single_characters_never_match():
    assert query_terms("试验车辆为乘用车") == []
    assert query_terms("M1类乘用车 前方静止乘用车") == ["乘用车"]
    assert query_terms("人") == []
