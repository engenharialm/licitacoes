"""Triagem pelos documentos: acha licitações de obra viária que o objeto não denuncia.

O site só lê o objeto do PNCP. Muitas obras da atividade da LM vêm com objetos como "reforma das vias
rurais" ou "melhoria de estradas", e só o edital, o termo de referência ou a planilha mostram que há
regularização de subleito, base/sub-base, BGS, imprimação, CBUQ etc. Este robô:

  1. lê as licitações abertas em MG no PNCP (mesma consulta do botão "Atualizar do PNCP");
  2. separa as de obra viária cujo objeto não bastou para o filtro do site;
  3. baixa os anexos (PDF, planilha .xlsx e .zip com esses arquivos dentro) e procura os serviços da LM;
  4. inclui no controle as que têm algum desses serviços, com o motivo; quando os anexos não podem ser lidos,
     inclui marcando "anexos não lidos — conferir" (não descarta por falta de informação).

Cada licitação é analisada uma vez por data de encerramento (cache em triagem_pncp). Roda no GitHub Actions
junto com o horário da disputa (.github/workflows/horario-disputa.yml).
"""
import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from pypdf import PdfReader

import horario_disputa as h

try:
    import openpyxl
except ImportError:   # planilha .xlsx fica sem leitura, o resto funciona
    openpyxl = None

MODALIDADES = {4: "Concorrência Eletrônica", 5: "Concorrência Presencial", 6: "Pregão Eletrônico", 8: "Dispensa"}
ESFERAS = {"M": "Municipal", "E": "Estadual", "F": "Federal", "D": "Distrital", "N": "Consórcio / outros"}

# --- mesmos serviços do site (SERVICOS_LM em index.html) ---
SERVICOS_LM = [
    ("Pavimentação asfáltica", r"pavimentacao asfaltica|asfalt", True),
    ("CBUQ / concreto asfáltico", r"\bcbuq\b|\bcauq\b|concreto (betuminoso|asfaltico)", True),
    ("Recapeamento", r"recapeamento", True),
    ("Restauração / recuperação / reforço de pavimento", r"(restaura|recupera|reforc|melhoria estrutural)\w* (estrutural )?(d[aeo]s? |de )?pavimen", True),
    ("Regularização e compactação de subleito", r"sub-?\s?leito", True),
    ("Base / sub-base", r"sub-?\s?base|base granular|base estabilizada|base (de|em) (brita|solo)|base e sub", True),
    ("BGS / brita graduada", r"brita graduada|\bbgs\b|\bbgtc\b", True),
    ("Solo-brita / solo-cimento / estabilização granulométrica", r"solo\s*-?\s*(brita|cimento)|estabiliza\w* granulometric", True),
    ("Imprimação / pintura de ligação", r"imprimacao|pintura de ligacao", True),
    ("PMF / tratamento superficial / microrrevestimento", r"\bpmf\b|pre-?\s?misturado|tratamento superficial|\btsd\b|\btss\b|micro\s*-?\s*revestimento|microrrevestimento", True),
    ("Tapa-buracos", r"tapa\s*-?\s*buracos?", True),
    ("Fresagem", r"fresagem", True),
    ("Pavimentação", r"pavimenta", False),
    ("Conservação / manutenção / melhoria de vias e estradas",
     r"(conserva|manuten|recupera|melhoria|reforma|readequa|restaura)\w* (d[aeo]s? |de |em |nas? )?(malha viaria|vias?|estradas?|rodovias?|ruas?|vicinais?|logradouros?|pistas? de rolamento)\b", False),
]
SERVICOS_LM = [(n, re.compile(rx), alta) for n, rx, alta in SERVICOS_LM]
RX_PAV = re.compile(r"pavimenta|asfalt|cbuq|recapeamento|micro\s*-?\s*revestimento|microrrevestimento|tratamento superficial|\btsd\b|\btss\b|tapa\s*-?\s*buracos?|fresagem")
RX_VIARIO = re.compile(r"infraestrutura viaria|infraestrutura urbana|infraestrutura rural|melhorias? (de|da|na) infraestrutura|obras? viarias?|sistema viario|alargamento d[aeo]s? (rua|avenida|via)")
RX_PREDIO = re.compile(r"escola|creche|predios?\b|edificac|edificio|\bubs\b|unidade basica|hospital|ginasio|credenciamento|madeira")
RX_EXCLUIR = re.compile(r"banheiros? quimicos|\bcaminh(ao|oes)\b|\bveiculos?\b|vassour|ferramentas|placa vibratoria|formas? para bloquete|\bpneus?\b|uniformes?\b")
RX_TEC = re.compile(r"\b(consultoria|gerenciamento|supervisao|fiscalizacao)\b|elaboracao de (estudos|projetos?)")
# obra em via: só estas vão para a leitura dos anexos (fundação/terraplenagem sem via não entram)
RX_OBRA_VIA = re.compile(r"\b(estradas?|vias?|ruas?|rodovias?|avenidas?|vicinais?|logradouros?|trechos?|bairros?|loteamentos?|malha viaria)\b|pavimen|infraestrutura")
RX_OBRA = re.compile(r"\bobras?\b|execu|constru|reforma|recupera|melhori|manuten|conserva|readequa|restaura|implanta|urbaniza|servicos? de engenharia")
# nos documentos, só serviços que caracterizam pavimento viário (o genérico "pavimentação" não basta)
SERVICOS_DOC = [s for s in SERVICOS_LM if s[2]]


