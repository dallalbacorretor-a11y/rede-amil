"""Coleta a rede da Amil na busca avancada do portal, produto por produto e praca por praca.

https://amil.com.br/portal/web/servicos/saude/rede-credenciada/amil/busca-avancada

Para cada produto da pagina (a rede dele na busca), cada praca que a busca oferece no
estado (a lista de municipios da rede; em SP, as pracas levantadas) e cada tipo de servico
que o portal lista para aquela rede e praca (consultorios, hospitais, laboratorios,
pronto-socorro, pronto atendimento, hemodialise, TEA, telemedicina, vacinacao, rede
preferencial...), pergunta quem atende, sem escolher bairro nem especialidade: vem tudo,
com a especialidade de cada linha.

A cobertura e por praca: a busca por uma cidade traz a rede da regiao, e o mesmo
prestador pode estar em 11 produtos partindo de Curitiba e em 2 partindo de Pinhais. Cada
unidade (credenciado x endereco) guarda em "pp" os produtos de cada praca em que
apareceu; "produtos" e o que vale para quem e da cidade da unidade: a praca da propria
cidade, ou, se a busca nao oferece a cidade como praca daquele produto, qualquer praca
que a traga.

Conferencia: uma busca SEM tipo de servico por produto e praca (a rede inteira de uma
vez). O que so aparecer nela entra (sem tipo) e o relatorio conta.

Grava ferramentas/amil/<UF>/<CIDADE>.json (cidade com unidade ou que e praca),
ferramentas/amil/_fora_<UF>.json (quem a busca do estado traz de outro estado) e
ferramentas/amil/_coleta_<UF>.json (data, pracas por produto, tipos, conferencia). O
montar.py faz a pagina a partir deles; o comparativo do rede-amil-bradesco le os mesmos
arquivos. Respostas em ferramentas/.cache/<data>/ (fora do git): rodar de novo no mesmo
dia retoma de onde parou.

Uso: python3 ferramentas/coletar.py PR SC SP [--paralelo 6] [--cache DIR]
"""
import argparse
import html as H
import http.cookiejar
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "ferramentas" / "amil"
PORTAL = "https://amil.com.br"
PAGINA = PORTAL + "/portal/web/servicos/saude/rede-credenciada/amil/busca-avancada"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# produto da pagina -> redes da busca avancada (QP; QC e a mesma rede). Conferido pelos
# hospitais de Curitiba: a mesma lista, produto a produto.
REDES = {
    "PR": {"bronze": [1123], "prata": [1079], "ouro": [1074], "platinum": [1081], "s80": [877],
           "s380": [884], "s450": [879], "s750": [880], "black": [1134, 1136], "s2500": [881],
           "s6500black": [882]},
    "SC": {"prata": [1079], "ouro": [1074], "platinum": [1081], "platmais": [1069], "s80sc": [1004],
           "s380": [884], "s450": [879], "s750": [880]},
    "SP": {"prata": [1079], "ouro": [1074], "platinum": [1081], "s380": [884], "s450": [879],
           "s750": [880], "black": [1134, 1136], "s2500": [881], "s6500black": [882]},
}
# em SP a Amil vende em mais de 200 municipios: a coleta fica na capital, na Grande Sao
# Paulo e nas principais cidades do interior e do litoral
PRACAS_SP = ["ARUJA", "BARUERI", "BAURU", "CAJAMAR", "CAMPINAS", "CAMPO LIMPO PAULISTA", "CAPIVARI",
             "CARAPICUIBA", "COTIA", "CUBATAO", "DIADEMA", "EMBU DAS ARTES", "GUARAREMA", "GUARUJA",
             "GUARULHOS", "ITAPECERICA DA SERRA", "ITAPEVI", "JACAREI", "JANDIRA", "JUNDIAI",
             "LOUVEIRA", "MAUA", "OSASCO", "PIRACICABA", "PRAIA GRANDE", "RIBEIRAO PIRES",
             "RIBEIRAO PRETO", "RIO GRANDE DA SERRA", "ROSEIRA", "SANTANA DE PARNAIBA", "SANTO ANDRE",
             "SANTOS", "SAO BERNARDO DO CAMPO", "SAO CAETANO DO SUL", "SAO JOSE DOS CAMPOS",
             "SAO PAULO", "SAO VICENTE", "SOROCABA", "TABOAO DA SERRA", "VALINHOS",
             "VARGEM GRANDE PAULISTA", "VARZEA PAULISTA", "VINHEDO", "VOTORANTIM"]
