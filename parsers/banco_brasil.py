import pandas as pd
import io
import re


def _parse_ofx(content: str) -> pd.DataFrame:
    transactions = []
    blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", content, re.DOTALL)
    for block in blocks:
        def get(tag):
            m = re.search(rf"<{tag}>(.*?)(?:<|$)", block)
            return m.group(1).strip() if m else ""

        dtposted = get("DTPOSTED")[:8]
        amount   = get("TRNAMT").replace(",", ".")
        memo     = get("MEMO") or get("NAME")

        try:
            data  = pd.to_datetime(dtposted, format="%Y%m%d").strftime("%Y-%m-%d")
            valor = float(amount)
        except Exception:
            continue

        tipo = "receita" if valor > 0 else "despesa"
        transactions.append({"data": data, "descricao": memo, "valor": abs(valor), "tipo": tipo})

    return pd.DataFrame(transactions)


def _to_float(val) -> float:
    """Converte 'R$ 1.234,56' ou '-1.234,56' ou '1234.56' para float."""
    s = str(val).replace("R$", "").strip()
    # remove separador de milhar (ponto antes de vírgula: '1.234,56' → '1234,56')
    s = re.sub(r"\.(?=\d{3}[,])", "", s)
    s = s.replace(",", ".").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def _read_csv_attempt(file_bytes: bytes):
    """Tenta ler o CSV do BB com diferentes encodings e separadores.
    Retorna (DataFrame com header=None, encoding, sep) ou levanta ValueError."""
    for enc in ("latin-1", "utf-8", "cp1252"):
        for sep in (",", ";", "\t"):
            try:
                text = file_bytes.decode(enc)
                df = pd.read_csv(io.StringIO(text), sep=sep, header=None, dtype=str)
                # considera válido se tiver pelo menos 2 colunas
                if df.shape[1] >= 2:
                    return df, enc, sep
            except Exception:
                continue
    raise ValueError("Não foi possível ler o arquivo CSV. Verifique o formato.")


def _parse_csv(file_bytes: bytes, nome_arquivo: str) -> pd.DataFrame:
    ext = nome_arquivo.lower().split(".")[-1]

    if ext in ("xls", "xlsx"):
        df = pd.read_excel(io.BytesIO(file_bytes), header=None, dtype=str)
    else:
        df, enc, sep = _read_csv_attempt(file_bytes)

    # ── encontra a linha de cabeçalho ────────────────────────────────────────
    header_row = None
    for i, row in df.iterrows():
        vals = [str(v).strip().lower() for v in row]
        has_date  = any("data" in v for v in vals)
        has_value = any(kw in v for v in vals for kw in ("valor", "débit", "debito", "crédit", "credito", "entrada", "saída", "saida"))
        if has_date and has_value:
            header_row = i
            break

    if header_row is None:
        header_row = 0

    df.columns = [str(v).strip() for v in df.iloc[header_row]]
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    df.columns = [c.lower() for c in df.columns]

    # ── mapeia colunas pelos nomes encontrados ────────────────────────────────
    def find_col(*keywords):
        for c in df.columns:
            cn = c.lower()
            if any(kw in cn for kw in keywords):
                return c
        return None

    col_data = find_col("data")
    col_hist = find_col("lançamento", "lancamento", "histórico", "historico", "descri", "memo")
    col_det  = find_col("detalhe")
    col_tipo = find_col("tipo lançamento", "tipo lancamento", "tipo")
    col_deb  = find_col("débit", "debito", "saída", "saida")
    col_cred = find_col("crédit", "credito", "entrada")
    col_val  = find_col("valor")

    if col_data is None:
        raise ValueError(f"Coluna de data não encontrada. Colunas detectadas: {list(df.columns)}")

    # ── extrai linhas ────────────────────────────────────────────────────────
    rows = []
    for _, row in df.iterrows():
        data_raw = str(row.get(col_data, "")).strip()

        # pula linhas inválidas (saldo do dia, totais, cabeçalhos repetidos)
        if not data_raw or data_raw.lower() in ("nan", "data", ""):
            continue
        if re.match(r"^00/00", data_raw):          # datas "00/00/0000"
            continue

        try:
            dt = pd.to_datetime(data_raw, dayfirst=True, errors="coerce")
            if pd.isna(dt):
                continue
            data = dt.strftime("%Y-%m-%d")
        except Exception:
            continue

        # descrição: junta Lançamento + Detalhes quando disponível
        hist = str(row.get(col_hist, "")).strip() if col_hist else ""
        det  = str(row.get(col_det,  "")).strip() if col_det  else ""
        if det and det.lower() not in ("nan", ""):
            descricao = f"{hist} — {det}" if hist else det
        else:
            descricao = hist or "BB"

        # pula linhas de saldo anterior/do dia
        if hist.lower() in ("saldo anterior", "saldo do dia", "saldo"):
            continue

        # ── valor e tipo ──────────────────────────────────────────────────────
        if col_deb and col_cred:
            # formato com colunas separadas de Débito e Crédito
            deb  = _to_float(row.get(col_deb,  0))
            cred = _to_float(row.get(col_cred, 0))
            if deb > 0:
                rows.append({"data": data, "descricao": descricao, "valor": deb,  "tipo": "despesa"})
            if cred > 0:
                rows.append({"data": data, "descricao": descricao, "valor": cred, "tipo": "receita"})

        elif col_val:
            # formato com coluna única de Valor (positivo = entrada, negativo = saída)
            v = _to_float(row.get(col_val, 0))
            if v == 0:
                continue

            # tenta usar a coluna "Tipo Lançamento" (Entrada / Saída)
            if col_tipo:
                tipo_raw = str(row.get(col_tipo, "")).strip().lower()
                if "entrada" in tipo_raw:
                    tipo = "receita"
                elif "saída" in tipo_raw or "saida" in tipo_raw or "débito" in tipo_raw or "debito" in tipo_raw:
                    tipo = "despesa"
                else:
                    tipo = "receita" if v > 0 else "despesa"
            else:
                tipo = "receita" if v > 0 else "despesa"

            rows.append({"data": data, "descricao": descricao, "valor": abs(v), "tipo": tipo})

    if not rows:
        raise ValueError(
            f"Nenhuma transação encontrada. Colunas detectadas: {list(df.columns)}. "
            "Verifique se o arquivo é um extrato válido do Banco do Brasil."
        )

    return pd.DataFrame(rows)


def parse(file_bytes: bytes, nome_arquivo: str) -> pd.DataFrame:
    ext = nome_arquivo.lower().split(".")[-1]

    if ext == "ofx":
        for enc in ("latin-1", "utf-8", "cp1252"):
            try:
                df = _parse_ofx(file_bytes.decode(enc))
                if not df.empty:
                    break
            except Exception:
                continue
        else:
            raise ValueError("Não foi possível ler o arquivo OFX.")
    else:
        df = _parse_csv(file_bytes, nome_arquivo)

    df["banco"]      = "bb"
    df["conta_nome"] = "Banco do Brasil"
    df["conta_tipo"] = "conta_corrente"

    return df[["data", "descricao", "valor", "tipo", "banco", "conta_nome", "conta_tipo"]].dropna(subset=["data", "valor"])
