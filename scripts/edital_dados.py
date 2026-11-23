"""Dados do edital que a LM usa para decidir: prazo de impugnação, garantia de proposta, modo de disputa,
exigência de usina (própria / distância máxima) e quantitativos do atestado de capacidade técnica.
Só registra o que está escrito no edital; o que não achar fica "não informado".
"""
import re

import horario_disputa as h

NI = "não informado"


def _limpo(t):
    return re.sub(r"\s+", " ", h.norm(t))


def _trecho(t, i, antes=0, depois=220):
    return t[max(0, i - antes):i + depois].strip()


def extrair(texto):
    t = _limpo(texto or "")
    if len(t) < 200:
        return None
    d = {}

    # impugnação: data explícita ou "até N dias úteis antes"
    imp = NI
    for m in re.finditer(r"impugna", t):
        j = t[m.start():m.start() + 260]
        dt = re.search(r"(\d{2}/\d{2}/\d{4})(?:\D{0,10}(\d{1,2}[:h]\d{2}))?", j)
        du = re.search(r"(\d+|tres|tr[eê]s|dois|cinco)\s*\(?\w*\)?\s*dias? uteis", j)
        if dt:
            imp = f"até {dt.group(1)}" + (f" {dt.group(2).replace('h', ':')}" if dt.group(2) else "")
            break
        if du:
            imp = f"até {du.group(1)} dias úteis antes da sessão"
            break
    d["impugnacao"] = imp

    # garantia de PROPOSTA (não confundir com garantia de execução do contrato)
    gar = NI
    for m in re.finditer(r"garantia (de|da) proposta", t):
        j = t[m.start():m.start() + 300]
        if re.search(r"nao sera exigid|dispensad|nao exigir", j[:150]):
            gar = "não exigida"
            break
        p = re.search(r"(\d+(?:[,.]\d+)?)\s*%", j)
        v = re.search(r"r\$\s*([\d.]+,\d{2})", j)
        if p or v:
            gar = (f"{p.group(1).replace('.', ',')}% do valor estimado" if p else "") + (" · " if p and v else "") + (f"R$ {v.group(1)}" if v else "")
            break
    d["garantia"] = gar

    m = re.search(r"modo de disputa\W{0,30}(?:sera|e|:)?\W{0,10}(aberto e fechado|fechado e aberto|aberto|fechado)", t)
    d["modoDisputa"] = m.group(1) if m else NI

    # usina de asfalto: própria / instalada / distância máxima
    usina = NI
    for m in re.finditer(r"usina", t):
        j = _trecho(t, m.start(), 120, 260)
        km = re.search(r"(\d{2,3}(?:[,.]\d+)?)\s*(?:km|quilometros)", j)
        if km or re.search(r"propria|instalad|disponibilidade|declaracao", j):
            if re.search(r"asfalt|cbuq|betumin|concreto", j):
                usina = ("distância máxima de " + km.group(1) + " km" if km else "exige usina (própria ou disponível)") + \
                        (" · própria" if re.search(r"usina propria|propria usina", j) else "")
                break
    d["usina"] = usina

    # atestado de capacidade técnica: parcelas de maior relevância com quantidade
    qts = []
    for m in re.finditer(r"capacidade tecnica|parcelas? de maior relevancia|atestado", t):
        j = t[m.start():m.start() + 1500]
        for q in re.finditer(r"([a-z][a-z ,()/-]{6,70}?)\W{1,6}(?:minimo de |quantidade minima de |de )?(\d{1,3}(?:\.\d{3})*(?:,\d+)?)\s*(m2|m²|m3|m³|toneladas|ton\b|t\b|km\b|metros quadrados|metros cubicos)", j):
            nome = re.sub(r"^(e|de|com|em|o|a|os|as)\s+", "", q.group(1).strip(" ,-/"))
            item = f"{nome} {q.group(2)} {q.group(3).replace('m2', 'm²').replace('m3', 'm³')}"
            if item not in qts and len(nome) > 5:
                qts.append(item)
        if qts:
            break
    d["atestado"] = "; ".join(qts[:4]) if qts else NI
    return d
