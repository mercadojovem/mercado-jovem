#!/usr/bin/env python3
import os, json, random, requests, xml.etree.ElementTree as ET
from datetime import datetime, timedelta

SUPABASE_URL     = os.environ["SUPABASE_URL"]
SUPABASE_KEY     = os.environ["SUPABASE_SERVICE_KEY"]
ANTHROPIC_KEY    = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# Fontes globais com RSS direto
FONTES_GLOBAIS = [
    {"nome": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"nome": "CNBC Business",    "url": "https://www.cnbc.com/id/10001147/device/rss/rss.html"},
    {"nome": "Yahoo Finance",    "url": "https://finance.yahoo.com/news/rssindex"},
    {"nome": "Financial Times",  "url": "https://www.ft.com/rss/home"},
    {"nome": "Valor Econômico",  "url": "https://valor.globo.com/rss/"},
]

# Palavras-chave por setor para filtrar notícias das fontes globais
KEYWORDS_SETOR = {
    "Banco":       ["bank","banking","interest rate","credit","federal reserve","central bank","juros","banco","selic","credito","inadimplencia","fintech"],
    "Energia":     ["oil","energy","petroleum","fuel","solar","wind","electricity","crude","energia","petroleo","combustivel","eletrica","aneel"],
    "Tecnologia":  ["tech","technology","ai","artificial intelligence","startup","software","digital","chip","semiconductor","tecnologia","inteligencia artificial"],
    "Alimentos":   ["food","agriculture","commodity","soybean","corn","grain","crop","alimento","agronegocio","safra","commodities","inflacao alimentar"],
    "Varejo":      ["retail","consumer","sales","e-commerce","shopping","spending","varejo","consumo","vendas","comercio","supermercado"],
    "Transporte":  ["transport","logistics","freight","aviation","shipping","airline","transporte","logistica","frete","aviacao","porto"],
    "Seguradora":  ["insurance","insurer","reinsurance","claim","premium","seguro","seguradora","sinistro","apolice"],
    "Saneamento":  ["water","sanitation","sewage","infrastructure","utilities","agua","saneamento","esgoto","hidrico"],
    "Asset Mgmt":  ["fund","investment","stock market","bonds","portfolio","asset","fundo","investimento","bolsa","acoes","ibovespa","renda fixa"],
    "Com. Exterior":["trade","export","import","tariff","dollar","exchange rate","exportacao","importacao","cambio","dolar","balanca comercial"],
}

# Queries Google News por setor
SETORES = {
    "Banco":       {"queries": ["banco central brasil selic decisao","credito bancario inadimplencia brasil","banco digital fintechs brasil","spread bancario juros emprestimo","sistema financeiro nacional regulacao"]},
    "Energia":     {"queries": ["energia eletrica tarifa brasil","petroleo preco barril mercado","energia solar eolica geracao brasil","combustivel gasolina etanol preco","aneel energia distribuicao brasil"]},
    "Tecnologia":  {"queries": ["startup tecnologia investimento brasil","inteligencia artificial empresas impacto","e-commerce vendas online brasil","ciberseguranca ataques empresas","semiconductores chips industria tech"]},
    "Alimentos":   {"queries": ["inflacao alimentar supermercado brasil","agronegocio exportacao commodities","safra producao agricola brasil","precos alimentos alta baixa","industria alimenticia crescimento"]},
    "Varejo":      {"queries": ["varejo vendas consumo brasil","comercio eletronico crescimento","confianca consumidor indice brasil","shopping lojas faturamento","emprego renda consumo familia"]},
    "Transporte":  {"queries": ["logistica frete transportadora brasil","infraestrutura rodovias porto aeroporto","combustivel diesel transportes custo","aviacao passageiros voos brasil","mobilidade urbana transporte publico"]},
    "Seguradora":  {"queries": ["seguros mercado brasil crescimento","seguro saude plano assistencia","sinistros indenizacoes setor segurador","seguro rural producao agricola","resseguro mercado regulacao"]},
    "Saneamento":  {"queries": ["saneamento basico brasil agua","concessao agua esgoto privatizacao","marco saneamento investimentos","escassez hidrica reservatorios nivel","infraestrutura hidrica obras brasil"]},
    "Asset Mgmt":  {"queries": ["fundos investimento renda fixa variavel","bolsa valores ibovespa semana","tesouro direto renda fixa rentabilidade","mercado financeiro capitalizacao","gestao ativos fundos brasileiros"]},
    "Com. Exterior":{"queries": ["exportacao importacao brasil balanca comercial","dolar real cambio variacao","comercio exterior tarifas china eua","exportacao commodities brasil mercado","acordo comercial brasil parceiros"]},
}


