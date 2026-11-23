"""Uma licitação = um registro. Todos os robôs (PNCP, Alerta, DNIT, DER, triagem) chamam ja_existe() antes de lançar.

É a mesma licitação quando, comparando com o que já está no controle:
  - mesmo número/ano e mesmo órgão (ou mesma cidade); ou
  - mesma cidade/órgão e objeto parecido (≥ 50% das palavras); ou
  - mesma cidade/órgão, mesmo dia de sessão e objeto com alguma semelhança (≥ 25%).
"""
import re

import horario_disputa as h

PARAR = {"contratacao", "empresa", "especializada", "execucao", "servicos", "municipio", "prefeitura", "municipal",
         "conforme", "edital", "anexos", "objeto", "para", "com", "minas", "gerais", "estado", "obras", "obra"}


def palavras(s):
    s = re.sub(r"^\s*\[[^\]]*\]", "", h.norm(s))
    return {w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 3 and w not in PARAR}


def parecido(a, b):
    a, b = palavras(a), palavras(b)
    return len(a & b) / len(a | b) if a and b else 0.0


def lugar(s):
    s = h.norm(s)
    s = re.sub(r"\(.*?\)|municipio de |prefeitura (municipal )?de |camara municipal de ", "", s)
    return re.sub(r"[^a-z]", "", s)


def numero(s):
    """'Pregão 85/2026 — Proc. ...', '000069/2026', '18/2026MEI' -> ('85', '2026')"""
    m = re.search(r"(\d+)\s*/\s*(\d{4})", (s or "").split("—")[0])
    return (str(int(m.group(1))), m.group(2)) if m else None


def ja_existe(existentes, objeto, orgao="", cidade="", num=None, data=""):
    """existentes: dict id -> campos. Devolve o id do registro que já representa esta licitação, ou None."""
    lo, lc = lugar(orgao), lugar(cidade)
    num = num if isinstance(num, tuple) or num is None else numero(num)
    dia = (data or "")[:10]
    for i, f in existentes.items():
        fo, fc = lugar(f.get("orgao")), lugar(f.get("cidade"))
        mesmo_lugar = (lo and (lo == fo or lo in fo or fo in lo) and len(min(lo, fo, key=len)) > 4) or (lc and lc == fc)
        if not mesmo_lugar:
            continue
        sim = parecido(objeto, f.get("objeto") or "")
        outro = numero(f.get("numero"))
        if num and outro and outro != num:
            continue   # números diferentes no mesmo órgão: são licitações diferentes (lotes, editais separados)
        if num and numero(f.get("numero")) == num and sim >= 0.15:
            return i
        if sim >= 0.5:
            return i
        if dia and (f.get("dataSessao") or "")[:10] == dia and sim >= 0.25:
            return i
    return None
