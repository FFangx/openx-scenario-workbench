from openx_workbench.synonyms import expand_query, query_terms


def test_everyday_words_bring_in_the_library_terms():
    assert expand_query("急刹超车场景") == "急刹超车场景 制动 换道 ALCA"
    assert query_terms("鬼探头") == ["横穿"]
    assert query_terms("自动泊车") == ["APA"]
    assert expand_query("前方行人横穿") == "前方行人横穿"  # the library's own words need nothing added


def test_english_words_bring_in_the_library_terms_as_whole_words():
    assert query_terms("Door open warning") == ["DOW"]
    assert expand_query("driving through a roundabout") == "driving through a roundabout 环岛"
    assert query_terms("a car cuts in") == query_terms("cut-in") == ["前车切入"]
    assert query_terms("lane keeping, dashed line") == ["LKA", "虚线", "broken"]
    assert query_terms("executing the test") == []  # "cut in" is no part of a word
    assert query_terms("AEBS braking") == ["AEB", "制动"]


def test_the_vehicle_under_test_is_no_target_and_single_characters_never_match():
    assert query_terms("试验车辆为乘用车") == []
    assert query_terms("M1类乘用车 前方静止乘用车") == ["乘用车"]
    assert query_terms("人") == []
