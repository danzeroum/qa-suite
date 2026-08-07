"""Publica uma release ANCORÁVEL do padrão: manifesto na árvore, tag por cima.

**O que estava quebrado.** `release.yml` dispara em `push: tags: v*` e o repositório
nunca teve tag. O consumidor pinava `webqa-suite==1.0.0` e referenciava
`auditar.yml@main`, e a régua andava sozinha entre duas execuções. Pior: mesmo com
a tag, uma tag é ponteiro móvel — *"continua sendo o que eu instalei"* seguiria
indemonstrável, que é o gap `GAP-QA-TAG` declarado do outro lado.

**A âncora é o manifesto, não a tag.** O manifesto mora na ÁRVORE do commit
taggeado: quem move a tag muda o manifesto que se encontra no destino, e o digest
guardado pelo consumidor deixa de conferir. Um asset de release seria editável
depois de publicado, e a edição não deixaria rastro.

**O manifesto declara o PAI.** Um arquivo não pode conter o hash do commit que o
contém; declarar o commit VALIDADO — o pai — é a formulação honesta. O elo que
fecha o buraco é `--verificar`: ele exige que o commit de release não mude nada
além do manifesto. Sem isso, conteúdo não validado entraria na versão sob a
bandeira de uma validação que rodou no pai.

**A trava que impede a versão de mentir.** A versão do wheel é DINÂMICA, vinda de
`webqa.__version__`. Uma tag `vX.Y.Z` cortada numa árvore cujo `__version__` não
seja `X.Y.Z` produziria um wheel com outro número, e dois conteúdos passariam a
reivindicar a mesma versão. A recusa acontece ANTES de qualquer ref nascer.

Uso:
    python scripts/publicar_release.py --versao 1.0.0 --commit <sha> [--executar]
    python scripts/publicar_release.py --verificar v1.0.0

Sem `--executar` é dry-run: emite o manifesto na saída padrão e não toca em ref
nenhuma. Somente stdlib + git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess  # nosec B404 - argv fixo, sem shell; só git e este interpretador
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RAIZ_REPO = RAIZ.parent
DIR_RELEASES = RAIZ / "releases"
REPOSITORIO = "danzeroum/qa-suite"

# `releases/` é relativo à RAIZ DO REPOSITÓRIO nas operações de git — o pacote
# vive em webqa-suite/, e git não conhece o subdiretório como raiz.
PREFIXO = RAIZ.name

VERSAO_VALIDA = re.compile(r"^\d+\.\d+(\.\d+)?([abrc]\d+|\.dev\d+)?$")
SEMVER_DE_RELEASE = re.compile(r"^\d+\.\d+\.\d+$")

# Campos que todo manifesto carrega. Enumerados para que `--verificar` cobre a
# forma sem depender da memória de quem escreveu o emissor.
CAMPOS = ("schema_version", "repositorio", "tag", "versao", "commit_sha",
          "tree_digest", "catalogo", "mordida")

# `reprovada` NÃO é representável, e a ausência é a decisão: um enum com ela
# criaria a categoria "release publicada com autoprova vermelha" — categoria que,
# existindo, será usada.
ESTADOS_DE_MORDIDA = ("pendente", "aprovada")


class Recusa(Exception):
    """Motivo pelo qual nenhuma ref deve nascer. Nunca é 'aviso'."""


# B607 (caminho parcial): `git` vem do PATH de propósito. Fixar `/usr/bin/git`
# quebraria a ferramenta em qualquer ambiente que a instale noutro lugar — o CI
# do GitHub, um venv com git de nix, a VPS —, e a mitigação real já está aqui: a
# lista é fixa, sem shell, e nenhum argumento vem de rede ou de arquivo do alvo.
def _git(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(  # nosec B603 B607
        ["git", *args], cwd=str(cwd or RAIZ_REPO),
        capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise Recusa(f"git {' '.join(args)} falhou: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def versao_da_arvore(commit: str) -> str:
    """`webqa.__version__` COMO ESTÁ na árvore do commit — não o do processo.

    Lido do git e não por import: o publicador pode rodar a partir de uma ponta
    que já foi bumpada, e importar daqui responderia sobre a árvore errada. É a
    diferença entre conferir a release e conferir quem a está cortando.
    """
    fonte = _git("show", f"{commit}:{PREFIXO}/webqa/__init__.py")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', fonte, re.MULTILINE)
    if not m:
        raise Recusa(f"a árvore de {commit} não declara __version__ em webqa/__init__.py")
    return m.group(1)


# A conversão de fim de linha é DESLIGADA no comando, e isto não é estilo — é a
# correção de um falso vermelho MEDIDO. `git archive` aplica a mesma conversão do
# checkout, então com `core.autocrlf=true` (o padrão da instalação do Git para
# Windows) ele emite CRLF e o digest muda:
#
#     core.autocrlf=false  -> sha256:f8ef23c5…   (o que o manifesto declara)
#     core.autocrlf=true   -> sha256:6fbf10d8…   (mesma árvore, outro número)
#
# O efeito observado: a v1.0.0 — correta, verificada em Linux e publicada — foi
# recusada por `--verificar` num clone Windows. Uma guarda que reprova a release
# certa por causa do sistema de quem a confere é pior que guarda nenhuma: ela
# ensina a ignorar o vermelho, e o próximo vermelho será o verdadeiro.
#
# Os `-c` valem só para esta invocação: nada no repositório de quem roda é
# alterado. O repo não tem `.gitattributes`, então a conversão vinha inteiramente
# da config local — que é justamente o que um digest de âncora não pode ler.
_SEM_CONVERSAO = ("-c", "core.autocrlf=false", "-c", "core.eol=lf")


def tree_digest(commit: str) -> str:
    """Digest do conteúdo versionado do commit. Permite dizer *esta árvore é
    aquela árvore* sem confiar na tag.

    `git archive` é determinístico para um commit dado: o mtime dos membros vem do
    próprio commit, não do relógio de quem arquiva. O que NÃO é determinístico por
    padrão é o fim de linha — ver `_SEM_CONVERSAO` acima.
    """
    r = subprocess.run(  # nosec B603 B607
        ["git", *_SEM_CONVERSAO, "archive", "--format=tar", commit], cwd=str(RAIZ_REPO),
        capture_output=True, check=False)
    if r.returncode != 0:
        raise Recusa(f"git archive de {commit} falhou: {r.stderr.decode(errors='replace')}")
    return "sha256:" + hashlib.sha256(r.stdout).hexdigest()


def _hash_de_arquivo(commit: str, rel: str) -> str:
    """sha256 dos BYTES CRUS do arquivo na árvore do commit.

    Bytes crus, não conteúdo normalizado: qualquer alteração do arquivo tem de
    aparecer, não só as semânticas — uma lista encurtada em segredo produz
    "nenhum achado" indistinguível de alvo seguro.
    """
    r = subprocess.run(  # nosec B603 B607
        ["git", "show", f"{commit}:{PREFIXO}/{rel}"], cwd=str(RAIZ_REPO),
        capture_output=True, check=False)
    if r.returncode != 0:
        raise Recusa(f"{rel} não existe na árvore de {commit}")
    return "sha256:" + hashlib.sha256(r.stdout).hexdigest()


def digerir_catalogo(catalogo: dict) -> str:
    """Digest do CATÁLOGO DE CHECKS: quais checks a régua aplica, e sob que dimensões.

    Não é a lista curada (essa é `caminhos-sensiveis.yaml`) e não é a árvore
    inteira (essa é `tree_digest`). É a superfície de julgamento: dois laudos que
    dizem "0 achados" sob catálogos diferentes mediram coisas diferentes, e a
    diferença entre eles não significa nada.

    Só a população `alvo` entra — `tests/` verifica a SUÍTE, não julga alvo, e
    incluí-la faria o catálogo mudar a cada teste novo da própria suíte, que é
    precisamente a mudança que NÃO altera o que a régua mede.

    Ordenado e sem número de linha: mover um check dentro do arquivo não muda o que
    ele mede, e um digest que mudasse aí gritaria por qualquer coisa — guarda que
    grita por qualquer coisa é desligada.

    Função pura sobre o catálogo já lido: é o que permite testá-la sobre um
    catálogo fabricado, inclusive nas bordas que não dá para produzir no repo real.
    """
    alvo = sorted(
        (t["nodeid"], sorted(t.get("dimensoes") or []))
        for t in catalogo.get("testes") or [] if t.get("populacao") == "alvo"
    )
    bruto = json.dumps(alvo, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(bruto).hexdigest()


def hash_do_catalogo_no_commit(commit: str) -> str:
    """O digest do catálogo COMO ESTÁ na árvore do commit — nunca a de trabalho.

    Via worktree efêmera e subprocesso, e as duas escolhas são a mesma: o catálogo
    é produzido pelo `scripts/catalogo.py` DAQUELE commit, e não pelo que está
    carregado neste processo. Um manifesto que descrevesse o catálogo da ponta
    enquanto ancora a árvore taggeada carimbaria uma superfície de julgamento que
    a release não tem — e o consumidor guardaria esse número como se fosse dela.
    """
    with tempfile.TemporaryDirectory(prefix="webqa-release-") as tmp:
        arvore = Path(tmp) / "arvore"
        _git("worktree", "add", "--detach", "--quiet", str(arvore), commit)
        try:
            r = subprocess.run(  # nosec B603
                [sys.executable, "scripts/catalogo.py", "--json"],
                cwd=str(arvore / PREFIXO), capture_output=True, text=True, check=False)
            if r.returncode != 0:
                raise Recusa(f"catálogo de {commit[:12]}… falhou: {r.stderr.strip()[:400]}")
            return digerir_catalogo(json.loads(r.stdout))
        finally:
            _git("worktree", "remove", "--force", str(arvore))


def caminho_do_manifesto(versao: str) -> Path:
    return DIR_RELEASES / f"v{versao}.manifesto.json"


def montar_manifesto(versao: str, commit: str, mordida: dict) -> dict:
    """O manifesto de uma release, sem tocar em ref nenhuma."""
    return {
        "schema_version": "1.0",
        "repositorio": REPOSITORIO,
        "tag": f"v{versao}",
        "versao": versao,
        "commit_sha": _git("rev-parse", commit),
        "tree_digest": tree_digest(commit),
        "catalogo": {
            "caminhos_sensiveis_hash": _hash_de_arquivo(commit, "data/caminhos-sensiveis.yaml"),
            "checks_hash": hash_do_catalogo_no_commit(commit),
        },
        "mordida": mordida,
    }


def serializar(manifesto: dict) -> str:
    """Uma única forma serializada — o digest do consumidor depende dos bytes."""
    return json.dumps(manifesto, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _problemas_de_identidade(manifesto: dict) -> list[str]:
    """Versão, tag e commit: os três campos que dizem QUAL release é esta."""
    problemas = []
    versao = manifesto["versao"]
    if not SEMVER_DE_RELEASE.match(versao):
        problemas.append(
            f"versao {versao!r} não é X.Y.Z. Pré-lançamento e `.dev` não viram release: a tag "
            f"existe para ancorar o que alguém pode instalar e comparar.")
    if manifesto["tag"] != f"v{versao}":
        problemas.append(f"tag {manifesto['tag']!r} não casa com versao {versao!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifesto["commit_sha"])):
        problemas.append("commit_sha não é um sha completo de 40 dígitos")
    return problemas


def _problemas_de_mordida(mordida: dict) -> list[str]:
    """A autoprova declarada. `pendente` é resposta legítima — e cara."""
    estado = (mordida or {}).get("estado")
    if estado not in ESTADOS_DE_MORDIDA:
        return [f"mordida.estado {estado!r} não é um de {ESTADOS_DE_MORDIDA}. `reprovada` não é "
                f"representável de propósito: a categoria 'release publicada com autoprova "
                f"vermelha', existindo, seria usada."]
    if estado == "pendente" and not (mordida.get("motivo") or "").strip():
        return ["mordida.estado é 'pendente' sem motivo escrito. Pendência sem motivo é uma "
                "decisão que ninguém consegue revisar depois."]
    if estado == "aprovada":
        return _problemas_de_mordida_aprovada(mordida)
    return []


def _problemas_de_mordida_aprovada(mordida: dict) -> list[str]:
    """`aprovada` exige os NÚMEROS, não a palavra.

    Um estado sem contagem seria um selo: quem lê o manifesto veria "aprovada" e
    não teria como perguntar *aprovada em quê*. Os três campos são o escopo inteiro
    da autoprova — as mordidas do contrato 1:1, as direções da guarda do smoke, e
    quantas entradas ficaram DECLARADAS sem mordida, com motivo.
    """
    problemas = []
    for chave in ("devem_falhar", "smoke_gui", "declarado_sem_mordida"):
        if chave not in mordida:
            problemas.append(
                f"mordida.{chave} ausente com estado 'aprovada'. Aprovada em quê? Estado sem "
                f"contagem é selo, e selo é o que o contrato chama de pior que fiscal nenhum.")
    if problemas:
        return problemas
    for chave in ("devem_falhar", "smoke_gui"):
        valor = str(mordida[chave])
        if not re.fullmatch(r"(\d+)/(\1)", valor):
            problemas.append(
                f"mordida.{chave} é {valor!r}: 'aprovada' exige que TODAS as mordidas do escopo "
                f"tenham reprovado. Parte do escopo mordendo é `pendente`, nunca `aprovada`.")
    return problemas


def mordida_da_autoprova(caminho: Path) -> dict:
    """Traduz o relatório de `scripts/autoprova.py` no bloco `mordida` do manifesto.

    A tradução é aqui, e não no autoprova, porque quem decide o que entra num
    manifesto de release é o publicador: o autoprova MEDE, este módulo PUBLICA, e
    manter os dois papéis separados é o que impede um relatório de se auto-aprovar.
    """
    try:
        relatorio = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise Recusa(f"relatório de autoprova ilegível em {caminho}: {erro}") from erro
    if relatorio.get("indeterminado"):
        raise Recusa(
            f"a autoprova não conseguiu provar: {relatorio['indeterminado']}. 'Não consegui "
            f"provar' e 'provei que não morde' pedem reações diferentes, e nenhuma das duas "
            f"produz release aprovada.")
    if not relatorio.get("aprovada"):
        faltantes = (relatorio.get("escopo") or {}).get("devem_falhar", {}).get("nao_morderam", [])
        raise Recusa(
            f"a autoprova reprovou: {len(faltantes)} mordida(s) do contrato 1:1 não reprovaram "
            f"{faltantes[:5]}. Uma régua verde cujas travas não mordem é indistinguível de uma "
            f"régua verde — e a release é exatamente quando alguém passa a confiar nela sem "
            f"poder olhar.")
    devem = relatorio["escopo"]["devem_falhar"]
    smoke = relatorio["escopo"]["smoke_gui"]
    return {
        "estado": "aprovada",
        "devem_falhar": f"{devem['morderam']}/{devem['total']}",
        "smoke_gui": f"{sum(smoke.values())}/{len(smoke)}",
        "declarado_sem_mordida": len(relatorio["declarado_sem_mordida"]),
    }


def problemas_de_forma(manifesto: dict) -> list[str]:
    """A forma do manifesto, conferida sem git. Puro: testável sobre dados fabricados."""
    faltando = [f"campo obrigatório ausente: {c}" for c in CAMPOS if c not in manifesto]
    if faltando:
        return faltando
    problemas = _problemas_de_identidade(manifesto)
    for chave in ("caminhos_sensiveis_hash", "checks_hash"):
        valor = (manifesto["catalogo"] or {}).get(chave, "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(valor)):
            problemas.append(f"catalogo.{chave} não é um digest sha256")
    return problemas + _problemas_de_mordida(manifesto["mordida"])


def _problemas_da_cadeia(tag: str, rel: str, manifesto: dict) -> list[str]:
    """O elo entre o manifesto e os objetos git — e o que ele existe para fechar.

    O commit de release existe SÓ para acrescentar o manifesto. Sem esta cobrança,
    conteúdo não validado entraria na versão sob a bandeira de uma validação que
    rodou no pai — que é a única coisa que "declarar o pai" poderia custar.
    """
    pai = _git("rev-parse", f"{tag}^")
    if pai != manifesto["commit_sha"]:
        return [f"o manifesto declara commit_sha {manifesto['commit_sha'][:12]}… e o pai de {tag} "
                f"é {pai[:12]}…. O manifesto descreve o commit VALIDADO; se ele não é o pai, a "
                f"validação citada não é sobre este conteúdo."]
    problemas = []
    medido = tree_digest(pai)
    if manifesto["tree_digest"] != medido:
        problemas.append(
            f"tree_digest não confere com a árvore do commit validado: o manifesto declara "
            f"{manifesto['tree_digest'][:19]}… e esta árvore rende {medido[:19]}…. O conteúdo "
            f"versionado de {pai[:12]}… não é o que a release ancorou.")
    mudados = [linha for linha in
               _git("diff", "--name-only", f"{pai}..{tag}^{{commit}}").splitlines() if linha]
    if mudados != [rel]:
        problemas.append(
            f"o commit de release mudou {mudados} além do manifesto. Ele existe só para "
            f"acrescentar o manifesto — qualquer outra mudança entraria na versão sob a "
            f"bandeira de uma validação que rodou no pai.")
    return problemas


def verificar(tag: str) -> list[str]:
    """`--verificar`: a cadeia inteira, contra os objetos git REAIS.

    Roda ANTES de qualquer push (e de novo no CI, sobre a tag publicada). Cobra as
    três coisas que fazem a âncora valer: o manifesto está na árvore taggeada, ele
    descreve o pai, e o commit de release não mudou mais nada.
    """
    versao = tag.lstrip("v")
    rel = f"{PREFIXO}/releases/v{versao}.manifesto.json"
    try:
        bruto = _git("show", f"{tag}:{rel}")
    except Recusa:
        return [f"a árvore de {tag} não contém {rel}. Tag que aponta para commit sem manifesto "
                f"não é release parcial — é ausência de release."]
    try:
        manifesto = json.loads(bruto)
    except json.JSONDecodeError as erro:
        return [f"{rel} em {tag} é ilegível: {erro}"]

    problemas = problemas_de_forma(manifesto)
    if problemas:
        return problemas

    if manifesto["tag"] != tag:
        problemas.append(f"o manifesto em {tag} declara a tag {manifesto['tag']!r}")
    problemas += _problemas_da_cadeia(tag, rel, manifesto)

    versao_taggeada = versao_da_arvore(f"{tag}^{{commit}}")
    if versao_taggeada != versao:
        problemas.append(
            f"a árvore de {tag} declara __version__ == {versao_taggeada!r} e a tag promete "
            f"{versao!r}. A versão do wheel é dinâmica: o artefato sairia com outro número, e dois "
            f"conteúdos passariam a reivindicar a mesma versão.")
    return problemas


def _preflight(versao: str, commit: str) -> tuple[str, str, str]:
    """As recusas que acontecem ANTES de qualquer objeto nascer. (tag, sha, rel).

    Todas aqui em cima de propósito: uma release recusada no meio deixaria um
    commit órfão ou uma tag apagada, e "release parcial" é a categoria que este
    publicador inteiro existe para não ter.
    """
    if not VERSAO_VALIDA.match(versao) or not SEMVER_DE_RELEASE.match(versao):
        raise Recusa(f"versão {versao!r} não é X.Y.Z")
    tag = f"v{versao}"
    if _git("tag", "--list", tag):
        raise Recusa(f"a tag {tag} já existe. Republicar moveria a âncora, que é o gesto que este "
                     f"diretório inteiro existe para tornar visível.")
    sha = _git("rev-parse", commit)
    declarada = versao_da_arvore(sha)
    if declarada != versao:
        raise Recusa(
            f"a árvore de {sha[:12]}… declara __version__ == {declarada!r} e você pediu a tag "
            f"{tag}. A versão do wheel é dinâmica — o artefato sairia com o número errado.")
    rel = f"{PREFIXO}/releases/v{versao}.manifesto.json"
    if _git("ls-tree", "--name-only", sha, rel):
        raise Recusa(f"{rel} já está na árvore de {sha[:12]}… — o commit de release existe para "
                     f"acrescentá-lo, e ele já está lá.")
    return tag, sha, rel


def conferir_mordida(tag: str, autoprova: Path) -> list[str]:
    """O manifesto da tag não pode dizer mais do que a autoprova mediu.

    Uma release que se declarasse `aprovada` com autoprova vermelha seria o selo
    falso que o contrato chama de pior que fiscal nenhum. O sentido único é
    deliberado: a autoprova pode ter medido MAIS do que o manifesto declara (uma
    release `pendente` cujas travas hoje mordem é honesta — ela só não prometeu),
    mas nunca o contrário.
    """
    versao = tag.lstrip("v")
    rel = f"{PREFIXO}/releases/v{versao}.manifesto.json"
    try:
        manifesto = json.loads(_git("show", f"{tag}:{rel}"))
    except (Recusa, json.JSONDecodeError) as erro:
        return [f"não consegui ler o manifesto de {tag}: {erro}"]
    declarada = manifesto.get("mordida") or {}
    if declarada.get("estado") != "aprovada":
        return []
    try:
        medida = mordida_da_autoprova(autoprova)
    except Recusa as erro:
        return [f"o manifesto declara mordida `aprovada` e {erro}"]
    divergentes = [c for c in ("devem_falhar", "smoke_gui", "declarado_sem_mordida")
                   if declarada.get(c) != medida.get(c)]
    if divergentes:
        return [f"o manifesto declara {[declarada.get(c) for c in divergentes]} e a autoprova "
                f"mediu {[medida.get(c) for c in divergentes]} em {divergentes}. O manifesto é "
                f"o que o consumidor guarda; ele não pode dizer mais do que se mediu."]
    return []


def publicar(versao: str, commit: str, mordida: dict, executar: bool) -> int:
    """Emite, commita, tagueia LOCALMENTE e verifica — nesta ordem, sem push."""
    tag, sha, rel = _preflight(versao, commit)
    manifesto = montar_manifesto(versao, sha, mordida)
    texto = serializar(manifesto)
    problemas = problemas_de_forma(manifesto)
    if problemas:
        raise Recusa("manifesto emitido é inválido:\n  " + "\n  ".join(problemas))

    if not executar:
        print(texto, end="")
        print(f"[dry-run] nenhuma ref criada. Use --executar para cortar {tag}.", file=sys.stderr)
        return 0

    if _git("status", "--porcelain"):
        raise Recusa("a árvore de trabalho tem mudanças não commitadas. O commit de release é "
                     "montado a partir do commit validado, e trabalho pendente entraria nele — "
                     "que é exatamente o que `--verificar` existe para tornar impossível.")

    # O ponto de partida é guardado para ser devolvido: o publicador cria a ref e
    # sai, e deixar quem o chamou em detached HEAD sobre o commit de release faria
    # o próximo comando dele agir na árvore errada.
    origem = _git("symbolic-ref", "--quiet", "--short", "HEAD") or _git("rev-parse", "HEAD")
    _git("checkout", "--detach", sha)
    try:
        caminho_do_manifesto(versao).parent.mkdir(parents=True, exist_ok=True)
        caminho_do_manifesto(versao).write_text(texto, encoding="utf-8")
        _git("add", "--", rel)
        _git("commit", "-m", f"release {tag}: manifesto do conteudo validado {sha[:12]}")
        _git("tag", "-a", tag, "-m", f"webqa-suite {versao}")

        problemas = verificar(tag)
        if problemas:
            _git("tag", "-d", tag)
            raise Recusa("a verificação da tag recém-criada falhou (a tag foi apagada):\n  "
                         + "\n  ".join(problemas))
    finally:
        _git("checkout", "--force", origem)
    print(f"{tag} criada localmente sobre {sha[:12]}… e verificada. "
          f"Publique com: git push origin {tag}")
    return 0


def aferir() -> int:
    """Placar das releases desta árvore: toda tag publicada ainda ancora o que dizia?

    Roda no CI de TODO push, e a cobertura é o ponto: a guarda que vive no
    `release.yml` só corre quando a tag nasce, e o gesto perigoso — mover uma tag
    já publicada — acontece depois. Aqui a cadeia é reconferida com o código da
    ponta, contra os objetos git reais, em toda execução.

    Manifesto sem tag correspondente é AVISO com placar, não vermelho, e o estado é
    transitório por construção: o manifesto entra na árvore pelo PR e a tag nasce
    do merge dele. Reprovar aqui tornaria o PR que publica a release impossível de
    mergear — a guarda impediria exatamente o que ela existe para exigir. O que
    fecha a janela é o próprio placar: o número aparece em toda execução, e
    cobertura parcial silenciosa induz mais confiança do que cobertura nenhuma.
    """
    manifestos = sorted(DIR_RELEASES.glob("v*.manifesto.json"))
    if not manifestos:
        print("::warning::nenhum manifesto em releases/ — não há release ancorável")
        return 0
    sem_tag, quebradas = [], []
    for caminho in manifestos:
        tag = caminho.name.removesuffix(".manifesto.json")
        if not _git("tag", "--list", tag):
            sem_tag.append(tag)
            continue
        problemas = verificar(tag)
        if problemas:
            quebradas.append(tag)
            for p in problemas:
                print(f"::error::{tag}: {p}", file=sys.stderr)
    conferidas = len(manifestos) - len(sem_tag) - len(quebradas)
    print(f"releases: {conferidas} ancorada(s) e conferida(s), {len(sem_tag)} aguardando a tag "
          f"({', '.join(sem_tag) or '—'}), {len(quebradas)} com a cadeia quebrada.")
    for tag in sem_tag:
        print(f"::warning::{tag}: manifesto na árvore e tag ainda não publicada. Enquanto isso "
              f"valer, o consumidor não tem o que pinar.")
    return 1 if quebradas else 0


def _relatar(tag: str, problemas: list[str], verde: str) -> int:
    """Imprime e devolve o código. Os problemas vão para stderr como `::error::`
    porque é assim que o log do CI os destaca; o verde vai para stdout."""
    for p in problemas:
        print(f"::error::{tag}: {p}", file=sys.stderr)
    if problemas:
        return 1
    print(f"{tag}: {verde}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aferir", action="store_true",
                        help="confere TODAS as releases desta árvore e imprime o placar")
    parser.add_argument("--versao", help="X.Y.Z da release a publicar")
    parser.add_argument("--commit", default="HEAD", help="commit VALIDADO a taggear")
    parser.add_argument("--executar", action="store_true",
                        help="cria commit de release e tag LOCAIS (nunca faz push)")
    parser.add_argument("--motivo-da-mordida", default="",
                        help="por que a autoprova de mordida está pendente nesta release")
    parser.add_argument("--autoprova", type=Path,
                        help="relatório de scripts/autoprova.py; aprova a mordida desta release")
    parser.add_argument("--verificar", metavar="TAG",
                        help="confere a cadeia de uma tag já existente")
    parser.add_argument("--conferir-mordida", nargs=2, metavar=("TAG", "AUTOPROVA"),
                        help="o manifesto da TAG não diz mais do que a AUTOPROVA mediu")
    args = parser.parse_args(argv)

    try:
        if args.aferir:
            return aferir()
        if args.conferir_mordida:
            tag, autoprova = args.conferir_mordida
            return _relatar(tag, conferir_mordida(tag, Path(autoprova)),
                            "o manifesto não diz mais do que a autoprova mediu.")
        if args.verificar:
            return _relatar(args.verificar, verificar(args.verificar),
                            "manifesto na árvore, cadeia íntegra, versão coerente.")
        if not args.versao:
            parser.error("informe --versao ou --verificar")
        mordida = (mordida_da_autoprova(args.autoprova) if args.autoprova
                   else {"estado": "pendente", "motivo": args.motivo_da_mordida})
        return publicar(args.versao, args.commit, mordida, args.executar)
    except Recusa as erro:
        print(f"::error::release recusada: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
