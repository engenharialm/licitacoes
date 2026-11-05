"""Lê o horário da disputa (sessão pública) no edital de cada licitação do PNCP ainda aberta
e grava no controle. O PNCP só informa o fim do envio de propostas, que às vezes é alguns
minutos antes da disputa ("Sessão pública 12 de novembro de 2026, às 09h00").

Roda no GitHub Actions (.github/workflows/horario-disputa.yml): o navegador não consegue baixar
os PDFs do PNCP, que respondem com um cabeçalho CORS inválido.

Grava em cada licitação:
  disputaEdital = { encerramento, sessao, trecho }  quando achou o horário no edital
  disputaEdital = { encerramento, conferir: true }  quando não achou (aparece "horário a conferir")
O "encerramento" é o do PNCP no momento da leitura: se o PNCP mudar a data, o edital é lido de novo.
"""
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from pypdf import PdfReader

PROJETO = "lm-construtora-13c8f"
CHAVE = "AIzaSyDcNsjr0GdYPj70IF74G0hhhKc8qQ_jpkc"
DOCS = f"https://firestore.googleapis.com/v1/projects/{PROJETO}/databases/(default)/documents"
MESES = {m: i + 1 for i, m in enumerate(["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
                                         "agosto", "setembro", "outubro", "novembro", "dezembro"])}
# onde o edital costuma dizer quando é a disputa, da mais certeira para a menos:
# "início da disputa" vence "sessão pública", que vence "abertura das propostas" (às vezes é só o fim do envio)
RX_CHAVES = [re.compile(r"inicio d[ao]s? (sessao de )?(disputa|lances)|sessao de (lances|disputa)|disputa de (precos|lances)|inicio da sessao"),
             re.compile(r"sessao publica|abertura da sessao|data da sessao"),
             re.compile(r"abertura das propostas|data de abertura|abertura do certame")]
RX_DATA = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})|(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})")
RX_HORA = re.compile(r"(\d{1,2})\s*(?:h|:|horas?)\s*(\d{2})?")


def norm(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def http(url, metodo="GET", corpo=None, tentativas=3):
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, method=metodo, data=corpo,
                                         headers={"Content-Type": "application/json", "User-Agent": "controle-licitacoes-lm"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            if t == tentativas - 1:
                raise
            time.sleep(5 * (t + 1))


def valor(f):
    if f is None:
        return None
    if "stringValue" in f:
        return f["stringValue"]
    if "booleanValue" in f:
        return f["booleanValue"]
    if "arrayValue" in f:
        return [valor(v) for v in f["arrayValue"].get("values", [])]
    if "mapValue" in f:
        return {k: valor(v) for k, v in f["mapValue"].get("fields", {}).items()}
    if "nullValue" in f:
        return None
    return next(iter(f.values()))


def campo(v):
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: campo(x) for k, x in v.items()}}}
    return {"stringValue": str(v)}


def licitacoes():
    token = ""
    while True:
        url = f"{DOCS}/licitacoes?key={CHAVE}&pageSize=300" + (f"&pageToken={token}" if token else "")
        j = json.loads(http(url))
        for d in j.get("documents", []):
            yield d["name"].rsplit("/", 1)[1], {k: valor(v) for k, v in d.get("fields", {}).items()}
        token = j.get("nextPageToken")
        if not token:
            return


def texto_do_edital(link):
    m = re.search(r"editais/(\d+)/(\d+)/(\d+)", link or "")
    if not m:
        return None
    base = f"https://pncp.gov.br/pncp-api/v1/orgaos/{m[1]}/compras/{m[2]}/{m[3]}/arquivos"
    arquivos = json.loads(http(base))
    # edital primeiro; depois aviso; planilhas e outros ficam de fora
    def prioridade(a):
        t = norm(urllib.parse.unquote(a.get("titulo", "")) + " " + (a.get("tipoDocumentoNome") or ""))
        return 0 if "edital" in t else 1 if "aviso" in t else 9
    for a in sorted(arquivos, key=prioridade):
        if prioridade(a) == 9:
            break
        try:
            leitor = PdfReader(io.BytesIO(http(a["url"])))
            return "\n".join((p.extract_text() or "") for p in leitor.pages[:15])
        except Exception:
            continue
    return None


