"""The streaming [SELFIE] tag filter — the trickiest parsing in the app."""
import pytest

from companion.services.photos import SelfieTagFilter, strip_selfie_tags


def run_filter(chunks):
    f = SelfieTagFilter()
    out = "".join(f.feed(c) for c in chunks)
    out += f.flush()
    return out, f.mood


def test_no_tag_passthrough():
    out, mood = run_filter(["hello ", "there!"])
    assert out == "hello there!"
    assert mood is None


def test_simple_tag_stripped():
    out, mood = run_filter(["sure thing!\n[SELFIE: coffee]"])
    assert out == "sure thing!\n"
    assert mood == "coffee"


def test_tag_split_across_many_chunks():
    text = "took this for you\n[SELFIE: cozy]"
    for size in (1, 2, 3, 5, 7):
        chunks = [text[i:i + size] for i in range(0, len(text), size)]
        out, mood = run_filter(chunks)
        assert out == "took this for you\n", f"chunk size {size}"
        assert mood == "cozy", f"chunk size {size}"


def test_mid_text_brackets_untouched():
    out, mood = run_filter(["math [1, 2, 3] is fun [ok?]"])
    assert out == "math [1, 2, 3] is fun [ok?]"
    assert mood is None


def test_bracket_that_almost_matches():
    out, mood = run_filter(["see [SELF magazine] today"])
    assert out == "see [SELF magazine] today"
    assert mood is None


def test_case_and_space_variants():
    out, mood = run_filter(["here!\n[ selfie : dressed up ]"])
    assert out == "here!\n"
    assert mood == "dressed_up"


def test_truncated_tag_at_stream_end():
    out, mood = run_filter(["okay!\n[SELFIE: gym"])
    assert out == "okay!\n"
    assert mood == "gym"


def test_multiple_tags_last_wins_all_stripped():
    out, mood = run_filter(["a [SELFIE: coffee] b [SELFIE: cozy]"])
    assert "SELFIE" not in out
    assert mood == "cozy"


@pytest.mark.parametrize("text,expected_clean,expected_mood", [
    ("hi [SELFIE: coffee]", "hi", "coffee"),
    ("no tag here", "no tag here", None),
    ("mixed [selfie:morning] end", "mixed  end", "morning"),
])
def test_strip_safety_net(text, expected_clean, expected_mood):
    clean, mood = strip_selfie_tags(text)
    assert clean == expected_clean
    assert mood == expected_mood
