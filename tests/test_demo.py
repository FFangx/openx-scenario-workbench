from openx_workbench.demo import ESMINI_COMMIT, fetch_public_demo


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def read(self) -> bytes:
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_public_demo_uses_a_pinned_upstream_revision():
    urls: list[str] = []

    def opener(url: str, timeout: float):
        urls.append(url)
        return FakeResponse(b"<xml />")

    demo = fetch_public_demo(opener=opener)

    assert demo.xosc_name == "cut-in.xosc"
    assert demo.xodr_name == "e6mini.xodr"
    assert len(urls) == 2
    assert all(ESMINI_COMMIT in url for url in urls)
