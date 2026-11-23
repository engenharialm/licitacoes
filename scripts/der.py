"""Concorrências do DER-MG lidas do site oficial (https://www.der.mg.gov.br/transparencia/licitacoes/concorrencias-AAAA).
Obras/serviços rodoviários com sessão a partir de hoje entram no controle com prioridade alta.
A lista lida também fica em fontes/der, que o botão "Atualizar DER" do site usa (o site do DER não deixa o
navegador ler direto). O que já está no controle (pelo PNCP ou rodada anterior) não é duplicado.

Uso: python der.py          (grava)
     python der.py --teste  (só mostra)
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import horario_disputa as h
import triagem_documentos as t
from entendimento import entender
from dnit import RX_FORA, RX_RODOVIARIO

BASE = "https://www.der.mg.gov.br"


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


def texto(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def lista(ano):
    s = baixar(f"{BASE}/transparencia/licitacoes/concorrencias-{ano}")
    itens = []
    for m in re.finditer(r'<a [^>]*href="(/transparencia/licitacoes/concorrencias-\d{4}/[^"]*?(\d+)-edital-[^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a [^>]*href="/transparencia/licitacoes/concorrencias-\d{4}/[^"]*-edital-|</table>|$)',
                         s, re.S):
        link, nid, rotulo, resto = m.groups()
        rot = texto(rotulo)
        num = re.search(r"(\d{7})\s*0*(\d+)/(\d{4})", rot + " " + texto(resto)[:60])
        itens.append({"id": nid, "link": BASE + link, "rotulo": rot, "num": num.groups() if num else None,
                      "resumo": texto(resto)[:1200]})
    return itens


def detalhe(link):
    tx = texto(baixar(link))
    tx = tx[tx.find("Modalidade:"):] if "Modalidade:" in tx else tx
    g = lambda rx: (re.search(rx, tx) or [None, ""])[1]
    dh = re.search(r"Data Abertura:\s*(\d{2})/(\d{2})/(\d{4})(?:\D{0,6}(\d{1,2})[:h](\d{2}))?", tx)
    valor = g(r"Valor Orçado:\s*R\$\s*([\d.]+,\d{2})")
    return {
        "modalidade": g(r"Modalidade:\s*(.+?)\s+Objeto:"), "objeto": g(r"Objeto:\s*(.+?)\s+(?:Valor Orçado|Data Abertura|Fone):"),
        "valor": float(valor.replace(".", "").replace(",", ".")) if valor else None,
        "data": (f"{dh.group(3)}-{dh.group(2)}-{dh.group(1)}T{int(dh.group(4) or 0):02d}:{dh.group(5) or '00'}:00") if dh else "",
        "suspensa": bool(re.search(r"suspens", tx[:3000], re.I)),
    }


def interessa(objeto):
    n = h.norm(objeto)
    return bool(RX_RODOVIARIO.search(n)) and not RX_FORA.search(n)


def main():
    agora_br = datetime.now(timezone(timedelta(hours=-3)))
    hoje = agora_br.strftime("%Y-%m-%d")
    itens = lista(agora_br.year)
    if agora_br.month == 1:
        itens += lista(agora_br.year - 1)
    print(f"{len(itens)} concorrências na página do DER-MG")
    existentes = [dict(f, id=i) for i, f in h.licitacoes()]
    abertas, novas = [], 0
    for it in itens[:60]:   # as mais recentes ficam no topo
        try:
            d = detalhe(it["link"])
        except Exception as e:
            print(f"não li {it['link']}: {e}")
            continue
        if not d["data"] or d["data"][:10] < hoje:
            continue
        objeto = d["objeto"] or it["resumo"]
        seq, ano = (it["num"][1], it["num"][2]) if it["num"] else ("", "")
        numero = f"{d['modalidade'] or 'Concorrência'} {it['num'][0]} {int(seq):06d}/{ano}" if it["num"] else it["rotulo"]
        reg_fonte = {"id": it["id"], "link": it["link"], "numero": numero, "objeto": objeto, "valor": d["valor"],
                     "data": d["data"], "modalidade": d["modalidade"], "interessa": interessa(objeto), "suspensa": d["suspensa"]}
        abertas.append(reg_fonte)
        if not reg_fonte["interessa"]:
            print(f"fora do perfil: {numero} — {objeto[:80]}")
            continue
        nomes = [nome for nome, rx, _ in t.SERVICOS_LM if rx.search(h.norm(objeto))]
        triagem = {"motivo": "Órgão prioritário (DER-MG)" + (": " + ", ".join(nomes) if nomes else ": obra/serviço rodoviário"),
                   "prioridade": "alta", "fonte": "DER-MG", "linkDer": it["link"]}
        ja = None
        for l in existentes:
            org = h.norm(l.get("orgao") or "")
            if l["id"] == f"der_{it['id']}" or (seq and ("estradas de rodagem" in org or "der" in org.split() or "deer" in org)
                                                 and re.search(rf"\b0*{int(seq)}/{ano}\b", l.get("numero") or "")):
                ja = l
                break
        if ja:
            print(f"já no controle: {numero} ({ja['id']})")
            if "--teste" not in sys.argv:
                upd = {"triagem": dict(ja.get("triagem") or {}, **triagem, obra=entender(objeto, d["valor"])["resumo"])}
                corpo = json.dumps({"fields": {k: t.campo(v) for k, v in upd.items()}}).encode()
                h.http(f"{h.DOCS}/licitacoes/{ja['id']}?key={h.CHAVE}&updateMask.fieldPaths=triagem", "PATCH", corpo)
            continue
        agora = datetime.now(timezone.utc).isoformat()
        reg = {
            "origem": "DER", "dataSessao": d["data"], "orgao": "DER-MG — Departamento de Estradas de Rodagem de Minas Gerais",
            "cidade": "Belo Horizonte (sede do órgão)", "numero": numero, "modalidade": d["modalidade"], "objeto": objeto,
            "valor": d["valor"], "linkPortal": it["link"], "interesse": None, "status": "", "servicos": [], "atestados": "",
            "observacao": "", "garantiaProposta": "", "vencedora": "", "camposEditados": [], "lote": agora, "criadoEm": agora,
            "atualizadoEm": agora, "triagem": dict(triagem, obra=entender(objeto, d["valor"])["resumo"]), "suspensa": d["suspensa"],
        }
        print(f"INCLUÍDA: {numero} | {d['data']} | R$ {d['valor']} | {objeto[:80]}")
        t.gravar("licitacoes", f"der_{it['id']}", reg)
        novas += 1
    t.gravar("fontes", "der", {"em": datetime.now(timezone.utc).isoformat(), "abertas": abertas})
    print(f"{len(abertas)} abertas no DER-MG; {novas} novas incluídas")


if __name__ == "__main__":
    main()