def objeto_aceito_pelo_site(n):
    """Aproximação do classificar() do site: se o objeto já basta, o botão Atualizar do PNCP inclui."""
    servicos = [s for s in SERVICOS_LM if s[1].search(n) and (s[2] or not RX_PREDIO.search(n))]
    pav = RX_PAV.search(n) or (RX_VIARIO.search(n) and not RX_PREDIO.search(n)) or servicos
    return bool(pav) and not RX_EXCLUIR.search(n) and not (RX_TEC.search(n) and "integrada" not in n)


def eh_aquisicao_material(n):
    ini = re.sub(r"destinad[oa]s? (a|para) (a )?(execucao|aplicacao)|para (a )?aplicacao", " ", n[:160])
    return bool(re.search(r"\b(aquisicao|compra|fornecimento)\b", ini)) and not re.search(r"execucao|executar|prestacao de servico|e aplicacao|aplicacao de", ini)


def candidata(objeto):
    n = h.norm(objeto)
    if objeto_aceito_pelo_site(n) or eh_aquisicao_material(n) or RX_EXCLUIR.search(n):
        return False
    if RX_TEC.search(n) and "integrada" not in n:
        return False
    return bool(RX_OBRA_VIA.search(n) and RX_OBRA.search(n))


def abertas_mg():
    data_final = (datetime.now() + timedelta(days=400)).strftime("%Y%m%d")
    vistos = {}
    for mod in MODALIDADES:
        pag, total = 1, 1
        while pag <= total:
            url = (f"https://pncp.gov.br/api/consulta/v1/contratacoes/proposta?dataFinal={data_final}&uf=MG"
                   f"&codigoModalidadeContratacao={mod}&tamanhoPagina=50&pagina={pag}")
            try:
                bruto = h.http(url, tentativas=4)
                j = json.loads(bruto) if bruto else {"data": [], "totalPaginas": 0}
            except Exception as e:
                print(f"falha {MODALIDADES[mod]} p.{pag}: {e}")
                pag += 1
                continue
            total = j.get("totalPaginas") or 0
            for it in j.get("data") or []:
                if it.get("numeroControlePNCP"):
                    vistos.setdefault(it["numeroControlePNCP"], it)
            pag += 1
            time.sleep(1.2)
    return list(vistos.values())


def doc_id(it):
    return "pncp_" + re.sub(r"[^\w-]", "_", it["numeroControlePNCP"])


def existe(colecao, id_):
    try:
        return json.loads(h.http(f"{h.DOCS}/{colecao}/{id_}?key={h.CHAVE}", tentativas=1))
    except Exception:
        return None


def texto_de(nome, dados):
    """Texto de um anexo: PDF (até 80 páginas), planilha .xlsx e .zip com esses arquivos dentro."""
    nome = nome.lower()
    if dados[:4] == b"%PDF" or nome.endswith(".pdf"):
        leitor = PdfReader(io.BytesIO(dados))
        return "\n".join((p.extract_text() or "") for p in leitor.pages[:80])
    if dados[:2] == b"PK" and (nome.endswith(".xlsx") or b"xl/workbook" in dados[:4000]) and openpyxl:
        wb = openpyxl.load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
        linhas = []
        for ws in wb.worksheets[:8]:
            for i, r in enumerate(ws.iter_rows(values_only=True)):
                if i > 3000:
                    break
                linhas.append(" ".join(str(x) for x in r if x is not None))
        return "\n".join(linhas)
    if dados[:2] == b"PK":
        partes = []
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            for info in z.infolist()[:40]:
                if info.file_size > 40_000_000 or not re.search(r"\.(pdf|xlsx)$", info.filename, re.I):
                    continue
                try:
                    partes.append(texto_de(info.filename, z.read(info)))
                except Exception:
                    continue
        return "\n".join(partes)
    return ""


