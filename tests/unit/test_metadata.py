from tests.fakes.fake_osc_query import FakeOscQuery

from bridge.metadata import resolve_track_label


def test_single_armed_track():
    query = FakeOscQuery(num_tracks=3, armed={1: True}, names={1: "Vocals"})
    assert resolve_track_label(query) == "Vocals"


def test_multiple_armed_joined():
    query = FakeOscQuery(
        num_tracks=3,
        armed={0: True, 2: True},
        names={0: "Vocals", 2: "Guitar"},
    )
    assert resolve_track_label(query, merge="_") == "Vocals_Guitar"


def test_fallback_selected_track():
    query = FakeOscQuery(num_tracks=3, names={2: "Keys"}, selected=2)
    assert resolve_track_label(query) == "Keys"


def test_unknown_when_no_armed_and_no_name():
    query = FakeOscQuery(num_tracks=2, selected=0)
    assert resolve_track_label(query) == "UnknownTrack"
