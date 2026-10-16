from app.schemas.geo_schema import RegistryAct, RegistryExtraction
from app.services.continuity_service import analyze_continuity, names_match, normalize_code


def act(code, kind, grantors=(), grantees=(), transfer=False, enc=False, cancels=None):
    return RegistryAct(
        act_code=code, act_type=kind, is_ownership_transfer=transfer, is_encumbrance=enc,
        grantors=list(grantors), grantees=list(grantees), cancels_act_code=cancels, summary=kind,
    )


BASE = [
    act("R-1", "COMPRA_E_VENDA", ["ANTONIO SOUZA"], ["JOSÉ PEREIRA"], transfer=True),
    act("R-2", "HIPOTECA", ["JOSÉ PEREIRA"], ["BANCO X"], enc=True),
    act("AV-3", "CANCELAMENTO", cancels="R.2"),
    act("R-4", "PARTILHA", ["ESPÓLIO DE JOSÉ PEREIRA"], ["CARLOS PEREIRA"], transfer=True),
]


def registry(*extra):
    return RegistryExtraction(registry_number="89.214", acts=[*BASE, *extra])


def test_regular():
    c = analyze_continuity(registry(), ["Carlos Pereira"])
    assert c.status == "REGULAR"
    assert c.current_registered_owner == "CARLOS PEREIRA (R-4)"
    assert c.active_liens == []  # hipoteca R-2 cancelada pela AV-3
    assert all(link.is_continuous for link in c.chain)


def test_seller_is_not_owner():
    c = analyze_continuity(registry(), ["MARCOS VINICIUS PEREIRA"])
    assert c.status == "QUEBRA_DETECTADA"
    assert "MARCOS VINICIUS PEREIRA" in c.observation


def test_active_penhora_gives_alert():
    c = analyze_continuity(registry(act("AV-5", "PENHORA", enc=True)), ["CARLOS PEREIRA"])
    assert c.status == "ALERTA"
    assert [lien.act_code for lien in c.active_liens] == ["AV-5"]


def test_internal_chain_break():
    c = analyze_continuity(
        registry(act("R-5", "COMPRA_E_VENDA", ["PESSOA ESTRANHA"], ["NOVO DONO"], transfer=True)),
        ["NOVO DONO"],
    )
    assert c.status == "QUEBRA_DETECTADA"
    assert c.chain[-1].is_continuous is False


def test_co_owner_missing_from_title():
    c = analyze_continuity(
        registry(act("R-5", "COMPRA_E_VENDA", ["CARLOS PEREIRA"], ["ANA LIMA", "BRUNO LIMA"], transfer=True)),
        ["ANA LIMA"],
    )
    assert c.status == "ALERTA"
    assert "BRUNO LIMA" in c.observation


def test_no_title_is_alert():
    assert analyze_continuity(registry(), []).status == "ALERTA"


def test_acts_are_sorted_by_number():
    shuffled = RegistryExtraction(registry_number="1", acts=list(reversed(BASE)))
    assert analyze_continuity(shuffled, ["CARLOS PEREIRA"]).status == "REGULAR"


def test_name_and_code_normalization():
    assert names_match("José Antônio Pereira", "JOSE ANTONIO PEREIRA")
    assert names_match("Espólio de José Pereira", "JOSÉ PEREIRA")
    assert not names_match("MARCOS PEREIRA", "CARLOS EDUARDO PEREIRA")
    assert normalize_code("R.03") == "R-3" and normalize_code("Av 12") == "AV-12"
