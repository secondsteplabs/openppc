"""openppc-online: the optional OpenPPC companion, for the commands that go online, each only when you run it.

It depends on openppc and never the reverse (ADR-7): `pip install openppc` never brings this in, and the `openppc`
command never goes online, with or without it.
"""
__version__ = "0.1.0"
