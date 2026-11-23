"""Preenche no controle, a partir do edital e do termo de referência (PNCP), os campos que a equipe usa:
  - Atestados: parcelas de maior relevância / quantitativos exigidos no atestado de capacidade técnica;
  - Garantia de proposta: percentual exigido e o VALOR (percentual x valor estimado), ou "não exigida".
Também guarda impugnação, modo de disputa e usina em dadosEdital. Não sobrescreve o que a equipe editou à mão.

Uso: python preencher_edital.py            (licitações abertas ainda sem esses dados)
     python preencher_edital.py --todas    (refaz todas as abertas)
     python preencher_edital.py --teste    (só mostra)
"""
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import edital_dados as ed
import horario_disputa as h
import triagem_documentos as t

VERSAO = 2
logging.getLogger("pypdf").setLevel(logging.ERROR)


def dinheiro(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def textos_do_processo(link):
    """Edital, termo de referência e projeto básico primeiro; planilhas por último (não têm esses dados)."""
    m = re.search(r"editais/(\d+)/(\d+)/(\d+)", link or "")
    if not m:
        return "", 0
    arquivos = json.loads(h.http(f"https://pncp.gov.br/pncp-api/v1/orgaos/{m[1]}/compras/{m[2]}/{m[3]}/arquivos"))

    def ordem(a):
        n = h.norm(unquote(a.get("titulo") or "") + " " + (a.get("tipoDocumentoNome") or ""))
        return 0 if "edital" in n else 1 if re.search(r"termo de referencia|\btr\b|projeto basico|memorial", n) else \
            3 if re.search(r"planilha|orcamento|cronograma|bdi|composic|\.xls", n) else 2
    partes, lidos = [], 0
    for a in sorted(arquivos, key=ordem)[:6]:
        if ordem(a) == 3:
            continue
        try:
            tx = t.texto_de(unquote(a.get("titulo") or ""), h.http(a["url"]))
        except Exception as e:
            print(f"   não li {unquote(a.get('titulo') or '')[:60]}: {e}")
            continue
        if len(tx.strip()) > 200:
            partes.append(tx)
            lidos += 1
        time.sleep(0.5)
    return "\n".join(partes), lidos


def main():
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%dT%H:%M")
    feitos = 0
    for doc_id, l in h.licitacoes():
        link = (l.get("pncp") or {}).get("linkPncp")
        if not link or l.get("duplicadaDe") or (l.get("dataSessao") or "9")[:16] < agora:
            continue
        de = l.get("dadosEdital") or {}
        if de.get("versao") == VERSAO and "--todas" not in sys.argv:
            continue
        try:
            texto, lidos = textos_do_processo(link)
        except Exception as e:
            print(f"falha {doc_id}: {e}")
            continue
        x = ed.extrair(texto) if lidos else None
        editados = l.get("camposEditados") or []
        dados = {}
        if x:
            pct = x.get("garantiaPct")
            valor = l.get("valor")
            if x["garantia"] == "não exigida":
                gar = "Não exigida no edital"
            elif pct and valor:
                gar = f"{str(pct).replace('.', ',')}% do valor estimado = {dinheiro(valor * pct / 100)}"
            elif x["garantia"] != ed.NI:
                gar = x["garantia"]
            else:
                gar = "Não informada no edital"
            if "garantiaProposta" not in editados and not (l.get("garantiaProposta") or "").strip() or \
                    (l.get("garantiaProposta") or "").startswith(("Não informada", "Não exigida")) or "% do valor" in (l.get("garantiaProposta") or ""):
                if "garantiaProposta" not in editados:
                    dados["garantiaProposta"] = gar
            if "atestados" not in editados and (not (l.get("atestados") or "").strip() or (l.get("atestados") or "").startswith("Edital:")):
                dados["atestados"] = "Edital: " + (x["atestado"] if x["atestado"] != ed.NI else "quantitativos não informados no edital/TR")
            x["versao"] = VERSAO
            x["lidos"] = lidos
            dados["dadosEdital"] = x
        else:
            dados["dadosEdital"] = {"versao": VERSAO, "lidos": 0, "conferir": True}
        print(f"{(l.get('cidade') or '')[:28]:28} | {dados.get('garantiaProposta', '-')[:55]:55} | {dados.get('atestados', '-')[:90]}")
        if "--teste" not in sys.argv:
            h.gravar(doc_id, dados)
        feitos += 1
    print(f"{feitos} licitações preenchidas")


if __name__ == "__main__":
    main()