# Curitiba e regiao metropolitana: todas ganham arquivo, mesmo a que a busca nao oferece
RMC = ["ADRIANOPOLIS", "AGUDOS DO SUL", "ALMIRANTE TAMANDARE", "ARAUCARIA", "BALSA NOVA",
       "BOCAIUVA DO SUL", "CAMPINA GRANDE DO SUL", "CAMPO DO TENENTE", "CAMPO LARGO", "CAMPO MAGRO",
       "CERRO AZUL", "COLOMBO", "CONTENDA", "CURITIBA", "DOUTOR ULYSSES", "FAZENDA RIO GRANDE",
       "ITAPERUCU", "LAPA", "MANDIRITUBA", "PIEN", "PINHAIS", "PIRAQUARA", "QUATRO BARRAS",
       "QUITANDINHA", "RIO BRANCO DO SUL", "RIO NEGRO", "SAO JOSE DOS PINHAIS", "TIJUCAS DO SUL",
       "TUNAS DO PARANA"]
# selo de qualificacao (icone da busca) -> sigla que a pagina mostra
SELOS = {"a": "ACRED", "e": "TE", "r": "RES", "p": "ESP", "n": "COMUN", "d": "PROFI", "g": "CERTI",
         "q": "QUALI", "i": "ISO"}

_cj = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
_trava = threading.Lock()
_redes = {}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").upper()


def arquivo(t):
    return re.sub(r"[^A-Z0-9]+", "_", sem_acento(t)).strip("_")


def pede(caminho, json_=False):
    h = {"User-Agent": UA, "Referer": PAGINA, "X-Requested-With": "XMLHttpRequest"}
    if json_:
        h["Accept"] = "application/vnd.amil.busca-credenciado.v2+json"
    url = PORTAL + caminho.replace("https://amil.com.br:443", "").replace(PORTAL, "")
    for tentativa in range(6):
        try:
            with _op.open(urllib.request.Request(url, headers=h), timeout=120) as r:
                t = r.read().decode()
            return json.loads(t) if json_ else t
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                return None
            if tentativa == 5:
                raise
            time.sleep(2 ** tentativa)


def inicia():
    with _trava:
        if not _redes:
            pede("/portal/web/servicos/saude/rede-credenciada/amil/busca-avancada")   # cookies
            for r in pede("/portal/web/servicos/saude/rede-credenciada/amil/redes-comercializadas",
                          json_=True)["redes"]:
                _redes[r["rede"]["codigo"]] = r["rede"]


def municipios(rede, uf):
    d = pede(f"/portal/web/servicos/saude/rede-credenciada/{rede}/estado/{uf.lower()}", json_=True)
    return {sem_acento(m["value"]): m["value"] for m in (d or {}).get("municipios", [])}


def tipos_servico(rede, uf, municipio):
    m = urllib.parse.quote(municipio)
    d = pede(f"/portal/web/servicos/saude/rede-credenciada/{rede}/estado/{uf.lower()}/municipio/{m}"
             f"/bairro/TODOS%20OS%20BAIRROS/tipos-servicos", json_=True)
    return [t["value"] for t in (d or {}).get("tiposServicos", [])]


