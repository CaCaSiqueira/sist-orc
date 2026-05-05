import pandas as pd
import io


def parse(file_bytes: bytes, nome_arquivo: str) -> pd.DataFrame:
    """
    Mercado Pago exporta CSV ou XLSX.
    Colunas comuns: DATA, DESCRIÇÃO, TIPO, VALOR
    """
    ext = nome_arquivo.lower().split(".")[-1]

    if ext in ("xls", "xlsx"):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                df = pd.read_csv(io.StringIO(file_bytes.decode(enc)))
                break
            except Exception:
                continue

    df.columns = [c.strip().lower()
                   .replace("ã", "a").replace("ç", "c").replace("ê", "e")
                   .replace("é", "e").replace("á", "a").replace("ó", "o")
                  for c in df.columns]

    # mapear colunas flexivelmente
    col_map = {}
    for col in df.columns:
        if "data" in col or "date" in col:
            col_map["data"] = col
        elif "descri" in col or "titulo" in col or "detalhe" in col or "origin" in col:
            col_map["descricao"] = col
        elif "valor" in col or "amount" in col or "total" in col:
            col_map["valor"] = col
        elif "tipo" in col or "type" in col or "operac" in col:
            col_map["tipo_orig"] = col

    if "data" not in col_map or "valor" not in col_map:
        raise ValueError(f"Colunas esperadas não encontradas. Colunas no arquivo: {list(df.columns)}")

    df = df.rename(columns={v: k for k, v in col_map.items()})

    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
    df["valor"] = (
        df["valor"].astype(str)
        .str.replace("R$", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")

    if "descricao" not in df.columns:
        df["descricao"] = "Transação Mercado Pago"

    df["tipo"] = df["valor"].apply(lambda v: "receita" if v > 0 else "despesa")
    df["valor"] = df["valor"].abs()
    df["banco"] = "mercado_pago"
    df["conta_nome"] = "Mercado Pago"
    df["conta_tipo"] = "carteira_digital"

    return df[["data", "descricao", "valor", "tipo", "banco", "conta_nome", "conta_tipo"]].dropna(subset=["data", "valor"])
