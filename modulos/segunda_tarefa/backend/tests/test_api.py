import pytest
from fastapi.testclient import TestClient

from app.api.deps import generator_dep, note_repo_dep, settings_dep
from app.core.config import Settings
from app.main import app
from app.schemas.devolution_schema import LLMNoteDraft, LLMRequirement
from app.schemas.enums import VicioCode
from app.services.generator_service import NoteGenerator
from tests.fakes import FakeLLM, FakeSearcher, InMemoryNoteRepository, precedent

CONT = precedent("prec_cont_01", "quebra_continuidade", [("Lei 6.015/1973", "195")])
GOOD = LLMNoteDraft(requirements=[LLMRequirement(
    vicio_code=VicioCode.QUEBRA_CONTINUIDADE, legal_topic="Quebra da continuidade", precedent_ids=["prec_cont_01"],
    justification_draft="Verifica-se que o transmitente...", suggested_solution="Apresentar certidão...")])
BAD = LLMNoteDraft(requirements=[GOOD.requirements[0].model_copy(update={"precedent_ids": ["inventado"]})])

PAYLOAD = {
    "protocol_number": "184.920",
    "protocol_date": "2026-10-14",
    "act_type": "Escritura de compra e venda",
    "presenter_name": "Banco do Brasil S.A.",
    "uf": "SP",
    "issues": [{"vicio_code": "quebra_continuidade",
                "case_facts": "Na matrícula consta solteiro; no título, casado na comunhão parcial."}],
}


@pytest.fixture
def repo():
    return InMemoryNoteRepository()


def make_client(repo, *llm_responses) -> TestClient:
    generator = NoteGenerator(FakeSearcher({"quebra_continuidade": [CONT]}), FakeLLM(*llm_responses))
    app.dependency_overrides = {
        note_repo_dep: lambda: repo,
        generator_dep: lambda: generator,
        settings_dep: lambda: Settings(_env_file=None),
    }
    return TestClient(app)  # sem "with": não executa o lifespan (sem Mongo real)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides = {}


def edits(note: dict) -> list[dict]:
    return [{k: v for k, v in r.items() if k != "order"} for r in note["requirements"]]


def test_vicios_endpoint_lists_all_codes(repo):
    res = make_client(repo).get("/api/vicios")
    assert res.status_code == 200
    assert {v["code"] for v in res.json()} == {c.value for c in VicioCode}


def test_generate_persists_draft(repo):
    res = make_client(repo, GOOD).post("/api/devolution-notes/generate", json=PAYLOAD)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "draft" and body["protocol_number"] == "184920"
    assert body["requirements"][0]["legal_basis"] == "Lei 6.015/1973, art. 195"
    assert "MINUTA" in body["full_compiled_text"]
    assert body["id"] in repo.docs


def test_generate_returns_502_when_llm_cites_unknown_ids(repo):
    res = make_client(repo, BAD, BAD).post("/api/devolution-notes/generate", json=PAYLOAD)
    assert res.status_code == 502
    assert "inventado" in res.json()["detail"]
    assert repo.docs == {}


def test_generate_rejects_missing_case_facts(repo):
    payload = {**PAYLOAD, "issues": [{"vicio_code": "quebra_continuidade", "case_facts": ""}]}
    assert make_client(repo).post("/api/devolution-notes/generate", json=payload).status_code == 422


def test_patch_edits_reorders_and_rerenders(repo):
    client = make_client(repo, GOOD)
    note = client.post("/api/devolution-notes/generate", json=PAYLOAD).json()
    reqs = edits(note)
    reqs[0]["user_edited_text"] = "Texto revisado."
    manual = {"vicio_code": "outro", "legal_topic": "Exigência manual", "legal_basis": "art. 1 da Lei X",
              "justification_draft": "Justificativa manual.", "suggested_solution": "Fazer Y.",
              "source": "manual", "grounded": False}

    res = client.patch(f"/api/devolution-notes/{note['id']}", json={"version": 1, "requirements": [manual, *reqs]})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"] == 2
    assert [r["order"] for r in body["requirements"]] == [1, 2]
    assert body["requirements"][0]["legal_topic"] == "Exigência manual"
    assert "Texto revisado." in body["full_compiled_text"]
    assert body["full_compiled_text"].index("Exigência manual") < body["full_compiled_text"].index("Texto revisado.")


