"""Entendimento prévio da obra, feito ANTES de lançar no controle: que obra é, onde, de que tamanho e se é do
perfil da LM. O resultado vai em triagem.obra (aparece no card como "Obra: ...").

entender(objeto, valor, texto_docs="") -> {"resumo": str, "tipo": str, "perfil": "sim"|"conferir"|"nao", "porque": str}
"""
import re

import horario_disputa as h

TIPOS = [   # (nome, regex, perfil) — a primeira que bater define o tipo
    ("Fornecimento de massa asfáltica / material", r"^(.{0,80})(fornecimento|aquisicao|compra)\b.{0,60}(cbuq|massa asfaltica|concreto (betuminoso|asfaltico)|\bpmf\b|pre-?misturado|emulsao|\bcap\b|cimento asfaltico)", "sim"),
    ("Pavimentação asfáltica", r"pavimentacao asfaltica|\bcbuq\b|\bcauq\b|concreto (betuminoso|asfaltico)|asfaltamento", "sim"),
    ("Recapeamento / fresagem", r"recapeamento|fresagem", "sim"),
    ("Restauração / recuperação de pavimento", r"(restaura|recupera|reforc)\w* (estrutural )?(d[aeo]s? |de )?pavimen", "sim"),
    ("Tapa-buracos / PMF / tratamento superficial", r"tapa\s*-?\s*buraco|\bpmf\b|tratamento superficial|\btsd\b|microrrevestimento|micro revestimento", "sim"),
    ("Manutenção / conservação rodoviária", r"(manutencao|conservacao)\w* rodovi|conservacao/recuperacao|\bcrema\b|\bpato\b", "sim"),
    ("Pavimentação (tipo a confirmar)", r"pavimenta", "conferir"),
    ("Duplicação / implantação de rodovia", r"duplica|implantacao (e pavimentacao )?d[ae] (rodovia|trecho|estrada)", "sim"),
    ("Melhoria / conservação de estradas e vias", r"(conserva|manuten|recupera|melhoria|readequa|restaura)\w* (d[aeo]s? |de |em |nas? )?(malha viaria|vias?|estradas?|rodovias?|vicinais?|ruas?)", "conferir"),
    ("Infraestrutura viária / urbana", r"infraestrutura (viaria|urbana|rural)|obras? viarias?|sistema viario", "conferir"),
    ("Ponte / obra de arte especial", r"\bpontes?\b|viaduto|obras? de artes? especia|\boae\b|encabecamento", "conferir"),
    ("Estabilização de taludes / contenção", r"talude|contencao|eliminacao de pontos criticos|erosao", "conferir"),
    ("Drenagem", r"drenagem|aguas pluviais|galeria", "conferir"),
    ("Sinalização", r"sinalizacao", "nao"),
]
PAV_DOCS = r"sub-?\s?leito|sub-?\s?base|brita graduada|\bbgs\b|imprimacao|pintura de ligacao|\bcbuq\b|concreto asfaltico|revestimento asfaltico|recapeamento|fresagem|\bpmf\b|tratamento superficial"
RX_RODOVIA = re.compile(r"\b(br|mg|mgc|lmg|amg|cmg)\s*-?\s*(\d{2,3})\b", re.I)


def _num(s):
    return float(s.replace(".", "").replace(",", "."))


def entender(objeto, valor=None, texto_docs=""):
    n = h.norm(objeto)
    tipo, perfil = "Obra a identificar", "conferir"
    for nome, rx, p in TIPOS:
        if nome.startswith("Fornecimento") and re.search(r"execu|pavimentacao|servicos? de|\bobras?\b|recapeamento", n):
            continue   # obra com fornecimento de material é obra, não compra de material
        if re.search(rx, n):
            tipo, perfil = nome, p
            break
    partes = [tipo]
    rod = sorted({f"{a.upper()}-{b}" for a, b in RX_RODOVIA.findall(objeto)})
    if rod:
        partes.append(", ".join(rod[:3]))
    km = re.search(r"km\s*([\d.,]+)\s*(?:ao|a|at[eé])\s*(?:o\s*)?km\s*([\d.,]+)", objeto, re.I)
    ext = re.search(r"([\d.]+(?:,\d+)?)\s*(km|m2|m²|m3|m³|m)\b\s*(?:de extens[aã]o)?", objeto, re.I)
    if km:
        try:
            partes.append(f"km {km.group(1)} a {km.group(2)} ({abs(_num(km.group(2)) - _num(km.group(1))):.1f} km)")
        except ValueError:
            partes.append(f"km {km.group(1)} a {km.group(2)}")
    elif ext and re.search(r"extens|km|m2|m²|m3|m³", ext.group(0), re.I):
        partes.append(f"{ext.group(1)} {ext.group(2).replace('m2', 'm²').replace('m3', 'm³')}")
    if valor:
        partes.append(f"R$ {valor / 1e6:.1f} mi".replace(".", ",") if valor >= 1e6 else f"R$ {valor / 1e3:.0f} mil")
    porque = ""
    # obra que o objeto não deixa claro: os documentos decidem
    if perfil == "conferir" and texto_docs:
        achou = sorted({m.group(0) for m in re.finditer(PAV_DOCS, h.norm(texto_docs))})
        if achou:
            perfil, porque = "sim", "documentos têm " + ", ".join(achou[:5])
        else:
            perfil, porque = "nao", "documentos sem serviços de pavimento"
    return {"resumo": " · ".join(partes), "tipo": tipo, "perfil": perfil, "porque": porque}
