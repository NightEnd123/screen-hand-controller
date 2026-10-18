"""Session numbers behind the dashboard charts."""
from gesture_control.stats import SessionStats


def feed(st, seconds, state="active", mode="point", fps=10, start=0.0, actions_at=None, cursor=None):
    t = start
    for i in range(int(seconds * fps)):
        acts = (actions_at or {}).get(i, ())
        st.add(t, state, mode, acts, cursor(t) if cursor else None)
        t += 1 / fps
    return t


def test_counts_clicks_shortcuts_pauses_and_scroll_entries():
    st = SessionStats()
    t = feed(st, 1, actions_at={2: [("down", "left")], 5: [("click", "right")]})
    t = feed(st, 1, mode="scroll", start=t)            # one scroll session, many frames
    t = feed(st, 0.5, start=t)
    t = feed(st, 1, mode="scroll", start=t)            # a second one
    feed(st, 1, start=t, actions_at={1: [("keys", "ctrl+tab", "swipe_right")], 3: [("keydown", "alt")],
                                     4: [("keys", "tab")], 6: [("pause", True)], 7: [("pause", False)]})
    c = st.snapshot()["counts"]
    assert c == {"clicks": 2, "scrolls": 2, "shortcuts": 2, "pauses": 1}


def test_mode_time_only_counts_while_active():
    st = SessionStats()
    t = feed(st, 2, mode="point")
    t = feed(st, 1, mode="scroll", start=t)
    feed(st, 3, state="paused", mode="point", start=t)
    mt = st.snapshot()["mode_time"]
    assert abs(mt["Point"] - 2.0) < 0.2 and abs(mt["Scroll"] - 1.0) < 0.2


def test_cursor_speed_is_bucketed_per_second():
    st = SessionStats()
    feed(st, 3.25, cursor=lambda t: (300 * t, 0))       # 300 px every second, frames ending at t=3.2
    sp = st.snapshot()["speed"]
    assert len(sp) == 3                                   # seconds 0, 1 and 2 are complete
    assert all(abs(v - 300) <= 35 for v in sp)            # +- one frame of boundary rounding


def test_timeline_intervals_merge_split_and_expire():
    st = SessionStats(span_s=60)
    t = feed(st, 5)
    t = feed(st, 5, state="paused", start=t)
    t = feed(st, 5, start=t)
    iv = st.snapshot()["intervals"]
    assert len(iv["active"]) == 2 and len(iv["paused"]) == 1
    assert abs((iv["paused"][0][1] - iv["paused"][0][0]) - 4.9) < 0.2
    feed(st, 70, start=t + 100)                          # much later: the old rows fall out
    iv = st.snapshot()["intervals"]
    assert len(iv["active"]) == 1 and iv["paused"] == []


def test_hand_seen_only_with_a_hand_while_active():
    st = SessionStats()
    t = feed(st, 2, mode="idle")
    feed(st, 2, mode="point", start=t)
    hand = st.snapshot()["intervals"]["hand"]
    assert len(hand) == 1 and hand[0][0] >= 1.9