def ler_anexos(it):
    """(texto de todos os anexos lidos, quantos anexos havia, quantos foram lidos)."""
    cnpj, ano, seq = it["orgaoEntidade"]["cnpj"], it["anoCompra"], it["sequencialCompra"]
    base = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
    try:
        arquivos = json.loads(h.http(base))
    except Exception:
        return "", 0, 0
    textos, lidos = [], 0
    for a in arquivos[:12]:
        titulo = unquote(a.get("titulo") or "")
        try:
            t = texto_de(titulo, h.http(a["url"]))
        except Exception as e:
            print(f"   anexo não lido ({titulo}): {e}")
            continue
        if len(t.strip()) > 200:   # PDF digitalizado (imagem) não traz texto
            lidos += 1
            textos.append(t)
        time.sleep(0.5)
    return "\n".join(textos), len(arquivos), lidos


def registro_pncp(it, motivo, prioridade, triagem):
    """Mesmo formato do que o botão "Atualizar do PNCP" grava, mais o campo triagem."""
    esfera_id = (it.get("orgaoEntidade") or {}).get("esferaId") or ""
    municipio = (it.get("unidadeOrgao") or {}).get("municipioNome") or ""
    cidade = municipio if esfera_id in ("M", "") else f"{municipio} (sede do órgão)"
    numero = f"{it.get('numeroCompra') or ''}/{it.get('anoCompra') or ''}" + (f" — Proc. {it['processo']}" if it.get("processo") else "")
    objeto = " ".join((it.get("objetoCompra") or "").split())
    valor = float(it["valorTotalEstimado"]) if (it.get("valorTotalEstimado") or 0) > 0 else None
    prefixo = (re.match(r"^\s*\[([^\]]+)\]", it.get("objetoCompra") or "") or [None, ""])[1]
    cnpj = it["orgaoEntidade"]["cnpj"]
    pncp = {
        "numeroControle": it["numeroControlePNCP"], "cnpj": cnpj, "orgao": it["orgaoEntidade"].get("razaoSocial") or "",
        "esfera": ESFERAS.get(esfera_id, esfera_id), "cidade": cidade, "numero": numero, "modalidade": it.get("modalidadeNome") or "",
        "objeto": objeto, "valor": valor, "dataAbertura": it.get("dataAberturaProposta") or "",
        "dataEncerramento": it.get("dataEncerramentoProposta") or "", "dataPublicacao": it.get("dataPublicacaoPncp") or "",
        "situacao": it.get("situacaoCompraNome") or "", "linkOrigem": it.get("linkSistemaOrigem") or "", "portalNome": prefixo,
        "linkPncp": f"https://pncp.gov.br/app/editais/{cnpj}/{it['anoCompra']}/{it['sequencialCompra']}",
        "pav": True, "ter": False, "dre": False, "asfalto": False, "motivo": motivo, "prioridade": prioridade,
        "publicadoVezes": 1, "ibge": str((it.get("unidadeOrgao") or {}).get("codigoIbge") or ""),
    }
    agora = datetime.now(timezone.utc).isoformat()
    return {
        "origem": "PNCP", "dataSessao": pncp["dataEncerramento"], "orgao": pncp["orgao"], "cidade": cidade, "numero": numero,
        "modalidade": pncp["modalidade"], "objeto": objeto, "valor": valor, "linkPortal": pncp["linkOrigem"],
        "pncp": pncp, "naListaPncp": True, "interesse": None, "status": "", "servicos": [], "atestados": "", "observacao": "",
        "garantiaProposta": "", "vencedora": "", "camposEditados": [], "lote": agora, "criadoEm": agora, "atualizadoEm": agora,
        "triagem": triagem,
    }


