"""Gera um vídeo tipo slideshow narrado a partir de um texto: divide o
texto em trechos, narra cada um (TTS), busca uma foto relacionada no banco
gratuito Pexels para cada trecho, e monta tudo num vídeo com efeito de
zoom lento (Ken Burns), sincronizado com o áudio de cada trecho."""
import re
import subprocess
import tempfile
from pathlib import Path

import requests
import yake
from deep_translator import GoogleTranslator

from .ffprobe_utils import probe_duration
from .tts import synthesize_speech

RESOLUTION = (1920, 1080)
FPS = 25
MAX_WORDS_PER_CHUNK = 22

_yake_extractor = yake.KeywordExtractor(lan="pt", n=2, top=3, dedupLim=0.9)

# Bancos de fotos genéricos como o Pexels não têm fotos de políticos
# brasileiros nem dos prédios/instituições reais do Brasil — as fotos que
# ele devolve pra esses temas são de tribunais/prédios de outros países,
# o que destoa bastante num vídeo sobre notícia brasileira. Por isso, pra
# cada tema, tentamos primeiro achar a foto REAL da instituição brasileira
# no Wikipedia (wiki_title) antes de cair pro termo genérico em inglês no
# Pexels (fallback_query).
_CONCEPT_MAP: list[tuple[re.Pattern, str | None, str]] = [
    (re.compile(r"supremo tribunal federal|\bstf\b", re.I), "Supremo Tribunal Federal", "courthouse justice gavel"),
    (re.compile(r"tribunal superior eleitoral|\btse\b", re.I), "Tribunal Superior Eleitoral", "courthouse justice gavel"),
    (re.compile(r"tribunal|justiça|juiz|ministro|stj|processo jurídico|julgamento", re.I), None, "courthouse justice gavel"),
    (re.compile(r"eleiç|eleitoral|candidat|voto|urna|campanha eleitoral", re.I), None, "election vote ballot"),
    (re.compile(r"congresso nacional|senado federal|câmara dos deputados", re.I), "Congresso Nacional", "government building"),
    (re.compile(r"planalto|presidência da república", re.I), "Palácio do Planalto", "government building"),
    (re.compile(r"governo|federal|presidente|ministério", re.I), None, "government building"),
    (re.compile(r"bolsa família", re.I), "Bolsa Família", "social welfare family"),
    (re.compile(r"benefício|auxílio|programa social|inss|aposentadoria", re.I), None, "social welfare family"),
    (re.compile(r"r\$|reais|bilhõ|milhõ|orçamento|contas públicas|dinheiro|valor(es)?\b|reajuste|pagamento|folha (de pagamento|salarial)|salári|inflaç|econom", re.I), None, "money finance"),
    (re.compile(r"sistema único de saúde|\bsus\b", re.I), "Sistema Único de Saúde", "hospital healthcare"),
    (re.compile(r"saúde|hospital|médic|vacina", re.I), None, "hospital healthcare"),
    (re.compile(r"educaç|escola|estudante|universidade|professor", re.I), None, "school education classroom"),
    (re.compile(r"polícia federal", re.I), "Polícia Federal (Brasil)", "police security"),
    (re.compile(r"polícia|segurança pública|crime|violência", re.I), None, "police security"),
]


def concept_match(chunk_text: str) -> tuple[str | None, str] | None:
    """Se o trecho bater com algum tema de notícia conhecido, devolve
    (título pra buscar no Wikipedia ou None, termo genérico de reserva
    pro Pexels). Retorna None se nada bater (cai pro fluxo normal de
    extração+tradução)."""
    for pattern, wiki_title, fallback_query in _CONCEPT_MAP:
        if pattern.search(chunk_text):
            return wiki_title, fallback_query
    return None


def looks_like_proper_name(phrase: str) -> bool:
    """Detecta se a frase extraída é provavelmente o nome de uma pessoa
    (ex: "André Mendonça") — buscar isso no Pexels não traz nada útil,
    então nesse caso é melhor usar um termo genérico do que o nome cru.
    Heurística: em português, substantivos comuns numa frase no meio do
    texto não vêm capitalizados — se TODAS as palavras da frase extraída
    começam maiúsculas, é sinal forte de nome próprio."""
    words = [w for w in phrase.split() if w]
    if len(words) < 2:
        return False
    return all(w[0].isupper() for w in words)


def extract_keyphrase(chunk_text: str) -> str:
    """Usa YAKE (extração estatística de palavras-chave, leve, sem baixar
    modelo) pra achar a frase-chave mais relevante do trecho em português
    — bem melhor do que filtrar stopwords manualmente, porque o YAKE
    reconhece expressões compostas como unidade ("tribunal eleitoral" e
    "tribunal militar" saem como frases distintas, não como palavras
    soltas embaralhadas)."""
    keywords = _yake_extractor.extract_keywords(chunk_text)
    if not keywords:
        return chunk_text
    # keywords vem ordenado por relevância (score menor = mais relevante)
    best_phrase, _score = min(keywords, key=lambda kw: kw[1])
    return best_phrase


def translate_to_english(text: str) -> str:
    """O catálogo/índice do Pexels responde muito melhor a termos em
    inglês. Traduz só a frase-chave já extraída (curta, então a chamada
    de tradução é rápida) preservando o contexto da expressão — ex:
    "tribunal eleitoral" vira corretamente "electoral court". Se a
    tradução falhar (ex: sem internet no momento), usa a frase-chave em
    português mesmo como fallback — ainda assim específica o bastante
    pra buscar uma foto razoável."""
    try:
        translated = GoogleTranslator(source="pt", target="en").translate(text[:100])
        return translated or text
    except Exception:  # noqa: BLE001 - tradução é best-effort
        return text


