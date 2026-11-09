"""Portal CitizenTech: enviar solicitação, acompanhar o robô e conversar com o assistente.

    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from robo.config import load_config, path  # noqa: E402

BRT = timezone(timedelta(hours=-3))
st.set_page_config(page_title="CitizenTech", page_icon="🏛️", layout="wide")


@st.cache_resource(show_spinner="Carregando o assistente…")
def get_rag():
    from robo.integracao import criar_rag
    rag, origem = criar_rag()
    return (rag, None) if rag is not None else (None, origem)


SEM_MUNICIPIO = "Não informar"


@st.cache_data
def municipios() -> dict[str, dict[str, str]]:
    """Municípios atendidos, rotulados como 'Nome (UF)'. Sem o arquivo, o campo fica só com 'Não informar'."""
    try:
        tabela = pd.read_csv(ROOT / "data" / "municipios_semiarido.csv", dtype=str, encoding="utf-8-sig")
    except (OSError, ValueError):
        return {}
    return {f"{m.municipio} ({m.uf})": {"municipio": m.municipio, "uf": m.uf, "cod_ibge": m.cod_ibge}
            for m in tabela.sort_values("municipio").itertuples()}


def pagina_enviar():
    st.header("Enviar solicitação")
    st.caption("Protótipo acadêmico: use apenas dados fictícios. Nenhum dado pessoal real deve ser enviado.")
    locais = municipios()
    with st.form("solicitacao", clear_on_submit=True):
        nome = st.text_input("Nome (fictício)", "Fulano de Tal")
        email = st.text_input("E-mail (fictício)", "fulano@exemplo.com")
        local = st.selectbox("Município", [SEM_MUNICIPIO, *locais],
                             help="Usado para agrupar os pedidos por município no painel do gestor.")
        texto = st.text_area("Do que você precisa?",
                             placeholder="Ex.: Perdi a roça de milho na seca e quero entrar no Garantia-Safra.")
        anexos = st.file_uploader("Documentos (imagem ou PDF)", type=["png", "jpg", "jpeg", "pdf"],
                                  accept_multiple_files=True)
        ok = st.form_submit_button("Enviar")
    if ok:
        if not texto.strip():
            st.error("Descreva o que você precisa.")
            return
        rid = "WEB-" + uuid.uuid4().hex[:6].upper()
        inbox = path("inbox")
        (inbox / "anexos").mkdir(parents=True, exist_ok=True)
        rels = []
        for i, f in enumerate(anexos or []):
            rel = Path("anexos") / f"{rid}_{i}{Path(f.name).suffix.lower()}"
            (inbox / rel).write_bytes(f.getvalue())
            rels.append(rel.as_posix())
        req = {"request_id": rid, "data_envio": datetime.now(BRT).isoformat(timespec="seconds"),
               "nome": nome, "email": email, **locais.get(local, {}), "texto": texto, "anexos": rels}
        (inbox / f"{rid}.json").write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
        st.success(f"Solicitação {rid} registrada na fila do robô.")

    st.divider()
    pend = sorted(path("inbox").glob("*.json")) if path("inbox").exists() else []
    st.write(f"Solicitações aguardando o robô: **{len(pend)}**")
    c1, c2 = st.columns(2)
    sem_genai = c2.toggle("Responder só por template (sem LLM)", value=False)
    if c1.button("▶ Executar o robô agora", type="primary", disabled=not pend):
        import run_robot  # noqa: E402
        with st.spinner("Robô em execução…"):
            args = ["--sem-coleta"] + (["--sem-genai"] if sem_genai else [])
            summary = run_robot.main(args)
        st.success(f"Execução {summary['run_id']}: {summary['resolvidas']} resolvidas, "
                   f"{summary['revisao_humana']} para revisão humana, {summary['invalidas']} inválidas.")
        for r in summary["resultados"]:
            eml = path("outbox") / f"{r['request_id']}.eml"
            with st.expander(f"{r['request_id']} — {r['decisao']} ({r.get('service_id') or '-'})"):
                st.json({k: v for k, v in r.items() if k != "run_id"})
                if eml.exists():
                    from email import policy
                    from email.parser import BytesParser
                    msg = BytesParser(policy=policy.default).parsebytes(eml.read_bytes())
                    st.text(msg.get_body(preferencelist=("plain",)).get_content())


def pagina_painel():
    st.header("Painel do robô")
    f = path("control_sheet")
    if not f.exists():
        st.info("Ainda não há execuções. Rode `python run_robot.py --carregar-teste`.")
        return
    try:
        xl = pd.read_excel(f, sheet_name=None)
    except Exception as exc:
        st.error(f"Não foi possível ler a planilha de controle: {exc}")
        return
    sol, rev, exe = xl.get("solicitacoes"), xl.get("revisao_humana"), xl.get("execucoes")
    if sol is not None and len(sol):
        c = st.columns(4)
        c[0].metric("Solicitações", len(sol))
        c[1].metric("Resolvidas", int((sol["decisao"] == "resolvido").sum()))
        c[2].metric("Revisão humana", int((sol["decisao"] == "revisao_humana").sum()))
        c[3].metric("Respostas via RAG", int((sol["fonte_resposta"] == "rag").sum()))
        st.subheader("Serviços mais pedidos")
        st.bar_chart(sol["service_id"].fillna("fora_escopo").value_counts())
    if rev is not None and len(rev):
        st.subheader("Fila de revisão humana")
        st.dataframe(rev, use_container_width=True, hide_index=True)
        pendentes = rev.loc[rev["status"] == "pendente", "request_id"].tolist()
        if pendentes:
            from robo.revisao import DESFECHOS, fechar
            with st.form("fechar_revisao"):
                pedido = st.selectbox("Pedido pendente", pendentes)
                desfecho = st.selectbox("Desfecho", DESFECHOS)
                responsavel = st.text_input("Responsável")
                observacao = st.text_area("Observação")
                if st.form_submit_button("Fechar revisão"):
                    try:
                        fechar(pedido, desfecho, responsavel, observacao)
                        st.success("Revisão fechada.")
                        st.rerun()
                    except (ValueError, OSError) as exc:
                        st.error(str(exc))
    if exe is not None and len(exe):
        st.subheader("Execuções")
        st.dataframe(exe.sort_values("run_id", ascending=False), use_container_width=True, hide_index=True)
    if sol is not None:
        with st.expander("Todas as solicitações"):
            st.dataframe(sol, use_container_width=True, hide_index=True)
    logf = path("logs")
    if logf.exists():
        with st.expander("Últimas linhas do log"):
            st.code("\n".join(logf.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]))


def pagina_chat():
    st.header("Assistente de serviços públicos")
    st.caption("Respostas baseadas nas Cartas de Serviço oficiais do gov.br, com citação das fontes. "
               "Se a informação não estiver nas fontes, o assistente avisa em vez de inventar.")
    rag, err = get_rag()
    if rag is None:
        st.error(f"Assistente indisponível: {err}")
        return
    hist = st.session_state.setdefault("hist", [])
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    q = st.chat_input("Pergunte sobre um serviço público…")
    if not q:
        return
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"), st.spinner("Consultando as fontes…"):
        try:
            out = rag.answer(q, history=hist[-6:])
        except Exception as exc:
            out = {"answer": f"Desculpe, ocorreu um erro ({exc}).", "citations": [], "chunks": []}
        st.markdown(out.get("answer") or "_Sem resposta._")
        if out.get("blocked"):
            st.warning("Pedido bloqueado pelas proteções do assistente.")
        cits = out.get("citations") or []
        if cits:
            st.markdown("**Fontes:** " + " · ".join(f"[{c['n']}] [{c['titulo']}]({c['url']})" for c in cits))
        with st.expander("Trechos recuperados"):
            for ch in out.get("chunks") or []:
                md = ch.get("metadata", {})
                st.markdown(f"**{md.get('titulo', '')} — {md.get('secao', '')}** (score {ch.get('score', 0):.3f})")
                st.caption(ch.get("text", "")[:600])
    hist += [{"role": "user", "content": q}, {"role": "assistant", "content": out.get("answer", "")}]


PAGINAS = {"Enviar solicitação": pagina_enviar, "Painel do robô": pagina_painel, "Assistente": pagina_chat}
with st.sidebar:
    st.title("🏛️ CitizenTech")
    escolha = st.radio("Navegação", list(PAGINAS))
    st.caption(f"Serviços atendidos: {len(load_config()['services'])}")
PAGINAS[escolha]()
