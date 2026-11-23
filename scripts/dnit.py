"""Editais do DNIT em Minas Gerais, lidos direto da consulta oficial do DNIT
(https://www.gov.br/dnit/pt-br/assuntos/licitacoes/superintendencias/editais-de-licitacoes, que carrega
https://www1.dnit.gov.br/editais/consulta/lista.asp). Toda obra/serviço rodoviário da Superintendência de MG
entra no controle com prioridade alta. O que já veio pelo PNCP não é duplicado: só recebe o link do DNIT.

Uso: python dnit.py          (grava)
     python dnit.py --teste  (só mostra)
"""
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone

import horario_disputa as h
import triagem_documentos as t
from entendimento import entender

LISTA = "https://www1.dnit.gov.br/editais/consulta/lista.asp"
RESUMO = "https://www1.dnit.gov.br/editais/consulta/resumoEdital.asp?NUMIDEdital="

RX_RODOVIARIO = re.compile(r"rodovi|\bbr\s*-?\s*\d{3}|estradas?|pavimen|asfalt|conserva\w* rodovi|manutencao rodovi|restaura|"
                           r"recupera|sinaliza|drenagem|\bpontes?\b|viadut|obras?\b|duplica|implanta|acostamento|contorno|"
                           r"travessia|faixa de dominio|rocada|recomposi|eliminacao de pontos criticos|obras? de artes?")
RX_FORA = re.compile(r"limpeza e conserva|limpeza, conserva|\bseguro\b|vigilancia|veiculos?|frota|ar condicionado|"
                     r"manutencao predial|predio|edificio|sede|copeiragem|recepcao|telefon|informatica|software|"
                     r"\b(consultoria|gerenciamento|supervisao|fiscalizacao)\b|elaboracao d[oe]s? (estudos|projetos?|anteprojeto)|"
                     r"\bestudos\b|projetos? basico|projeto executivo|levantamento|topograf|aquisicao|locacao|"
                     r"balanca|pesagem|radar|controle de velocidade|apoio tecnico|desapropria|ambiental")


def baixar(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("latin-1")


def resumo(idn):
    """Valor global, data/hora da sessão e local (plataforma) do resumo do edital."""
    txt = html.unescape(re.sub(r"<[^>]+>", " ", baixar(RESUMO + idn)))
    txt = " ".join(txt.replace("​", "").split())
    valor = re.search(r"Valor Global \(R\$\)\s*([\d.]+,\d{2})", txt)
    dh = re.search(r"Data/Hora\s*(\d{2})/(\d{2})/(\d{4})\D{0,8}?(\d{1,2}):(\d{2})", txt)
    local = re.search(r"Local / Data Local\s*(\S+)", txt)
    sape = re.search(r"Edital SAPE\s*(\S+)", txt)
    proc = re.search(r"Processo\s*([\d./-]+)", txt)
    return {
        "valor": float(valor.group(1).replace(".", "").replace(",", ".")) if valor else None,
        "data": f"{dh.group(3)}-{dh.group(2)}-{dh.group(1)}T{int(dh.group(4)):02d}:{dh.group(5)}:00" if dh else "",
        "local": local.group(1) if local else "", "sape": sape.group(1) if sape else "", "processo": proc.group(1) if proc else "",
    }


def main():
    lista = json.loads(baixar(LISTA), strict=False)["aaData"]
    hoje = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")
    mg = []
    for e in lista:
        if "MINAS" not in (e.get("regional") or "").upper() or e.get("status") not in ("EDITAL ATIVO", "EDITAL SUSPENSO"):
            continue
        d, m, a = (e.get("data_abertura") or "00/00/0000").split("/")
        if f"{a}-{m}-{d}" < hoje:
            continue
        n = h.norm(e.get("objeto") or "")
        if RX_RODOVIARIO.search(n) and not RX_FORA.search(n):
            mg.append(e)
    print(f"{len(lista)} editais no DNIT; {len(mg)} obras/serviços rodoviários abertos em MG")

    existentes = [dict(f, id=i) for i, f in h.licitacoes()]
    novas = 0
    for e in mg:
        seq, ano = re.match(r"\d+-0*(\d+)/(\d{4})", e["numero"]).groups()
        idn = str(e["detalhes"])
        link = RESUMO + idn
        objeto = " ".join((e.get("objeto") or "").split())
        servicos = [nome for nome, rx, _ in t.SERVICOS_LM if rx.search(h.norm(objeto))]
        motivo = "Órgão prioritário (DNIT)" + (": " + ", ".join(servicos) if servicos else ": obra/serviço rodoviário")
        triagem = {"motivo": motivo, "prioridade": "alta", "fonte": "DNIT", "linkDnit": link}
        valor_lista = None
        # já está no controle (veio pelo PNCP ou de uma rodada anterior)?
        ja = None
        for l in existentes:
            org = h.norm(l.get("orgao") or "")
            num = (l.get("numero") or "").split("—")[0].strip()
            if l.get("id") == f"dnit_{idn}" or (("dnit" in org or "infraest" in org) and re.fullmatch(rf"0*{seq}/{ano}", num)):
                ja = l
                break
        situacao = "Suspenso (DNIT)" if e["status"] == "EDITAL SUSPENSO" else ""
        if ja:
            print(f"já no controle: {e['numero']} ({ja['id']})")
            if "--teste" not in sys.argv:
                upd = {"triagem": triagem}
                if situacao:
                    upd["suspensa"] = True
                corpo = json.dumps({"fields": {k: t.campo(v) for k, v in upd.items()}}).encode()
                mask = "&".join(f"updateMask.fieldPaths={k}" for k in upd)
                h.http(f"{h.DOCS}/licitacoes/{ja['id']}?key={h.CHAVE}&{mask}", "PATCH", corpo)
            continue
        r = resumo(idn)
        agora = datetime.now(timezone.utc).isoformat()
        numero = f"{e['modalidade']} {int(seq)}/{ano}" + (f" — Edital SAPE {r['sape']}" if r["sape"] else "") + \
                 (f" — Proc. {r['processo']}" if r["processo"] else "")
        reg = {
            "origem": "DNIT", "dataSessao": r["data"] or f"{e['data_abertura'][6:]}-{e['data_abertura'][3:5]}-{e['data_abertura'][:2]}T00:00:00",
            "orgao": "DNIT — Superintendência Regional em Minas Gerais", "cidade": "Belo Horizonte (sede do órgão)",
            "numero": numero, "modalidade": e["modalidade"], "objeto": objeto, "valor": r["valor"],
            "linkPortal": link, "interesse": None, "status": "", "servicos": [], "atestados": "", "observacao": "",
            "garantiaProposta": "", "vencedora": "", "camposEditados": [], "lote": agora, "criadoEm": agora, "atualizadoEm": agora,
            "triagem": dict(triagem, plataforma=r["local"], obra=entender(objeto, r["valor"])["resumo"]), "suspensa": bool(situacao),
        }
        print(f"INCLUÍDA: DNIT {e['numero']} | {r['data']} | R$ {r['valor']} | {objeto[:80]}")
        t.gravar("licitacoes", f"dnit_{idn}", reg)
        novas += 1
    print(f"{novas} novas do DNIT")


if __name__ == "__main__":
    main()
