#!/usr/bin/env python3
"""Gera dashboard.html a partir de projetos.json e do estado atual de cada projeto.

Só lê os projetos — nunca altera nada dentro deles.

    python3 gerar_painel.py            # atualiza datas, git e quem está rodando
    python3 gerar_painel.py --testes   # também roda os testes do backend de cada projeto
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CACHE_TESTES = AQUI / ".estado_testes.json"


def sh(args, cwd=None, timeout=60):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def ultima_alteracao(pasta: Path) -> str | None:
    """Arquivo mais recente entre os versionáveis (respeita o .gitignore)."""
    code, out = sh(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=pasta)
    if code != 0:
        return None
    mtimes = []
    for f in filter(None, out.split("\0")):
        try:
            mtimes.append((pasta / f).stat().st_mtime)
        except OSError:
            pass
    return datetime.fromtimestamp(max(mtimes)).strftime("%Y-%m-%d %H:%M") if mtimes else None


def info_git(pasta: Path) -> dict | None:
    if sh(["git", "rev-parse", "--git-dir"], cwd=pasta)[0] != 0:
        return None
    _, log = sh(["git", "log", "-1", "--format=%cs|%s", "--", "."], cwd=pasta)
    _, status = sh(["git", "status", "--porcelain", "--", "."], cwd=pasta)
    data, _, msg = log.strip().partition("|")
    return {"ultimo_commit": data, "mensagem": msg,
            "pendentes": len([l for l in status.splitlines() if l.strip()])}


def portas_em_uso() -> dict[int, str]:
    """porta -> diretório de trabalho do processo que escuta nela."""
    _, out = sh(["ss", "-ltnpH"])
    donos = {}
    for linha in out.splitlines():
        m = re.search(r":(\d+)\s.*pid=(\d+)", linha)
        if not m:
            continue
        porta, pid = int(m.group(1)), m.group(2)
        try:
            donos[porta] = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            donos[porta] = ""
    return donos


def rodar_testes(pasta: Path) -> dict:
    py = pasta / "backend/.venv/bin/python"
    if not (pasta / "backend/tests").is_dir():
        return {"status": "sem_testes"}
    if not py.exists():
        return {"status": "erro", "resumo": "venv do backend não encontrado"}
    _, topo = sh(["git", "rev-parse", "--show-toplevel"], cwd=pasta)
    topo = topo.strip() or str(pasta)
    _, antes = sh(["git", "status", "--porcelain", "--", "."], cwd=pasta)
    code, out = sh([str(py), "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                   cwd=pasta / "backend", timeout=600)
    # Alguns testes regeneram arquivos de exemplo versionados; devolve os que estavam limpos.
    _, depois = sh(["git", "status", "--porcelain", "--", "."], cwd=pasta)
    sujos = {l[3:] for l in depois.splitlines() if l.startswith(" M")} - {l[3:] for l in antes.splitlines()}
    if sujos:
        sh(["git", "checkout", "--", *sujos], cwd=topo)  # caminhos do status são relativos à raiz do repo
    resumo = next((l.strip() for l in reversed(out.splitlines())
                   if re.search(r"\b(passed|failed|error)", l)), out.strip()[-200:])
    passou = re.search(r"(\d+) passed", resumo)
    return {"status": "ok" if code == 0 else "falha", "resumo": resumo,
            "passaram": int(passou.group(1)) if passou else 0,
            "em": datetime.now().strftime("%Y-%m-%d %H:%M")}


def main():
    projetos = json.loads((AQUI / "projetos.json").read_text())
    try:
        cache = json.loads(CACHE_TESTES.read_text())
    except (OSError, ValueError):
        cache = {}

    if "--testes" in sys.argv:
        for p in projetos:
            print(f"testando {p['dir']}…", flush=True)
            cache[p["dir"]] = rodar_testes(AQUI / "modulos" / p["dir"])
        CACHE_TESTES.write_text(json.dumps(cache, ensure_ascii=False, indent=2))

    donos = portas_em_uso()
    for p in projetos:
        pasta = AQUI / "modulos" / p["dir"]
        p["path"] = str(pasta)
        p["existe"] = pasta.is_dir()
        p["atualizado"] = ultima_alteracao(pasta) if p["existe"] else None
        p["git"] = info_git(pasta) if p["existe"] else None
        p["readme"] = (pasta / "README.md").exists()
        p["testes"] = cache.get(p["dir"])
        p["rodando"] = any(donos.get(porta, "").startswith(str(pasta))
                           for porta in (p["api"], p["web"]))

    dados = {"gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"), "projetos": projetos}
    modelo = (AQUI / "painel_template.html").read_text()
    html = modelo.replace("/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False))
    (AQUI / "dashboard.html").write_text(html)
    print(f"dashboard.html gerado ({len(projetos)} projetos)")


if __name__ == "__main__":
    main()
