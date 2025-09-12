import urllib.parse

from hypothesis import given, settings
from hypothesis import strategies as st

from app.security.redirects import sanitize_next_path

# Alphabet with URL-ish characters plus broad unicode
_url_alphabet = st.characters(
    blacklist_categories=("Cs",),
    blacklist_characters=["\x00", "\n", "\r"],
)


@st.composite
def percent_chunk(draw):
    hexpair = draw(st.text(alphabet="0123456789ABCDEFabcdef", min_size=2, max_size=2))
    return "%" + hexpair


token = st.one_of(
    st.text(_url_alphabet, min_size=1, max_size=10),
    percent_chunk(),
    st.sampled_from(["..", "login", "v1", "auth", "oauth", "google"]),
)


@st.composite
def path_segments(draw):
    parts = draw(st.lists(token, min_size=0, max_size=6))
    # Join with single slashes; segments themselves may contain encoded slashes etc.
    return "/".join(part.strip("/") for part in parts)


@st.composite
def urlish_strings(draw):
    # Optional absolute/protocol-relative prefix
    proto = draw(
        st.sampled_from(["", "http://evil.com", "https://evil.com", "//evil.com", ""])
    )
    leading = draw(st.sampled_from(["", "/", "//", "///"]))
    segs = draw(path_segments())

    base = f"{proto}{leading}{segs}"

    # Maybe sprinkle in traversal
    if draw(st.booleans()) and segs:
        base = base + "/.."

    # Build query params, possibly with nested next= ... patterns
    params = []

    # Some regular parameters
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        k = draw(st.sampled_from(["a", "b", "tab", "q", "redirect", "r"]))
        v = draw(st.text(_url_alphabet, min_size=0, max_size=12))
        params.append(f"{k}={v}")

    # Possibly add a nested next param
    if draw(st.booleans()):
        depth = draw(st.integers(min_value=1, max_value=3))
        nested = draw(path_segments())
        # Build something like ?next=?next=... or encoded forms
        for _ in range(depth):
            prefix = draw(st.sampled_from(["?next=", "%3Fnext%3D", "%253Fnext%253D"]))
            nested = prefix + nested
        # Sometimes wrap inside an outer key
        if draw(st.booleans()):
            params.append("next=" + nested)
        else:
            params.append("redir=" + nested)

    query = ("?" + "&".join(params)) if params else ""

    # Optional fragment or encoded fragment
    frag = draw(st.sampled_from(["", "#frag", "%23frag", "#", "%23"]))

    # Optional surrounding whitespace
    pad_left = draw(
        st.text(
            st.characters(blacklist_categories=("Cs",), blacklist_characters=["\x00"]),
            min_size=0,
            max_size=2,
        )
    )
    pad_right = draw(
        st.text(
            st.characters(blacklist_categories=("Cs",), blacklist_characters=["\x00"]),
            min_size=0,
            max_size=2,
        )
    )

    return pad_left + base + query + frag + pad_right


@settings(max_examples=500, deadline=None)
@given(urlish_strings())
def test_starts_with_slash_and_not_empty(raw: str):
    result = sanitize_next_path(raw)
    assert isinstance(result, str)
    assert result != ""
    assert result.startswith("/")


@settings(max_examples=500, deadline=None)
@given(urlish_strings())
def test_not_blocklisted_paths(raw: str):
    result = sanitize_next_path(raw)
    # Must never redirect to auth-related paths (exact or as a prefix)
    assert result != "/login"
    assert not result.startswith("/v1/auth")
    assert not result.startswith("/google")
    assert not result.startswith("/oauth")


@settings(max_examples=500, deadline=None)
@given(urlish_strings())
def test_double_decode_cap_no_more_than_one_material_change(raw: str):
    # Applying additional pre-decodes should not keep changing the sanitized output
    out0 = sanitize_next_path(raw)
    out1 = sanitize_next_path(urllib.parse.unquote(raw))
    out2 = sanitize_next_path(urllib.parse.unquote(urllib.parse.unquote(raw)))

    # At most one pre-decode should materially change the output
    assert out2 == out1

    # And all outputs should be normalized to start with '/'
    assert out0.startswith("/") and out1.startswith("/") and out2.startswith("/")


@settings(max_examples=500, deadline=None)
@given(urlish_strings())
def test_no_next_param_in_resulting_query(raw: str):
    result = sanitize_next_path(raw)
    parsed = urllib.parse.urlparse(result)
    qs = urllib.parse.parse_qs(parsed.query)
    assert "next" not in qs


@settings(max_examples=500, deadline=None)
@given(urlish_strings())
def test_no_double_slashes_in_output(raw: str):
    result = sanitize_next_path(raw)
    # Repeated slashes should be collapsed everywhere (the leading slash remains single)
    assert "//" not in result

