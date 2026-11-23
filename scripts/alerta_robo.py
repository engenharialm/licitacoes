"""Mesma busca do botão "Atualizar do Alerta", feita pelo robô. A chave da API vem do segredo ALERTA_TOKEN do
GitHub (Settings → Secrets and variables → Actions); sem ele, o passo é pulado. Não duplica o que já veio do PNCP
(mesmo número PNCP, ou mesma cidade com sessão no mesmo dia).
"""
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import horario_disputa as h
import triagem_documentos as t
from pncp_robo import classificar

PALAVRAS = ("pavimentação,pavimentacao,asfalto,asfáltica,asfaltica,CBUQ,concreto betuminoso,recapeamento,tapa-buraco,"
            "tapa buraco,microrrevestimento,micro revestimento,fresagem")


def cidade(s):
    return re.sub(r"[^a-z]", "", re.sub(r"\(.*?\)", "", h.norm(s)))


def main():
    token = os.environ.get("ALERTA_TOKEN", "").strip()
    if not token:
        print("ALERTA_TOKEN não configurado no GitHub: Alerta Licitação pulado.")
        return
    hoje = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")
    coletadas, pag, paginas = {}, 1, 1
    while pag <= paginas:
        q = urllib.parse.urlencode({"uf": "MG", "palavra_chave": PALAVRAS, "pagina": pag, "licitacoesPorPagina": 100, "token": token})
        j = json.loads(h.http("https://alertalicitacao.com.br/api/v1/licitacoesAbertas/?" + q))
        if int(j.get("totalErros") or 0):
            print("Erro do Alerta:", [e.get("codigo") for e in j.get("erros", [])])
            return
        paginas = int(j.get("paginas") or 1)
        for it in j.get("licitacoes") or []:
            if it.get("id_licitacao"):
                coletadas[it["id_licitacao"]] = it
        pag += 1
        time.sleep(1.2)
    existentes = {i: f for i, f in h.licitacoes()}
    outras = {(cidade(f.get("cidade")), (f.get("dataSessao") or "")[:10]) for f in existentes.values() if f.get("origem") != "ALERTA"}
    novas = 0
    for it in coletadas.values():
        c = classificar(it.get("objeto") or "", it.get("orgao") or "")
        if not c:
            continue
        abertura = (it.get("abertura_datetime") or "").replace(" ", "T")
        if abertura and abertura[:10] < hoje:
            continue
        id_ = "alerta_" + re.sub(r"[^\w-]", "_", str(it["id_licitacao"]))
        n = re.search(r"PNCP-(\d{14})-\d-0*(\d+)-(\d{4})", str(it["id_licitacao"]))
        if id_ in existentes or (n and f"pncp_{n[1]}-1-{int(n[2]):06d}_{n[3]}" in existentes) \
                or (abertura and (cidade(it.get("municipio")), abertura[:10]) in outras):
            continue
        motivo, prio = c
        agora = datetime.now(timezone.utc).isoformat()
        alerta = {"id": str(it["id_licitacao"]), "titulo": it.get("titulo") or "", "municipio": it.get("municipio") or "",
                  "uf": it.get("uf") or "", "orgao": it.get("orgao") or "", "objeto": (it.get("objeto") or "").strip(),
                  "abertura": abertura, "link": it.get("link") or "", "linkExterno": it.get("linkExterno") or "",
                  "modalidade": it.get("tipo") or "", "pav": True, "ter": False, "dre": False, "asfalto": False,
                  "motivo": motivo, "prioridade": prio}
        t.gravar("licitacoes", id_, {
            "origem": "ALERTA", "dataSessao": abertura, "orgao": alerta["orgao"], "cidade": alerta["municipio"],
            "numero": alerta["titulo"], "modalidade": alerta["modalidade"], "objeto": alerta["objeto"],
            "linkPortal": alerta["linkExterno"], "valor": None, "alerta": alerta, "naListaAlerta": True, "interesse": None,
            "status": "", "servicos": [], "atestados": "", "observacao": "", "garantiaProposta": "", "vencedora": "",
            "camposEditados": [], "lote": agora, "criadoEm": agora, "atualizadoEm": agora,
            "triagem": {"motivo": motivo, "prioridade": prio, "fonte": "Alerta (robô)"}})
        print(f"INCLUÍDA: {alerta['municipio']} — {alerta['titulo']} | {motivo}")
        novas += 1
    print(f"{len(coletadas)} lidas no Alerta; {novas} novas incluídas")


if __name__ == "__main__":
    main()
