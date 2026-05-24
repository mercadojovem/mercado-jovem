#!/usr/bin/env python3
"""
MERCADO JOVEM — Jornal Automático
Busca notícias reais, processa com Claude API,
salva no Supabase e envia para aprovação no Telegram.
"""

import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date

# ── CONFIGURAÇÕES ─────────────────────────────────────
SUPABASE_URL      = os.environ["SUPABASE_URL"]
SUPABASE_KEY      = os.environ["SUPABASE_SERVICE_KEY"]
ANTHROPIC_KEY     = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# ── SETORES E PALAVRAS-CHAVE ──────────────────────────
SETORES = {
    "Banco": {
        "queries": ["banco central juros brasil", "selic credito bancario", "inadimplencia financeiro brasil"],
        "empresas_keywords": ["banco", "financeiro", "crédito", "juros"]
    },
    "Energia": {
        "queries": ["energia eletrica brasil preco", "petroleo combustivel brasil", "energia renovavel solar eolica"],
        "empresas_keywords": ["energia", "petróleo", "combustível", "elétrica"]
    },
    "Tecnologia": {
        "queries": ["tecnologia startup brasil investimento", "inteligencia artificial empresas", "mercado tech digital brasil"],
        "empresas_keywords": ["tech", "tecnologia", "software", "digital", "startup"]
    },
    "Alimentos": {
        "queries": ["inflacao alimentos brasil supermercado", "agronegocio safra brasil", "commodities soja milho"],
        "empresas_keywords": ["alimento", "agro", "safra", "commodity"]
    },
    "Varejo": {
        "queries": ["varejo consumo vendas brasil", "comercio black friday brasil", "pib consumo familia"],
        "empresas_keywords": ["varejo", "comércio", "vendas", "consumo"]
    },
    "Transporte": {
        "queries": ["logistica transporte frete brasil", "combustivel greve caminhoneiros", "infraestrutura estradas portos"],
        "empresas_keywords": ["transporte", "logística", "frete", "caminhão"]
    },
    "Seguradora": {
        "queries": ["seguros brasil mercado crescimento", "sinistros seguradora brasil", "seguro vida saude brasil"],
        "empresas_keywords": ["seguro", "sinistro", "apólice"]
    },
    "Saneamento": {
        "queries": ["saneamento basico brasil agua", "concessao agua esgoto privatizacao", "infraestrutura hidrica brasil"],
        "empresas_keywords": ["saneamento", "água", "esgoto", "hídrico"]
    }
}

# ── FAIXAS DE IMPACTO ─────────────────────────────────
FAIXAS_IMPACTO = {
    "leve":    {"min": 1.0, "max": 3.0},
    "moderado": {"min": 3.0, "max": 6.0},
    "forte":   {"min": 6.0, "max": 10.0}
}

# ── BUSCAR NOTÍCIAS VIA RSS ───────────────────────────
def buscar_noticias_rss(query: str) -> list[dict]:
    """Busca notícias no Google News RSS."""
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        noticias = []

        for item in items[:3]:  # pega as 3 mais recentes
            titulo = item.findtext("title", "").strip()
            link   = item.findtext("link", "").strip()
            pub    = item.findtext("pubDate", "").strip()
            fonte  = item.findtext("source", "").strip()

            if titulo and link:
                noticias.append({
                    "titulo": titulo,
                    "link":   link,
                    "data":   pub,
                    "fonte":  fonte or "Google News"
                })

        return noticias
    except Exception as e:
        print(f"⚠️ Erro RSS ({query}): {e}")
        return []

# ── BUSCAR EMPRESAS DO SUPABASE ───────────────────────
def buscar_empresas() -> list[dict]:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/empresas?select=id,nome,codigo,setor,valor,variacao",
        headers=HEADERS_SB
    )
    if resp.status_code == 200:
        return resp.json()
    return []