def buscar_titulos_recentes() -> set:
    desde = (datetime.now() - timedelta(days=7)).isoformat()
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/noticias?select=titulo_original&created_at=gte.{desde}&status=in.(aprovado,pendente)",
        headers=HEADERS_SB, timeout=10
    )
    if resp.status_code != 200:
        return set()
    return {r.get("titulo_original", "").lower().strip() for r in resp.json()}


def buscar_setores_recentes() -> list:
    desde = (datetime.now() - timedelta(days=2)).isoformat()
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/noticias?select=setor&created_at=gte.{desde}&status=in.(aprovado,pendente)",
        headers=HEADERS_SB, timeout=10
    )
    if resp.status_code != 200:
        return []
    return [r.get("setor", "") for r in resp.json()]


def titulo_similar(titulo: str, publicados: set) -> bool:
    stop = {"de","da","do","e","o","a","no","na","em","para","com","que","se","os","as","um","uma","the","of","in","to","and","a","for","is","are","on","at"}
    palavras = set(titulo.lower().split()) - stop
    for pub in publicados:
        palavras_pub = set(pub.split()) - stop
        if len(palavras & palavras_pub) >= 4:
            return True
    return False


def buscar_rss(url: str, nome: str, setor: str = None) -> list:
    """Busca notícias de uma URL RSS. Se setor fornecido, filtra por palavras-chave."""
    try:
        resp = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        noticias = []
        keywords = [k.lower() for k in KEYWORDS_SETOR.get(setor, [])] if setor else []
        for item in items[:10]:
            titulo = item.findtext("title", "").strip()
            link   = item.findtext("link", "").strip()
            pub    = item.findtext("pubDate", "").strip()
            if not titulo or not link:
                continue
            # Se filtrando por setor, verifica keywords
            if keywords:
                titulo_lower = titulo.lower()
                if not any(k in titulo_lower for k in keywords):
                    continue
            noticias.append({"titulo": titulo, "link": link, "data": pub, "fonte": nome})
        return noticias
    except Exception as e:
        print(f"  Erro RSS {nome}: {e}")
        return []


def buscar_google_news(query: str) -> list:
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        noticias = []
        for item in items[:5]:
            titulo = item.findtext("title", "").strip()
            link   = item.findtext("link", "").strip()
            pub    = item.findtext("pubDate", "").strip()
            fonte  = item.findtext("source", "").strip()
            if titulo and link:
                noticias.append({"titulo": titulo, "link": link, "data": pub, "fonte": fonte or "Google News"})
        return noticias
    except Exception as e:
        print(f"  Erro Google News ({query}): {e}")
        return []


def buscar_empresas() -> list:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/empresas?select=id,nome,codigo,setor,valor,variacao",
        headers=HEADERS_SB
    )
    return resp.json() if resp.status_code == 200 else []


