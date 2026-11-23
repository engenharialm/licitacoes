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

    # garantia de PROPOSTA (não confundir com garantia de execução do contrato nem garantia adicional)
    gar, pct = NI, None
    for m in re.finditer(r"garantia (de|da|para (a )?participacao|de participacao)\s*(proposta|participacao|na licitacao)?", t):
        j = t[m.start():m.start() + 350]
        if not re.search(r"proposta|participacao", j[:60]):
            continue
        if re.search(r"nao sera exigid|dispensad|nao exigir|nao havera|sem exigencia", j[:200]):
            gar = "não exigida"
            break
        p = re.search(r"(\d+(?:[,.]\d+)?)\s*%", j)
        v = re.search(r"r\$\s*([\d.]+,\d{2})", j)
        if p and float(p.group(1).replace(",", ".")) <= 5:
            pct = float(p.group(1).replace(",", "."))
            gar = f"{p.group(1).replace('.', ',')}% do valor estimado"
            break
        if v:
            gar = f"R$ {v.group(1)}"
            break
    d["garantia"], d["garantiaPct"] = gar, pct

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

    # atestado de capacidade técnica: parcelas de maior relevância com quantidade mínima
    UN = r"(m2|m²|m3|m³|toneladas|ton\b|t\b|km\b|metros quadrados|metros cubicos|metros lineares|ml\b|m\b|unidades?|un\b)"
    SERV_ATESTADO = r"pavimen|cbuq|asfalt|betumin|base|sub-?base|subleito|imprima|pintura de ligacao|meio-?fio|sarjeta|drenag|concreto|fresag|recape|terraplen|escava|tubo|bloquete|intertravad|calcamento|reperfil|tratamento superficial|regulariza|compacta|aterro|ponte|galeria|sinaliza|lama asfaltica|microrrevest|remendo|tapa"
    qts = []
    for m in re.finditer(r"parcelas? de maior relevancia|capacidade tecnica[- ]operacional|capacidade tecnico[- ]operacional|atestados? de capacidade tecnica", t):
        j = t[m.start():m.start() + 3000]
        for q in re.finditer(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)\s*" + UN, j):
            antes = j[max(0, q.start() - 260):q.start()]
            # tira o "quantidade igual ou superior a", "minimo de" etc. que fica entre o serviço e o número
            antes = re.sub(r"(,?\s*(com |em )?(quantidade|quantitativo)s?( minim[ao]s?)?( igual ou superior a| de| equivalente a)?|exigencia minima|no minimo|minimo de|igual ou superior a|correspondente a)\W*$", "", antes.strip(" :;,-")).strip(" :;,-")
            corte = max(antes.rfind(x) for x in (";", ": ", " - ", "a) ", "b) ", "c) ", "d) ", "e) ", "\u2022", ". "))
            nome = antes[corte + 1:] if corte >= 0 else antes[-120:]
            nome = re.sub(r"^[\W\d.]*(\w\)\s*)?", "", nome).strip(" ,-/.:")
            # só linhas que são serviço de obra (evita e-mail, prazos, transporte de caminhão etc.)
            if len(nome) < 8 or not re.search(SERV_ATESTADO, nome) or re.search(r"\b(prazo|dias|meses|anos|percent|valor|r\$|lei|resolucao|pagina|caminhao|transporte)\b", nome):
                continue
            un = q.group(2).replace("m2", "m²").replace("m3", "m³").replace("metros quadrados", "m²").replace("metros cubicos", "m³")
            item = f"{nome[-110:]}: {q.group(1)} {un}"
            if item not in qts:
                qts.append(item)
        if qts:
            break
    d["atestado"] = "; ".join(qts[:6]) if qts else NI
    return d
