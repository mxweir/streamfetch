"""Verified HTTPS independent of a build machine's certificate-file location."""

import ssl

import certifi


def verified_context() -> ssl.SSLContext:
    """Preserve configured system trust and add the packaged Mozilla CA bundle.

    Frozen Python may point at a CA path that exists only on the CI runner.
    Never disable certificate or hostname verification to work around that.
    """
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context
