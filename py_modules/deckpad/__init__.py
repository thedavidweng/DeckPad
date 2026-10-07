import os


def _provide_xml_etree():
    # Decky Loader's PyInstaller build of Python 3.11 ships `xml` and `pyexpat` but not `xml.etree`,
    # which dbus-fast imports at module level. Fall back to the unmodified CPython 3.11.7 copy in
    # py_modules/_stdlib (PSF license) by extending the frozen `xml` package's search path.
    try:
        import xml.etree  # noqa: F401
    except ModuleNotFoundError:
        import xml

        xml.__path__.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "_stdlib", "xml"))


_provide_xml_etree()