def test_patch_with_stale_version_returns_409(repo):
    client = make_client(repo, GOOD)
    note = client.post("/api/devolution-notes/generate", json=PAYLOAD).json()
    url = f"/api/devolution-notes/{note['id']}"
    assert client.patch(url, json={"version": 1, "requirements": edits(note)}).status_code == 200
    res = client.patch(url, json={"version": 1, "requirements": edits(note)})
    assert res.status_code == 409 and "versão" in res.json()["detail"]


def test_issue_assigns_sequential_numbers_and_locks(repo):
    client = make_client(repo, GOOD, GOOD)
    n1 = client.post("/api/devolution-notes/generate", json=PAYLOAD).json()
    n2 = client.post("/api/devolution-notes/generate", json=PAYLOAD).json()

    i2 = client.post(f"/api/devolution-notes/{n2['id']}/issue").json()
    i1 = client.post(f"/api/devolution-notes/{n1['id']}/issue").json()

    year = i1["issued_at"][:4]
    assert (i2["note_number"], i1["note_number"]) == (f"1/{year}", f"2/{year}")
    assert i1["status"] == "issued" and f"Nº 2/{year}" in i1["full_compiled_text"]
    assert "MINUTA" not in i1["full_compiled_text"]

    assert client.patch(f"/api/devolution-notes/{n1['id']}", json={"version": i1["version"], "requirements": []}).status_code == 409
    assert client.post(f"/api/devolution-notes/{n1['id']}/issue").status_code == 409


def test_issue_blocked_while_manual_requirement_incomplete(repo):
    client = make_client(repo)  # sem LLM: só exigência manual
    payload = {**PAYLOAD, "issues": [{"vicio_code": "cnd_municipal_ausente", "case_facts": "Certidão municipal não apresentada."}]}
    note = client.post("/api/devolution-notes/generate", json=payload).json()
    assert note["warnings"] and note["requirements"][0]["grounded"] is False

    res = client.post(f"/api/devolution-notes/{note['id']}/issue")
    assert res.status_code == 422
    # a recusa não consome número nem bloqueia a edição
    assert repo.counters == {}
    assert client.patch(f"/api/devolution-notes/{note['id']}", json={"version": 1, "requirements": edits(note)}).status_code == 200


def test_preview_renders_without_saving(repo):
    client = make_client(repo, GOOD)
    note = client.post("/api/devolution-notes/generate", json=PAYLOAD).json()
    reqs = edits(note)
    reqs[0]["user_edited_text"] = "Só na prévia."

    res = client.post(f"/api/devolution-notes/{note['id']}/preview", json={"requirements": reqs})

    assert res.status_code == 200 and "Só na prévia." in res.json()["markdown"]
    assert "Só na prévia." not in repo.docs[note["id"]]["full_compiled_text"]


def test_exports(repo):
    client = make_client(repo, GOOD)
    note = client.post("/api/devolution-notes/generate", json=PAYLOAD).json()

    md = client.get(f"/api/devolution-notes/{note['id']}/export.md")
    assert md.status_code == 200 and md.text == note["full_compiled_text"]
    assert 'filename="nota-devolutiva-minuta-protocolo-184920.md"' in md.headers["content-disposition"]

    txt = client.get(f"/api/devolution-notes/{note['id']}/export.txt")
    assert txt.status_code == 200 and "**" not in txt.text
    assert txt.headers["content-type"].startswith("text/plain")


def test_unknown_or_invalid_id_returns_404(repo):
    client = make_client(repo)
    assert client.get("/api/devolution-notes/nao-e-objectid").status_code == 404
    assert client.get("/api/devolution-notes/65f000000000000000000000").status_code == 404
