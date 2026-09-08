from __future__ import annotations

import hashlib
import inspect
import unittest

from sazmanhr.client import EnterpriseWebWindow, PinnedPage


def fingerprint(raw: bytes) -> str:
    value = hashlib.sha256(raw).hexdigest().upper()
    return ":".join(value[index:index + 2] for index in range(0, len(value), 2))


class FakeUrl:
    def __init__(self, host="127.0.0.1", port=8765, scheme="https"):
        self._host = host
        self._port = port
        self._scheme = scheme

    def host(self):
        return self._host

    def port(self, default):
        return self._port if self._port is not None else default

    def scheme(self):
        return self._scheme


class FakeCert:
    def __init__(self, der: bytes):
        self._der = der

    def toDer(self):
        return self._der


class FakeError:
    def __init__(self, der: bytes, *, host="127.0.0.1", port=8765,
                 overridable=True, with_chain=True):
        self._url = FakeUrl(host, port)
        self._overridable = overridable
        self._chain = [FakeCert(der)] if with_chain else []
        self.accepted = False
        self.rejected = False

    def url(self):
        return self._url

    def isOverridable(self):
        return self._overridable

    def certificateChain(self):
        return self._chain

    def acceptCertificate(self):
        self.accepted = True

    def rejectCertificate(self):
        self.rejected = True


class StubPage:
    allowed_host = "127.0.0.1"
    allowed_port = 8765
    preflight_succeeded = True
    allowed_fingerprint = ""

    _normalize_fingerprint = staticmethod(PinnedPage._normalize_fingerprint)


class Rc3DesktopTlsPinTests(unittest.TestCase):
    def invoke(self, page, error):
        PinnedPage._on_certificate_error(page, error)

    def test_qt6_signal_is_connected(self):
        source = inspect.getsource(PinnedPage.__init__)
        self.assertIn("self.certificateError.connect(self._on_certificate_error)", source)

    def test_matching_pinned_leaf_is_accepted_after_preflight(self):
        der = b"matching-leaf-certificate"
        page = StubPage()
        page.allowed_fingerprint = fingerprint(der)
        error = FakeError(der)
        self.invoke(page, error)
        self.assertTrue(error.accepted)
        self.assertFalse(error.rejected)

    def test_changed_certificate_is_rejected(self):
        page = StubPage()
        page.allowed_fingerprint = fingerprint(b"expected-certificate")
        error = FakeError(b"changed-certificate")
        self.invoke(page, error)
        self.assertFalse(error.accepted)
        self.assertTrue(error.rejected)

    def test_preflight_is_required(self):
        der = b"matching-leaf-certificate"
        page = StubPage()
        page.preflight_succeeded = False
        page.allowed_fingerprint = fingerprint(der)
        error = FakeError(der)
        self.invoke(page, error)
        self.assertFalse(error.accepted)
        self.assertTrue(error.rejected)

    def test_wrong_endpoint_nonoverridable_and_missing_chain_fail_closed(self):
        der = b"matching-leaf-certificate"
        for error in (
            FakeError(der, host="localhost"),
            FakeError(der, port=443),
            FakeError(der, overridable=False),
            FakeError(der, with_chain=False),
        ):
            page = StubPage()
            page.allowed_fingerprint = fingerprint(der)
            self.invoke(page, error)
            self.assertFalse(error.accepted)
            self.assertTrue(error.rejected)

    def test_verified_api_fingerprint_is_bound_before_web_load(self):
        source = inspect.getsource(EnterpriseWebWindow.connect_and_load)
        bind = source.index("self.page.allowed_fingerprint = client.tls_fingerprint")
        ready = source.index("self.page.preflight_succeeded = True")
        load = source.index("self.view.load(")
        self.assertLess(bind, ready)
        self.assertLess(ready, load)


if __name__ == "__main__":
    unittest.main()