def processar_com_claude(titulo: str, setor: str, empresas_setor: list) -> dict | None:
    empresas_str = ", ".join([f"{e['nome']} ({e['codigo']})" for e in empresas_setor]) if empresas_setor else "sem empresas cadastradas"
    prompt = f"""Analise esta notícia e gere um JSON de impacto para uma simulação de bolsa escolar.

NOTÍCIA: {titulo}
SETOR: {setor}
EMPRESAS DO SETOR: {empresas_str}

Responda APENAS com JSON válido, sem markdown:

{{
  "relevante": true,
  "manchete": "título jornalístico em até 10 palavras",
  "chapeu": "categoria em 2 palavras",
  "corpo": "3 a 4 frases explicando o impacto econômico de forma clara e direta",
  "impacto": "positivo ou negativo ou neutro",
  "intensidade": "leve ou moderado ou forte",
  "justificativa": "1 frase explicando o impacto econômico",
  "pergunta": "1 pergunta reflexiva sobre como reagir a essa notícia",
  "variacao_sugerida": 4.5
}}

variacao_sugerida: número positivo. leve=1-3, moderado=3-6, forte=6-10. Nunca acima de 10.
Se não for relevante para o setor, retorne: {{"relevante": false}}"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-5", "max_tokens": 800, "messages": [{"role": "user", "content": prompt}]},
            timeout=30
        )
        if resp.status_code != 200:
            return None
        texto = resp.json()["content"][0]["text"].strip()
        if "```" in texto:
            texto = texto.split("```")[1]
            if texto.startswith("json"):
                texto = texto[4:]
        data = json.loads(texto)
        return data if data.get("relevante") else None
    except Exception as e:
        print(f"  Erro Claude: {e}")
        return None


def calcular_impacto_empresas(empresas: list, analise: dict, setor: str) -> list:
    empresas_setor = [e for e in empresas if e.get("setor") == setor]
    if not empresas_setor:
        return []
    variacao_base = float(analise.get("variacao_sugerida", 3.0))
    sinal = -1 if analise.get("impacto") == "negativo" else 1
    resultado = []
    for emp in empresas_setor:
        var = round(min(variacao_base + random.uniform(-0.5, 0.5), 10.0), 2)
        valor_atual = float(emp.get("valor", 1000000))
        novo_valor  = round(valor_atual * (1 + (sinal * var / 100)), 2)
        resultado.append({
            "id": emp["id"], "nome": emp["nome"], "codigo": emp["codigo"],
            "valor_atual": valor_atual, "novo_valor": novo_valor,
            "variacao_pct": round(sinal * var, 2),
            "variacao_display": f"{'+' if sinal > 0 else ''}{sinal * var:.1f}%"
        })
    return resultado


def salvar_noticia(noticia_raw: dict, analise: dict, setor: str, empresas_impacto: list, fonte_url: str) -> int | None:
    data = {
        "titulo": analise["manchete"], "chapeu": analise["chapeu"],
        "corpo": analise["corpo"], "impacto": analise["impacto"],
        "intensidade": analise["intensidade"], "setor": setor,
        "empresas_afetadas": empresas_impacto, "status": "pendente",
        "fonte_url": fonte_url, "fonte_nome": noticia_raw.get("fonte", "Google News"),
        "pergunta": analise.get("pergunta", ""),
        "justificativa": analise.get("justificativa", ""),
        "titulo_original": noticia_raw["titulo"]
    }
    resp = requests.post(f"{SUPABASE_URL}/rest/v1/noticias", headers=HEADERS_SB, json=data)
    if resp.status_code in [200, 201]:
        resultado = resp.json()
        return resultado[0]["id"] if isinstance(resultado, list) else resultado.get("id")
    return None


def enviar_telegram(noticia_id: int, analise: dict, setor: str, empresas_impacto: list, titulo_original: str, fonte: str) -> int | None:
    emoji_imp = "🟢" if analise["impacto"] == "positivo" else ("🔴" if analise["impacto"] == "negativo" else "⚪")
    emoji_int = {"leve": "🟡", "moderado": "🟠", "forte": "🔴"}.get(analise["intensidade"], "⚪")
    emps_txt = "".join([f"\n  • {e['nome']} → *{e['variacao_display']}*" for e in empresas_impacto]) or "\n  • Impacto geral no mercado"
    hoje = datetime.now().strftime("%d/%m/%Y")
    mensagem = (
        f"📰 *JORNAL MJ — Aprovação*\n_{hoje}_\n━━━━━━━━━━━━━━━━\n\n"
        f"🏷️ *SETOR:* {setor}  |  📡 *FONTE:* {fonte}\n"
        f"{emoji_imp} *IMPACTO:* {analise['impacto'].upper()} · {emoji_int} {analise['intensidade'].upper()}\n\n"
        f"📌 *MANCHETE:*\n_{analise['manchete']}_\n\n"
        f"📝 *TEXTO:*\n{analise['corpo']}\n\n"
        f"💡 _{analise.get('justificativa', '')}_\n\n"
        f"❓ _{analise.get('pergunta', '')}_\n\n"
        f"🏢 *EMPRESAS:*{emps_txt}\n\n"
        f"🔗 {titulo_original}\n"
        f"━━━━━━━━━━━━━━━━\n_ID: {noticia_id}_"
    )
    teclado = {"inline_keyboard": [[
        {"text": "✅ APROVAR", "callback_data": f"aprovar_{noticia_id}"},
        {"text": "❌ REJEITAR", "callback_data": f"rejeitar_{noticia_id}"}
    ]]}
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown",
              "reply_markup": teclado, "disable_web_page_preview": True},
        timeout=15
    )
    if resp.status_code == 200:
        return resp.json()["result"]["message_id"]
    return None


def atualizar_msg_id(noticia_id: int, msg_id: int):
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/noticias?id=eq.{noticia_id}",
        headers=HEADERS_SB, json={"telegram_msg_id": msg_id}
    )


def coletar_noticias_setor(setor: str, publicados: set) -> list:
    """Coleta candidatos de todas as fontes para um setor, sem duplicatas."""
    candidatos = []

    # 1. Fontes globais com filtro por palavras-chave
    fontes_embaralhadas = FONTES_GLOBAIS.copy()
    random.shuffle(fontes_embaralhadas)
    for fonte in fontes_embaralhadas:
        noticias = buscar_rss(fonte["url"], fonte["nome"], setor)
        for n in noticias:
            t = n["titulo"].lower().strip()
            if t not in publicados and not titulo_similar(n["titulo"], publicados):
                candidatos.append(n)

    # 2. Google News queries embaralhadas
    queries = SETORES[setor]["queries"].copy()
    random.shuffle(queries)
    for query in queries[:2]:  # máximo 2 queries do Google por setor
        noticias = buscar_google_news(query)
        for n in noticias:
            t = n["titulo"].lower().strip()
            if t not in publicados and not titulo_similar(n["titulo"], publicados):
                candidatos.append(n)

    # Embaralha tudo para misturar fontes
    random.shuffle(candidatos)
    return candidatos


def main():
    print(f"\nJORNAL MJ — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")

    empresas         = buscar_empresas()
    publicados       = buscar_titulos_recentes()
    setores_recentes = buscar_setores_recentes()

    print(f"{len(empresas)} empresas | {len(publicados)} títulos recentes | Setores recentes: {list(set(setores_recentes))}\n")

    # Contagem de empresas por setor
    contagem = {s: 0 for s in SETORES}
    for e in empresas:
        s = e.get("setor", "")
        if s in contagem:
            contagem[s] += 1

    # Penaliza setores usados recentemente
    penalizados = {s: setores_recentes.count(s) for s in SETORES}

    # Ordena com penalização + aleatoriedade
    todos = list(SETORES.keys())
    random.shuffle(todos)
    setores_ordenados = sorted(todos, key=lambda s: (penalizados.get(s, 0), -contagem.get(s, 0)))

    publicadas    = 0
    setores_usados = set()

    for setor in setores_ordenados:
        if publicadas >= 3:
            break
        if setor in setores_usados:
            continue

        print(f"Setor: {setor}")
        empresas_setor = [e for e in empresas if e.get("setor") == setor]
        candidatos = coletar_noticias_setor(setor, publicados)
        print(f"  {len(candidatos)} candidatos encontrados")

        for noticia_raw in candidatos:
            if setor in setores_usados:
                break

            print(f"  Processando [{noticia_raw['fonte']}]: {noticia_raw['titulo'][:55]}...")
            analise = processar_com_claude(noticia_raw["titulo"], setor, empresas_setor)

            if not analise:
                continue

            empresas_impacto = calcular_impacto_empresas(empresas, analise, setor)
            noticia_id = salvar_noticia(noticia_raw, analise, setor, empresas_impacto, noticia_raw["link"])

            if not noticia_id:
                continue

            msg_id = enviar_telegram(noticia_id, analise, setor, empresas_impacto, noticia_raw["titulo"], noticia_raw["fonte"])

            if msg_id:
                atualizar_msg_id(noticia_id, msg_id)
                publicadas += 1
                setores_usados.add(setor)
                publicados.add(noticia_raw["titulo"].lower().strip())
                print(f"  ✅ Enviada ({publicadas}/3) — Fonte: {noticia_raw['fonte']}")
                break

    print(f"\nCONCLUÍDO — {publicadas}/3 notícias enviadas\n")

    if publicadas == 0:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": "⚠️ *Jornal MJ* — Nenhuma notícia nova encontrada hoje.", "parse_mode": "Markdown"}
        )


if __name__ == "__main__":
    main()