def split_into_chunks(text: str, max_words: int = MAX_WORDS_PER_CHUNK) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        words = len(sentence.split())
        if current and current_words + words > max_words:
            chunks.append(" ".join(current))
            current, current_words = [], 0
        current.append(sentence)
        current_words += words
    if current:
        chunks.append(" ".join(current))
    return chunks


def search_wikipedia_image(title: str) -> bytes | None:
    """Busca a foto real de uma pessoa/instituição na Wikipedia em
    português (Wikimedia Commons por trás) — de uso livre, e MUITO mais
    específica/correta do que um banco de fotos genérico pra política e
    instituições brasileiras. Retorna None se a página não existir ou não
    tiver imagem (ex: nome mal escrito, pessoa sem verbete)."""
    try:
        resp = requests.get(
            f"https://pt.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}",
            timeout=10,
            headers={"User-Agent": "video-editor-local/1.0 (uso pessoal)"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        image_info = data.get("originalimage") or data.get("thumbnail")
        if not image_info or not image_info.get("source"):
            return None
        image_resp = requests.get(
            image_info["source"], timeout=15, headers={"User-Agent": "video-editor-local/1.0 (uso pessoal)"}
        )
        image_resp.raise_for_status()
        return image_resp.content
    except requests.RequestException:
        return None


def search_pexels_by_query(query: str, api_key: str) -> bytes | None:
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query[:80], "per_page": 1, "orientation": "landscape"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return None
        image_resp = requests.get(photos[0]["src"]["large"], timeout=15)
        image_resp.raise_for_status()
        return image_resp.content
    except requests.RequestException:
        return None


def search_pexels_image(chunk_text: str, api_key: str) -> tuple[bytes | None, str]:
    """Retorna (bytes da imagem, descrição da fonte usada) para o log de
    diagnóstico. Ordem de prioridade:

    1. Frase-chave extraída parece nome de pessoa -> tenta achar ESSA
       pessoa no Wikipedia primeiro (ex: "André Mendonça"). Isso vem antes
       do passo 2 de propósito: um trecho tipo "o ministro André Mendonça
       decidiu..." bate tanto com "nome de pessoa" quanto com o tema
       genérico "ministro/tribunal" — e a foto da pessoa específica é
       sempre mais relevante do que o conceito genérico da instituição.
    2. Se não for nome de pessoa (ou o Wikipedia não achar essa pessoa),
       tema de notícia com instituição brasileira conhecida (STF, TSE,
       Planalto, Congresso...) -> tenta a foto REAL dela no Wikipedia.
    3. Se o Wikipedia não achar nada nos passos 1-2, ou o tema não tiver
       instituição associada, cai pro termo genérico em inglês no Pexels.
    4. Caso não seja um tema de notícia reconhecido -> frase-chave
       (YAKE) traduzida pro inglês, buscada no Pexels normalmente.
    """
    keyphrase_pt = extract_keyphrase(chunk_text)

    if looks_like_proper_name(keyphrase_pt):
        image = search_wikipedia_image(keyphrase_pt)
        if image:
            return image, f"wikipedia:{keyphrase_pt}"

    match = concept_match(chunk_text)
    if match:
        wiki_title, fallback_query = match
        if wiki_title:
            image = search_wikipedia_image(wiki_title)
            if image:
                return image, f"wikipedia:{wiki_title}"
        image = search_pexels_by_query(fallback_query, api_key)
        return image, fallback_query

    if looks_like_proper_name(keyphrase_pt):
        fallback_query = "press conference news"
        image = search_pexels_by_query(fallback_query, api_key)
        return image, fallback_query

    query = translate_to_english(keyphrase_pt)
    image = search_pexels_by_query(query, api_key)
    return image, query


def _build_segment_from_image(image_path: Path, audio_path: Path, duration: float, output_path: Path) -> None:
    w, h = RESOLUTION
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"zoompan=z='min(zoom+0.0008,1.08)':d={int(duration * FPS)}:s={w}x{h}:fps={FPS}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _build_segment_solid_color(audio_path: Path, duration: float, output_path: Path) -> None:
    """Usado quando nenhuma foto relacionada foi encontrada — fundo sólido
    em vez de travar a geração do vídeo."""
    w, h = RESOLUTION
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x1d1f27:s={w}x{h}:d={duration:.3f}",
        "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def generate_video_from_text(
    text: str,
    output_path: Path,
    pexels_api_key: str,
    tts_engine: str = "edge",
    voice_id: str | None = None,
    rate: int | None = None,
) -> None:
    chunks = split_into_chunks(text)
    if not chunks:
        raise ValueError("Texto vazio.")

    query_log_lines = []

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        segment_paths = []

        for i, chunk in enumerate(chunks):
            audio_path = tmp / f"audio_{i}.mp3"
            synthesize_speech(chunk, audio_path, engine=tts_engine, voice_id=voice_id, rate=rate)
            duration = probe_duration(audio_path)

            segment_path = tmp / f"segment_{i}.mp4"
            image_bytes, used_query = (
                search_pexels_image(chunk, pexels_api_key) if pexels_api_key else (None, "")
            )
            query_log_lines.append(f"[{i}] busca=\"{used_query}\" | trecho=\"{chunk}\"")
            if image_bytes:
                image_path = tmp / f"image_{i}.jpg"
                image_path.write_bytes(image_bytes)
                _build_segment_from_image(image_path, audio_path, duration, segment_path)
            else:
                _build_segment_solid_color(audio_path, duration, segment_path)

            segment_paths.append(segment_path)

        concat_list = tmp / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segment_paths), encoding="utf-8"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    log_path = output_path.parent / "buscas_de_imagem.log.txt"
    log_path.write_text("\n".join(query_log_lines), encoding="utf-8")