def resultado(rede, uf, municipio, tipo="", nome=""):
    q = [("plano.codigo", ""), ("filtro.codigoPlano", ""), ("filtro.operadora", _redes[rede]["operadora"]),
         ("filtro.contexto", "amil"), ("filtro.linha", ""), ("identificacao", ""),
         ("filtro.codigoRede", str(rede)), ("filtro.uf", uf), ("filtro.municipio", municipio),
         ("filtro.bairro", "TODOS OS BAIRROS"), ("filtro.tipoServico", tipo),
         ("filtro.especialidade", ""), ("filtro.nomeCredenciado", nome)]
    return pede("/portal/web/servicos/saude/rede-credenciada/resultado-partial?" + urllib.parse.urlencode(q))


def total(html):
    m = re.search(r"localizou\s*(?:<[^>]+>\s*)*([\d.]+)", html or "")
    return int(m.group(1).replace(".", "")) if m else 0


def unidades(html):
    """Unidades de um resultado: {(codigo do credenciado, logradouro): unidade}."""
    out = {}
    for tab in re.split(r'<table class="tabelaBusca">', html or "")[1:]:
        m = re.search(r'credenciado-especialidade">([^<]*)<', tab)
        esp = H.unescape(m.group(1).strip()) if m else ""
        for cred in re.split(r'<tr class="credenciado', tab)[1:]:
            nome = re.search(r'nomeFantasia">([^<]*)<', cred)
            cnpj = re.search(r"CNPJ:\s*([\d./-]+)", cred)
            selos = re.findall(r'class="icn-([a-z])', cred.split('<tr class="estabelecimento')[0])
            for est in re.split(r'<tr class="estabelecimento', cred)[1:]:
                idm = re.search(r'id="dados-endereco-credenciado-([\d-]+)"', est)

                def span(c):
                    m = re.search(r'class="' + c + r'"[^>]*>([^<]*)<', est)
                    return H.unescape(m.group(1).strip()) if m else ""

                def valor(c):
                    m = re.search(r'class="' + c + r'" value="([^"]*)"', est)
                    return H.unescape(m.group(1).strip()) if m else ""
                cod = idm.group(1).split("-")[0] if idm else ""
                k = (cod, span("logradouro"))
                u = out.setdefault(k, {
                    "cod": cod, "nome": H.unescape(nome.group(1).strip()) if nome else "",
                    "cnpj": re.sub(r"\D", "", cnpj.group(1)) if cnpj else "",
                    "end": span("logradouro"), "compl": span("complemento"), "cep": span("cep"),
                    "cidade": sem_acento(valor("cidade")), "uf": valor("estado"),
                    "lat": valor("latitude"), "lon": valor("longitude"),
                    "tel": [H.unescape(t.strip()) for t in re.findall(r'class="telefone">([^<]*)<', est)],
                    "bairro": span("bairro"), "selos": selos, "esp": []})
                if esp and esp not in u["esp"]:
                    u["esp"].append(esp)
    return out


