"""Monta a pagina (index.html) a partir da coleta da busca avancada (coletar.py).

Para cada estado coletado (ferramentas/amil/_coleta_<UF>.json e <UF>/<CIDADE>.json) troca
window.DADOS_UF[<UF>] na pagina: um prestador por CNPJ (o da filial; medico sem CNPJ, pelo
codigo do credenciado), com todos os enderecos dele, as pracas em que a busca o traz e os
produtos de cada praca, as categorias (o tipo de servico da busca) com as especialidades de
cada uma e os selos de qualificacao. O que nao vem da busca (nome do produto na tela, linha,
cor e onde a Amil vende) continua o da pagina.

Uso: python3 ferramentas/montar.py
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = RAIZ / "index.html"
PASTA = RAIZ / "ferramentas" / "amil"
MARCA = "window.DADOS_UF="

# tipo de servico da busca -> categoria da pagina
CATEGORIA = {
    "HOSPITAIS PARA INTERNACAO": "Hospitais",
    "PRONTO-SOCORRO 24H (URGENCIA E EMERGENCIA)": "Pronto-socorro 24h",
    "PRONTO ATENDIMENTO - HORARIO COMERCIAL": "Pronto atendimento",
    "CONSULTORIOS - CLINICAS - TERAPIAS": "Clinicas e consultorios",
    "LABORATORIOS E EXAMES": "Laboratorios e imagem",
    "HEMODIALISE": "Hemodialise",
    "CONSULTA POR TELEMEDICINA": "Telemedicina",
    "TEA": "TEA",
    "CENTROS DE VACINACAO": "Centros De Vacinacao",
    "REDE PREFERENCIAL": "Rede Preferencial",
}
# as que a pagina oferece no filtro, nesta ordem (vacinacao e rede preferencial ficam no
# dado de quem as tem, como antes)
CATEGORIAS = ["Hospitais", "Pronto-socorro 24h", "Pronto atendimento", "Clinicas e consultorios",
              "Laboratorios e imagem", "Hemodialise", "Telemedicina", "TEA"]
ESTADO = {"PR": "Paraná", "SC": "Santa Catarina", "SP": "São Paulo"}


def data_br(iso):
    return "/".join(reversed(iso.split("-")))


def cnpj_fmt(c):
    c = re.sub(r"\D", "", c or "")
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else ""


def endereco(u):
    return " ".join((u["end"] + " " + (u.get("compl") or "")).split())


def coord(u):
    try:
        la, lo = float(u["lat"]), float(u["lon"])
    except (TypeError, ValueError, KeyError):
        return None
    return (round(la, 5), round(lo, 5)) if la and lo else None


def montar_uf(uf, antigo):
    meta = json.loads((PASTA / f"_coleta_{uf}.json").read_text(encoding="utf-8"))
    unidades = []
    for f in sorted((PASTA / uf).glob("*.json")):
        unidades += json.loads(f.read_text(encoding="utf-8"))["unidades"]
    # quem a busca do estado traz de outro estado (cidade vizinha na divisa, telemedicina)
    fora = PASTA / f"_fora_{uf}.json"
    if fora.exists():
        unidades += json.loads(fora.read_text(encoding="utf-8"))
    produtos_antigos = {p["codigo"]: p for p in antigo.get("produtos", [])}
    ordem_prod = list(meta["pracas"])
    grupos = {}
    for u in sorted(unidades, key=lambda u: (u["nome"], u["cidade"], u["end"])):
        chave = u["cnpj"] if len(u["cnpj"] or "") == 14 else "cod:" + u["cod"]
        grupos.setdefault(chave, []).append(u)

    prestadores, centros = [], {}
    for chave, us in grupos.items():
        pp, cats, esp, pc, selos, tel, bairros, ends = {}, set(), set(), {}, [], set(), set(), set()
        for u in us:
            for praca, prods in u["pp"].items():
                pp.setdefault(praca, set()).update(prods)
            for tipo, es in u["esp"].items():
                cat = CATEGORIA.get(tipo, tipo.title()) if tipo else None
                esp.update(es)
                if cat:
                    cats.add(cat)
                    pc.setdefault(cat, set()).update(es)
            selos += [s for s in u["selos"] if s not in selos]
            tel.update(u["tel"])
            if u["bairro"]:
                bairros.add(u["bairro"])
            ends.add(endereco(u))
            xy = coord(u)
            if xy and u["uf"] == uf:
                c = centros.setdefault(f"{u['bairro']}|{u['cidade']}", [0.0, 0.0, 0])
                c[0] += xy[0]
                c[1] += xy[1]
                c[2] += 1
        cats_ord = sorted(cats)
        principal = next((c for c in CATEGORIAS if c in cats), cats_ord[0] if cats_ord else "")
        todos = set().union(*pp.values()) if pp else set()
        # o ponto do mapa e o do primeiro endereco da lista
        us_xy = sorted((u for u in us if coord(u)), key=endereco)
        xy = coord(us_xy[0]) if us_xy else None
        prestadores.append({
            "n": " ".join(us[0]["nome"].split()), "c": cnpj_fmt(us[0]["cnpj"]), "cid": sorted(pp),
            "pp": {k: [p for p in ordem_prod if p in v] for k, v in sorted(pp.items())},
            "cr": sorted({u["cidade"] for u in us}), "b": sorted(bairros), "e": sorted(ends),
            "t": sorted(tel), "p": [p for p in ordem_prod if p in todos], "cat": principal, "cats": cats_ord,
            "esp": sorted(esp), "pc": {k: sorted(v) for k, v in sorted(pc.items())}, "s": sorted(selos),
            "xy": list(xy) if xy else None})
    prestadores.sort(key=lambda p: (CATEGORIAS.index(p["cat"]) if p["cat"] in CATEGORIAS else 99, p["n"]))

    produtos = []
    for cod in ordem_prod:
        p = dict(produtos_antigos.get(cod) or {"codigo": cod, "rotulo": cod.title(), "acomodacao": "",
                                                "linha": "", "cor": "#2733c4"})
        p["pracas"] = meta["pracas"][cod]
        produtos.append(p)
    pracas = sorted(set().union(*map(set, meta["pracas"].values())))
    nota = (f"capital, Grande São Paulo e principais cidades do interior — {len(pracas)} municípios "
            "levantados") if uf == "SP" else ""
    return {
        "gerado_em": data_br(meta["data"]),
        "centros": {k: [round(v[0] / v[2], 5), round(v[1] / v[2], 5), v[2]] for k, v in centros.items()},
        "uf": uf, "estado": ESTADO.get(uf, uf), "nota": nota, "produtos": produtos,
        "categorias": CATEGORIAS, "prestadores": prestadores}


def main():
    html = PAGINA.read_text(encoding="utf-8")
    ini = html.index(MARCA) + len(MARCA)
    dados, fim = json.JSONDecoder().raw_decode(html, ini)
    ufs = sorted(re.match(r"_coleta_(\w+)\.json", f.name).group(1) for f in PASTA.glob("_coleta_*.json"))
    if not ufs:
        sys.exit("nada em ferramentas/amil/: rode antes o coletar.py")
    for uf in ufs:
        antes = dados.get(uf, {})
        dados[uf] = montar_uf(uf, antes)
        d = dados[uf]
        hosp = sum(1 for p in d["prestadores"] if p["cat"] == "Hospitais")
        cid = {c for p in d["prestadores"] for c in p["cr"]}
        print(f"{uf}: {len(d['prestadores'])} prestadores (antes {len(antes.get('prestadores', []))}), "
              f"{hosp} hospitais, {len(cid)} cidades, base de {d['gerado_em']}", flush=True)
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    PAGINA.write_text(html[:ini] + texto + html[fim:], encoding="utf-8")


if __name__ == "__main__":
    main()