def achar_disputa(texto, encerramento):
    """Data e hora da sessão citadas perto de "sessão pública", no mesmo dia do fim das propostas (ou até 1 dia depois)."""
    fim = datetime.fromisoformat(encerramento[:19])
    t = re.sub(r"\s+", " ", norm(texto))
    for rx in RX_CHAVES:
        for k in rx.finditer(t):
            janela = t[k.start():k.start() + 260]
            d = RX_DATA.search(janela)
            if not d:
                continue
            try:
                if d.group(1):
                    dia = datetime(int(d.group(3)), int(d.group(2)), int(d.group(1)))
                else:
                    dia = datetime(int(d.group(6)), MESES[d.group(5)], int(d.group(4)))
            except (KeyError, ValueError):
                continue
            if not (timedelta(0) <= dia - fim.replace(hour=0, minute=0, second=0) <= timedelta(days=1)):
                continue
            # a hora mais perto da data: depois ("dia 12/11, às 09h") ou logo antes ("09:00:00 13/11/2026")
            # "até as 08:59" é prazo de proposta e "impugnação até 23:59" é outro prazo: ficam de fora
            corte = re.search(r"impugna|esclarec|limite", janela[d.end():])
            fim_busca = d.end() + min(60, corte.start() if corte else 60)
            horas = [h for h in RX_HORA.finditer(janela, max(0, d.start() - 25), fim_busca)
                     if int(h.group(1)) <= 23 and int(h.group(2) or 0) <= 59 and not RX_DATA.match(janela, h.start())
                     and not re.search(r"\bate\b", janela[max(0, h.start() - 8):h.start()])]
            if not horas:
                continue
            h = min(horas, key=lambda h: h.start() - d.end() if h.start() >= d.end() else (d.start() - h.end()) + 30)
            sessao = dia.replace(hour=int(h.group(1)), minute=int(h.group(2) or 0))
            return sessao.strftime("%Y-%m-%dT%H:%M:00"), janela[:160]
    return None, None


def gravar(doc_id, dados):
    mascara = "&".join(f"updateMask.fieldPaths={k}" for k in dados)
    corpo = json.dumps({"fields": {k: campo(v) for k, v in dados.items()}}).encode()
    http(f"{DOCS}/licitacoes/{doc_id}?key={CHAVE}&{mascara}", "PATCH", corpo)


def main():
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%dT%H:%M")
    lidas = achadas = 0
    for doc_id, l in licitacoes():
        p = l.get("pncp") or {}
        enc = p.get("dataEncerramento") or ""
        if l.get("origem") != "PNCP" or not enc or enc[:16] < agora or l.get("naListaPncp") is False:
            continue
        if (l.get("disputaEdital") or {}).get("encerramento") == enc:
            continue   # já lido com esta data do PNCP
        lidas += 1
        try:
            texto = texto_do_edital(p.get("linkPncp"))
        except Exception as e:
            print(f"falha ao ler edital {doc_id}: {e}")
            continue
        sessao, trecho = achar_disputa(texto or "", enc)
        dados = {"disputaEdital": {"encerramento": enc, "sessao": sessao, "trecho": trecho} if sessao
                 else {"encerramento": enc, "conferir": True},
                 "atualizadoEm": datetime.now(timezone.utc).isoformat()}
        # o horário da disputa vira a data da sessão, salvo se a equipe ajustou à mão
        if sessao and "dataSessao" not in (l.get("camposEditados") or []):
            dados["dataSessao"] = sessao
        achadas += bool(sessao)
        gravar(doc_id, dados)
        print(f"{'OK ' + sessao if sessao else 'a conferir'}: {l.get('orgao')} — {l.get('numero')}")
        time.sleep(1)
    print(f"{lidas} editais lidos, {achadas} com horário da disputa encontrado")


if __name__ == "__main__":
    sys.exit(main())