# ── PROCESSAR COM CLAUDE API ──────────────────────────
def processar_com_claude(noticia_titulo: str, noticia_link: str, setor: str, empresas_do_setor: list[dict]) -> dict | None:
    """Usa Claude para analisar a notícia e gerar conteúdo didático."""

    empresas_str = ", ".join([f"{e['nome']} ({e['codigo']})" for e in empresas_do_setor]) if empresas_do_setor else "nenhuma empresa cadastrada neste setor"

    prompt = f"""Você é analista financeiro do projeto educacional "Mercado Jovem" para alunos do Ensino Médio.

Analise esta notícia real e gere um JSON com análise de impacto para o projeto.

NOTÍCIA: {noticia_titulo}
SETOR AFETADO: {setor}
EMPRESAS DO SETOR NO PROJETO: {empresas_str}

Responda APENAS com JSON válido, sem markdown, sem explicações, seguindo exatamente esta estrutura:

{{
  "relevante": true,
  "manchete": "título jornalístico impactante em até 10 palavras",
  "chapeu": "categoria em 2 palavras (ex: Crise Energética, Boom Tecnológico)",
  "corpo": "texto didático de 3 a 4 frases explicando a notícia para alunos do Ensino Médio, conectando com o mercado financeiro real",
  "impacto": "positivo ou negativo ou neutro",
  "intensidade": "leve ou moderado ou forte",
  "justificativa": "1 frase explicando por que esse impacto faz sentido economicamente",
  "pergunta": "1 pergunta reflexiva para os alunos sobre como reagir a essa notícia",
  "variacao_sugerida": 4.5
}}

REGRAS para variacao_sugerida:
- Sempre número positivo (o sinal depende do campo impacto)
- leve: entre 1.0 e 3.0
- moderado: entre 3.0 e 6.0  
- forte: entre 6.0 e 10.0
- NUNCA ultrapasse 10.0

Se a notícia não for relevante para o projeto, retorne: {{"relevante": false}}"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )

        if resp.status_code != 200:
            print(f"❌ Claude erro {resp.status_code}: {resp.text}")
            return None

        texto = resp.json()["content"][0]["text"].strip()

        # Remove possíveis blocos markdown
        if "```" in texto:
            texto = texto.split("```")[1]
            if texto.startswith("json"):
                texto = texto[4:]

        data = json.loads(texto)
        return data if data.get("relevante") else None

    except Exception as e:
        print(f"❌ Erro Claude: {e}")
        return None

# ── CALCULAR IMPACTO NAS EMPRESAS ─────────────────────
def calcular_impacto_empresas(empresas: list[dict], analise: dict, setor: str) -> list[dict]:
    """Calcula a variação sugerida para cada empresa do setor."""
    import random

    empresas_setor = [e for e in empresas if e.get("setor") == setor]
    if not empresas_setor:
        return []

    variacao_base = float(analise.get("variacao_sugerida", 3.0))
    sinal = -1 if analise.get("impacto") == "negativo" else 1

    resultado = []
    for emp in empresas_setor:
        # Pequena variação aleatória por empresa (±0.5%) para parecer mais real
        variacao_individual = variacao_base + random.uniform(-0.5, 0.5)
        variacao_individual = round(min(variacao_individual, 10.0), 2)

        valor_atual = float(emp.get("valor", 1000000))
        novo_valor  = valor_atual * (1 + (sinal * variacao_individual / 100))
        novo_valor  = round(novo_valor, 2)

        resultado.append({
            "id":               emp["id"],
            "nome":             emp["nome"],
            "codigo":           emp["codigo"],
            "valor_atual":      valor_atual,
            "novo_valor":       novo_valor,
            "variacao_pct":     round(sinal * variacao_individual, 2),
            "variacao_display": f"{'+' if sinal > 0 else ''}{sinal * variacao_individual:.1f}%"
        })

    return resultado

# ── SALVAR NO SUPABASE ─────────────────────────────────
def salvar_noticia(noticia_raw: dict, analise: dict, setor: str, empresas_impacto: list[dict], fonte_url: str) -> int | None:
    """Salva a notícia no Supabase com status pendente."""
    data = {
        "titulo":             analise["manchete"],
        "chapeu":             analise["chapeu"],
        "corpo":              analise["corpo"],
        "impacto":            analise["impacto"],
        "intensidade":        analise["intensidade"],
        "setor":              setor,
        "empresas_afetadas":  empresas_impacto,
        "status":             "pendente",
        "fonte_url":          fonte_url,
        "fonte_nome":         noticia_raw.get("fonte", "Google News"),
        "pergunta":           analise.get("pergunta", ""),
        "justificativa":      analise.get("justificativa", ""),
        "titulo_original":    noticia_raw["titulo"]
    }

    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/noticias",
        headers=HEADERS_SB,
        json=data
    )

    if resp.status_code in [200, 201]:
        resultado = resp.json()
        noticia_id = resultado[0]["id"] if isinstance(resultado, list) else resultado.get("id")
        print(f"✅ Notícia salva — ID {noticia_id}")
        return noticia_id
    else:
        print(f"❌ Erro ao salvar: {resp.status_code} — {resp.text}")
        return None

# ── ENVIAR PARA TELEGRAM ──────────────────────────────
def enviar_telegram(noticia_id: int, analise: dict, setor: str, empresas_impacto: list[dict], titulo_original: str) -> int | None:
    """Envia a notícia para o Telegram com botões de aprovação."""

    emoji_impacto = "🟢" if analise["impacto"] == "positivo" else ("🔴" if analise["impacto"] == "negativo" else "⚪")
    emoji_intensidade = {"leve": "🟡", "moderado": "🟠", "forte": "🔴"}.get(analise["intensidade"], "⚪")

    # Montar lista de empresas
    empresas_txt = ""
    for e in empresas_impacto:
        empresas_txt += f"\n  • {e['nome']} → *{e['variacao_display']}*"
    if not empresas_txt:
        empresas_txt = "\n  • Nenhuma empresa cadastrada neste setor"

    hoje = datetime.now().strftime("%d/%m/%Y")

    mensagem = (
        f"📰 *JORNAL MJ — Nova Notícia para Aprovação*\n"
        f"_{hoje}_\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏷️ *SETOR:* {setor}\n"
        f"{emoji_impacto} *IMPACTO:* {analise['impacto'].upper()} · "
        f"{emoji_intensidade} {analise['intensidade'].upper()}\n\n"
        f"📌 *MANCHETE:*\n_{analise['manchete']}_\n\n"
        f"📝 *TEXTO PARA OS ALUNOS:*\n{analise['corpo']}\n\n"
        f"💡 *JUSTIFICATIVA:*\n_{analise.get('justificativa', '')}_\n\n"
        f"❓ *PERGUNTA REFLEXIVA:*\n_{analise.get('pergunta', '')}_\n\n"
        f"🏢 *EMPRESAS AFETADAS:*{empresas_txt}\n\n"
        f"🔗 *Notícia original:* {titulo_original}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_ID interno: {noticia_id}_"
    )

    # Botões inline
    teclado = {
        "inline_keyboard": [[
            {"text": "✅ APROVAR E PUBLICAR", "callback_data": f"aprovar_{noticia_id}"},
            {"text": "❌ REJEITAR",           "callback_data": f"rejeitar_{noticia_id}"}
        ]]
    }

    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       mensagem,
            "parse_mode": "Markdown",
            "reply_markup": teclado,
            "disable_web_page_preview": True
        },
        timeout=15
    )

    if resp.status_code == 200:
        msg_id = resp.json()["result"]["message_id"]
        print(f"✅ Telegram enviado — msg_id {msg_id}")
        return msg_id
    else:
        print(f"❌ Erro Telegram: {resp.status_code} — {resp.text}")
        return None

# ── ATUALIZAR MSG_ID NO SUPABASE ──────────────────────
def atualizar_msg_id(noticia_id: int, msg_id: int):
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/noticias?id=eq.{noticia_id}",
        headers=HEADERS_SB,
        json={"telegram_msg_id": msg_id}
    )

# ── MAIN ──────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"JORNAL MJ — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}\n")

    # Buscar empresas cadastradas
    empresas = buscar_empresas()
    print(f"📊 {len(empresas)} empresas encontradas no Supabase\n")

    # Selecionar 3 setores com mais empresas cadastradas para priorizar
    setores_com_empresas = {}
    for e in empresas:
        s = e.get("setor", "")
        if s in SETORES:
            setores_com_empresas[s] = setores_com_empresas.get(s, 0) + 1

    # Preenche com setores sem empresas também (para buscar notícias gerais)
    for s in SETORES:
        if s not in setores_com_empresas:
            setores_com_empresas[s] = 0

    # Ordena: primeiro os que têm empresas, depois por nome
    setores_ordenados = sorted(
        setores_com_empresas.keys(),
        key=lambda s: (-setores_com_empresas[s], s)
    )

    noticias_publicadas = 0
    setores_tentados    = 0
    setores_usados      = set()

    for setor in setores_ordenados:
        if noticias_publicadas >= 3:
            break
        if setor in setores_usados:
            continue

        print(f"\n🔍 Buscando notícias para setor: {setor}")
        queries = SETORES[setor]["queries"]
        empresas_setor = [e for e in empresas if e.get("setor") == setor]

        noticia_encontrada = False

        for query in queries:
            if noticia_encontrada:
                break

            noticias_rss = buscar_noticias_rss(query)
            print(f"   Query '{query}': {len(noticias_rss)} notícias encontradas")

            for noticia_raw in noticias_rss:
                if noticia_encontrada:
                    break

                print(f"   ⚙️  Processando: {noticia_raw['titulo'][:60]}...")

                # Analisar com Claude
                analise = processar_com_claude(
                    noticia_raw["titulo"],
                    noticia_raw["link"],
                    setor,
                    empresas_setor
                )

                if not analise:
                    print("   ⏭️  Não relevante ou erro — pulando")
                    continue

                # Calcular impacto nas empresas
                empresas_impacto = calcular_impacto_empresas(empresas, analise, setor)

                # Salvar no Supabase
                noticia_id = salvar_noticia(
                    noticia_raw, analise, setor,
                    empresas_impacto, noticia_raw["link"]
                )

                if not noticia_id:
                    continue

                # Enviar para Telegram
                msg_id = enviar_telegram(
                    noticia_id, analise, setor,
                    empresas_impacto, noticia_raw["titulo"]
                )

                if msg_id:
                    atualizar_msg_id(noticia_id, msg_id)
                    noticias_publicadas += 1
                    setores_usados.add(setor)
                    noticia_encontrada = True
                    print(f"   ✅ Notícia {noticias_publicadas}/3 enviada para aprovação!")

    print(f"\n{'='*50}")
    print(f"✅ CONCLUÍDO — {noticias_publicadas}/3 notícias enviadas para aprovação")
    print(f"{'='*50}\n")

    if noticias_publicadas == 0:
        # Notifica que não encontrou notícias relevantes
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": "⚠️ *Jornal MJ* — Nenhuma notícia relevante encontrada hoje.\nO sistema tentará novamente amanhã.",
                "parse_mode": "Markdown"
            }
        )

if __name__ == "__main__":
    main()
