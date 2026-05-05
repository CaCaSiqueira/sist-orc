import pandas as pd
import io


def parse(file_bytes: bytes, nome_arquivo: str) -> pd.DataFrame:
    """
    Nubank exporta CSV da fatura com colunas:
    date, category, title, amount
    E CSV da conta com colunas:
    Data, Valor, Identificador, Descrição
    """
    content = file_bytes.decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(content))
    df.columns = [c.strip().lower() for c in df.columns]

    # fatura do cartão
    if "title" in df.columns and "amount" in df.columns:
        df = df.rename(columns={"date": "data", "title": "descricao", "amount": "valor"})
        df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce").abs()
        df["tipo"] = "despesa"
        df["banco"] = "nubank"
        df["conta_nome"] = "Nubank Cartão"
        df["conta_tipo"] = "cartao_credito"
        return df[["data", "descricao", "valor", "tipo", "banco", "conta_nome", "conta_tipo"]].dropna(subset=["data", "valor"])

    # conta corrente / NuConta
    if "descrição" in df.columns or "descricao" in df.columns:
        col_desc = "descrição" if "descrição" in df.columns else "descricao"
        col_val = "valor"
        col_data = "data"
        df = df.rename(columns={col_desc: "descricao", col_val: "valor", col_data: "data"})
        df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        df["tipo"] = df["valor"].apply(lambda v: "receita" if v > 0 else "despesa")
        df["valor"] = df["valor"].abs()
        df["banco"] = "nubank"
        df["conta_nome"] = "NuConta"
        df["conta_tipo"] = "conta_corrente"
        return df[["data", "descricao", "valor", "tipo", "banco", "conta_nome", "conta_tipo"]].dropna(subset=["data", "valor"])

    raise ValueError(f"Formato do arquivo Nubank não reconhecido: colunas encontradas: {list(df.columns)}")