class Coleta:
    def __init__(self, uf, cache, paralelo):
        self.uf, self.cache, self.paralelo = uf, cache, paralelo
        self.cache.mkdir(parents=True, exist_ok=True)
        self.produtos = REDES[uf]
        self.prod_de = {r: p for p, rs in self.produtos.items() for r in rs}
        self.redes = sorted(self.prod_de)

    def em_cache(self, nome, gerar, json_=False):
        """Resposta guardada, ou pede; erro do portal (500 numa consulta grande) vira None, sem
        gravar, para a proxima tentativa pedir de novo."""
        arq = self.cache / nome
        if arq.exists():
            t = arq.read_text(encoding="utf-8")
            return json.loads(t) if json_ else t
        try:
            v = gerar()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"    falhou {nome}: {str(e)[:80]}", flush=True)
            return None
        arq.write_text(json.dumps(v, ensure_ascii=False) if json_ else (v or ""), encoding="utf-8")
        return v if json_ else (v or "")

    def com_nova_tentativa(self, f, itens, rotulo, obrigatorio=True):
        """Roda f em paralelo; o que falhar e tentado de novo, um de cada vez, com pausa. Se a
        consulta e obrigatoria e continua falhando, para: melhor nao gravar o estado do que
        gravar com um pedaco faltando."""
        res = dict(self.paralelo_map(f, itens, rotulo))
        for volta in range(3):
            falta = [k for k, v in res.items() if v is None]
            if not falta:
                break
            print(f"    {len(falta)} com erro, nova tentativa ({volta + 1})…", flush=True)
            time.sleep(30 * (volta + 1))
            for k in falta:
                res[k] = f(k)[1]
        falta = [k for k, v in res.items() if v is None]
        if falta and obrigatorio:
            sys.exit(f"{self.uf}: {len(falta)} consultas continuam com erro ({falta[:3]}...); "
                     "nada gravado, rode de novo mais tarde (o que ja veio fica no cache)")
        return res, falta

    def paralelo_map(self, f, itens, rotulo):
        inicio, out = time.time(), []
        print(f"  {rotulo}: {len(itens)}…", flush=True)
        with ThreadPoolExecutor(self.paralelo) as ex:
            for n, r in enumerate(ex.map(f, itens), 1):
                out.append(r)
                if n % 500 == 0:
                    print(f"    {n}/{len(itens)} · {time.time() - inicio:.0f}s", flush=True)
        return out

    def coleta(self):
        uf = self.uf
        inicia()
        # pracas de cada rede (nome como a busca escreve)
        muns = {r: self.em_cache(f"{r}-{uf}-municipios.json", lambda r=r: municipios(r, uf), json_=True)
                for r in self.redes}
        if uf == "SP":
            muns = {r: {k: v for k, v in m.items() if k in PRACAS_SP} for r, m in muns.items()}
        pares = [(r, c) for r in self.redes for c in sorted(muns[r])]

        def tipos(t):
            r, c = t
            return t, self.em_cache(f"{r}-{uf}-{arquivo(c)}-tipos.json",
                                    lambda: tipos_servico(r, uf, muns[r][c]), json_=True)
        tipos_de, _ = self.com_nova_tentativa(tipos, pares, f"{uf}: tipos de servico por produto e praca")
        tarefas = [(r, c, t) for (r, c), ts in tipos_de.items() for t in ts]

        def busca(t):
            r, c, tipo = t
            return t, self.em_cache(f"{r}-{uf}-{arquivo(c)}-{arquivo(tipo)}.html",
                                    lambda: resultado(r, uf, muns[r][c], tipo))
        U = {}
        respostas, _ = self.com_nova_tentativa(busca, tarefas, f"{uf}: consultas por tipo")
        # a busca de uma praca traz tambem quem fica em outro estado (o Hospital Bom Jesus de
        # Rio Negro/PR na busca de Mafra/SC): fica, guardado a parte
        for (r, praca, tipo), html in respostas.items():
            for k, u in unidades(html).items():
                x = U.setdefault((u["uf"], u["cidade"]) + k, dict(u, esp={}, pp={}, tipos=[], selos=[]))
                x["pp"].setdefault(praca, set()).add(self.prod_de[r])
                if tipo not in x["tipos"]:
                    x["tipos"].append(tipo)
                es = x["esp"].setdefault(tipo, [])
                es += [e for e in u["esp"] if e not in es]
                x["selos"] += [s for s in u["selos"] if s not in x["selos"]]
                for c in ("tel",):
                    x[c] += [t for t in u[c] if t not in x[c]]

        # conferencia: a busca sem tipo, por produto e praca
        def sem_tipo(t):
            r, c = t
            return t, self.em_cache(f"{r}-{uf}-{arquivo(c)}-SEM_TIPO.html", lambda: resultado(r, uf, muns[r][c]))
        so_sem_tipo, soma_sem_tipo = [], 0
        respostas, sem_conferencia = self.com_nova_tentativa(sem_tipo, pares, f"{uf}: conferencia sem tipo",
                                                             obrigatorio=False)
        for (r, praca), html in respostas.items():
            if html is None:
                continue
            soma_sem_tipo += total(html)
            for k, u in unidades(html).items():
                x = U.get((u["uf"], u["cidade"]) + k)
                if x and self.prod_de[r] in x["pp"].get(praca, ()):
                    continue
                if not x:
                    x = U[(u["uf"], u["cidade"]) + k] = dict(u, esp={"": list(u["esp"])}, pp={}, tipos=[""],
                                                              selos=[])
                    x["selos"] = list(u["selos"])
                x["pp"].setdefault(praca, set()).add(self.prod_de[r])
                so_sem_tipo.append({"praca": praca, "produto": self.prod_de[r], "nome": u["nome"],
                                    "end": u["end"], "cidade": u["cidade"]})

        # produtos de quem e da cidade: a praca dela, ou qualquer uma se ela nao e praca do produto
        pracas_de = {p: set().union(*(set(muns[r]) for r in rs)) for p, rs in self.produtos.items()}
        por_cidade, fora = {}, []
        for (uf_u, cidade, *_), x in U.items():
            prods = []
            for p in self.produtos:
                if uf_u == uf and cidade in pracas_de[p]:
                    tem = p in x["pp"].get(cidade, ())
                else:
                    tem = any(p in s for s in x["pp"].values())
                if tem:
                    prods.append(p)
            x["produtos"] = prods
            x["pp"] = {c: [p for p in self.produtos if p in s] for c, s in sorted(x["pp"].items())}
            x["selos"] = [SELOS.get(s, s.upper()) for s in x["selos"]]
            if uf_u == uf:
                por_cidade.setdefault(cidade, []).append(x)
            else:
                fora.append(x)
        todas_pracas = set().union(*pracas_de.values())
        cidades = set(por_cidade) | todas_pracas | (set(RMC) if uf == "PR" else set())
        hoje = date.today().isoformat()
        PASTA.joinpath(uf).mkdir(parents=True, exist_ok=True)
        for velho in PASTA.joinpath(uf).glob("*.json"):
            if velho.stem not in cidades:
                velho.unlink()
        for c in sorted(cidades):
            lista = sorted(por_cidade.get(c, []), key=lambda u: (u["nome"], u["end"]))
            (PASTA / uf / f"{c}.json").write_text(json.dumps({
                "cidade": c, "uf": uf, "data": hoje, "fonte": PAGINA, "praca": c in todas_pracas,
                "unidades": lista}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (PASTA / f"_fora_{uf}.json").write_text(json.dumps(
            sorted(fora, key=lambda u: (u["uf"], u["cidade"], u["nome"])), ensure_ascii=False,
            separators=(",", ":")), encoding="utf-8")
        tipos_vistos = sorted({t for ts in tipos_de.values() for t in ts})
        (PASTA / f"_coleta_{uf}.json").write_text(json.dumps({
            "uf": uf, "data": hoje, "fonte": PAGINA,
            "pracas": {p: sorted(s) for p, s in pracas_de.items()},
            "tipos": tipos_vistos, "consultas": len(tarefas) + len(pares) * 2,
            "conferencia": {"soma_sem_tipo": soma_sem_tipo, "so_sem_tipo": so_sem_tipo,
                            "sem_resposta": [{"produto": self.prod_de[r], "praca": c}
                                             for r, c in sem_conferencia]}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        n = sum(len(v) for v in por_cidade.values())
        print(f"{uf}: {n} unidades em {len(por_cidade)} cidades (e {len(fora)} de outro estado), "
              f"{len(todas_pracas)} pracas, "
              f"{len(tarefas)} consultas por tipo ({', '.join(tipos_vistos)}); "
              f"{len(so_sem_tipo)} so na busca sem tipo", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ufs", nargs="+")
    ap.add_argument("--paralelo", type=int, default=6)
    ap.add_argument("--cache", help="pasta das respostas (padrao: ferramentas/.cache/<data de hoje>)")
    a = ap.parse_args()
    cache = Path(a.cache) if a.cache else RAIZ / "ferramentas" / ".cache" / date.today().isoformat()
    for uf in a.ufs:
        Coleta(uf.upper(), cache, a.paralelo).coleta()


if __name__ == "__main__":
    main()
