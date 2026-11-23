"""Mesma busca do botão "Atualizar do PNCP", feita pelo robô 3 vezes ao dia: licitações abertas em MG cujo objeto
já mostra pavimentação/obra viária (ou de DNIT/DER-MG) entram no controle. Não mexe nas que já existem.

Uso: python pncp_robo.py          (grava)
     python pncp_robo.py --teste  (só mostra)
"""
import re
from datetime import datetime, timedelta, timezone

import horario_disputa as h
import triagem_documentos as t
from dnit import RX_FORA, RX_RODOVIARIO
from entendimento import entender

RX_CALC = re.compile(r"calcamento|bloquete|intertravad|sextavad|paralelep|polied|\bpedra\b|blocos? de concreto")
RX_ASF = re.compile(r"asfalt|cbuq|betuminoso|recapeamento|microrrevestimento|tratamento superficial|\btsd\b|\bpmf\b|tapa\s*-?\s*buracos?|fresagem")
RX_ORGAO = re.compile(r"departamento nacional de infra|\bdnit\b|estradas de rodagem|\bder\s*-?\s*mg\b|\bdeer\b")


def classificar(objeto, orgao):
    n = h.norm(objeto)
    if t.excluido(n):
        return None
    if t.eh_aquisicao_material(n):
        # fornecimento de massa asfáltica / material de pavimento: interessa (usina), prioridade normal
        if re.search(r"cbuq|massa asfaltica|concreto (betuminoso|asfaltico)|pmf|pre-?\s?misturado|emulsao|cap|cimento asfaltico|asfalt", n):
            return "Fornecimento de material asfáltico (CBUQ / PMF / emulsão / CAP)", "normal"
        return None
    if RX_ORGAO.search(h.norm(orgao)) and RX_RODOVIARIO.search(n) and not RX_FORA.search(n):
        nomes = [s[0] for s in t.SERVICOS_LM if s[1].search(n)]
        sigla = "DNIT" if re.search(r"infra|dnit", h.norm(orgao)) else "DER-MG"
        return f"Órgão prioritário ({sigla})" + (": " + ", ".join(nomes) if nomes else ": obra/serviço rodoviário"), "alta"
    if not t.objeto_aceito_pelo_site(n) or (RX_CALC.search(n) and not RX_ASF.search(n)):
        return None
    servicos = [s for s in t.SERVICOS_LM if s[1].search(n) and (s[2] or not t.RX_PREDIO.search(n))]
    nomes = [s[0] for s in servicos] or ["Pavimentação / obra viária"]
    alta = any(s[2] for s in servicos) or t.RX_PAV.search(n)
    return "Objeto: " + ", ".join(nomes), "alta" if alta else "normal"


def main():
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%dT%H:%M")
    itens = [it for it in t.abertas_mg() if (it.get("dataEncerramentoProposta") or "9")[:16] >= agora]
    existentes = {i: f for i, f in h.licitacoes()}
    ids = set(existentes)
    grupos = {}
    for it in itens:
        org = (it.get("orgaoEntidade") or {}).get("razaoSocial", "") + " " + (it.get("unidadeOrgao") or {}).get("nomeUnidade", "")
        c = classificar(it.get("objetoCompra") or "", org)
        if not c:
            continue
        chave = it["orgaoEntidade"]["cnpj"] + "|" + re.sub(r"[^a-z0-9]", "", h.norm(re.sub(r"^\s*\[[^\]]*\]", "", it.get("objetoCompra") or "")))
        grupos.setdefault(chave, []).append((it, c))
    novas = 0
    for g in grupos.values():
        if any(t.doc_id(it) in ids for it, _ in g):
            continue   # já está no controle (alguma das publicações)
        it, (motivo, prio) = max(g, key=lambda x: x[0].get("dataPublicacaoPncp") or "")
        quem = f"{it['orgaoEntidade'].get('razaoSocial')} — {it.get('numeroCompra')}/{it.get('anoCompra')}"
        # mesma licitação já lançada pelo site do DNIT/DER (outro id): mesmo órgão e mesmo número/ano
        org = h.norm(it["orgaoEntidade"].get("razaoSocial") or "")
        sigla = "dnit" if re.search(r"infra|dnit", org) else ("der" if "estradas de rodagem" in org else "")
        mnum = re.search(r"(\d+)\D*$", re.sub(r"/\d{4}\s*$", "", str(it.get("numeroCompra") or "0")))
        num = int(mnum.group(1)) if mnum else 0
        pal = set(w for w in re.split(r"[^a-z0-9]+", h.norm(it.get("objetoCompra") or "")) if len(w) > 3)
        def parecido(f):
            q = set(w for w in re.split(r"[^a-z0-9]+", h.norm(f.get("objeto") or "")) if len(w) > 3)
            return pal and q and len(pal & q) / len(pal | q) >= 0.4
        if sigla and any(i.startswith(sigla + "_") and parecido(f) for i, f in existentes.items()):
            print(f"já no controle pelo site do {sigla.upper()}: {quem}")
            continue
        if sigla and any(i.startswith(sigla + "_") and re.search(rf"0*{num}/{it.get('anoCompra')}", f.get("numero") or "")
                         for i, f in existentes.items()):
            print(f"já no controle pelo site do {sigla.upper()}: {quem}")
            continue
        # entendimento prévio: que obra é; se o objeto não deixa claro, os documentos decidem
        valor = it.get("valorTotalEstimado") or None
        e = entender(it.get("objetoCompra") or "", valor)
        anexos = "ok"
        if e["perfil"] == "conferir" and not motivo.startswith("Órgão prioritário"):
            texto, n_anexos, n_lidos = t.ler_anexos(it)
            if n_lidos:
                e = entender(it.get("objetoCompra") or "", valor, texto)
            else:
                anexos = "inacessiveis"
        if e["perfil"] == "nao" and not motivo.startswith("Órgão prioritário"):
            print(f"fora do perfil ({e['porque'] or e['tipo']}): {quem}")
            continue
        triagem = {"motivo": motivo + (f" — {e['porque']}" if e["porque"] else ""), "prioridade": prio, "fonte": "PNCP (robô)",
                   "obra": e["resumo"], "anexos": anexos}
        print(f"INCLUÍDA: {quem} | Obra: {e['resumo']} | {triagem['motivo']}")
        t.gravar("licitacoes", t.doc_id(it), t.registro_pncp(it, motivo, prio, triagem))
        novas += 1
    print(f"{len(itens)} abertas em MG no PNCP; {novas} novas incluídas")


if __name__ == "__main__":
    main()
