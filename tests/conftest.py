import pytest

from geo_extractor import i18n


@pytest.fixture(autouse=True)
def spanish_system(monkeypatch):
    """Los tests no dependen del idioma del ordenador donde se ejecutan: por defecto, sistema en castellano."""
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    monkeypatch.setattr(i18n, "_language", None)