def campo(v):
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, (int, float)):
        return {"doubleValue": float(v)}
    if isinstance(v, list):
        return {"arrayValue": {"values": [campo(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: campo(x) for k, x in v.items()}}}
    return h.campo(v)


_CONTROLE = None


def gravar(colecao, id_, dados):
    """Grava no Firestore. Registro NOVO no controle passa antes pela regra de duplicidade (uma licitação = um registro)."""
    global _CONTROLE
    if colecao == "licitacoes" and "criadoEm" in dados:
        import duplicidade
        if _CONTROLE is None:
            _CONTROLE = dict(h.licitacoes())
        if id_ not in _CONTROLE:
            copia = duplicidade.ja_existe(_CONTROLE, dados.get("objeto") or "", dados.get("orgao") or "", dados.get("cidade") or "",
                                          dados.get("numero"), dados.get("dataSessao"))
            if copia:
                print(f"   não lançada: já está no controle como {copia}")
                return False
        _CONTROLE[id_] = dados
    if "--teste" in sys.argv:   # só mostra o que faria, sem gravar
        return True
    corpo = json.dumps({"fields": {k: campo(v) for k, v in dados.items()}}).encode()
    h.http(f"{h.DOCS}/{colecao}/{id_}?key={h.CHAVE}", "PATCH", corpo)
    return True


def main():
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%dT%H:%M")
    itens = [it for it in abertas_mg() if (it.get("dataEncerramentoProposta") or "9")[:16] >= agora]
    cands = [it for it in itens if candidata(it.get("objetoCompra") or "")]
    print(f"{len(itens)} abertas em MG; {len(cands)} obras viárias que o objeto não denuncia")
    incluidas = sem_anexo = analisadas = 0
    for it in cands:
        id_ = doc_id(it)
        enc = it.get("dataEncerramentoProposta") or ""
        cache = existe("triagem_pncp", id_)
        if cache and h.valor(cache["fields"].get("encerramento")) == enc:
            continue   # já analisada com esta data
        if existe("licitacoes", id_):
            gravar("triagem_pncp", id_, {"encerramento": enc, "resultado": "já no controle"})
            continue   # evita duplicidade: já está no controle
        analisadas += 1
        texto, n_anexos, n_lidos = ler_anexos(it)
        tn = re.sub(r"manta asfaltica|impermeabiliza\w*|cobertura asfaltica", " ", h.norm(texto))
        achados = [nome for nome, rx, _ in SERVICOS_DOC if rx.search(tn)]
        # uma palavra solta ("asfalto" num estacionamento de UBS) não basta: precisa de 2 serviços
        # ou de subleito/base/BGS, que já caracterizam a obra viária
        nucleo = {"Regularização e compactação de subleito", "Base / sub-base", "BGS / brita graduada"}
        if len(achados) < 2 and not nucleo.intersection(achados):
            achados = []
        em = datetime.now(timezone.utc).isoformat()
        quem = f"{it['orgaoEntidade'].get('razaoSocial')} — {it.get('numeroCompra')}/{it.get('anoCompra')}"
        if achados:
            motivo = "Edital/TR/planilha: " + ", ".join(achados)
            gravar("licitacoes", id_, registro_pncp(it, motivo, "alta",
                   {"motivo": motivo, "prioridade": "alta", "fonte": "documentos", "anexos": "ok", "anexosLidos": n_lidos, "em": em}))
            incluidas += 1
            resultado = motivo
            print(f"INCLUÍDA: {quem} | {motivo}")
        elif n_lidos == 0:
            motivo = "Obra viária pelo objeto; anexos não puderam ser lidos" + ("" if n_anexos else " (nenhum anexo no PNCP)")
            gravar("licitacoes", id_, registro_pncp(it, motivo, "normal",
                   {"motivo": motivo, "prioridade": "normal", "fonte": "objeto", "anexos": "inacessiveis", "em": em}))
            sem_anexo += 1
            resultado = motivo
            print(f"INCLUÍDA (conferir anexos): {quem}")
        else:
            resultado = f"sem serviços de pavimentação nos {n_lidos} anexos lidos"
        gravar("triagem_pncp", id_, {"encerramento": enc, "resultado": resultado, "em": em})
        time.sleep(1)
    print(f"{analisadas} analisadas pelos anexos; {incluidas} incluídas por serviço encontrado; {sem_anexo} incluídas com anexos a conferir")


if __name__ == "__main__":
    sys.exit(main())
