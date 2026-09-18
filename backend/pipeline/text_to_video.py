"""Gera um vídeo narrado a partir de um texto: divide o texto em trechos
curtos, narra cada um (TTS), e busca uma mídia relacionada pra cada
trecho — nessa ordem de qualidade: foto real (Wikipedia) > vídeo de banco
(Pexels) > foto de banco (Pexels) > fundo sólido. Monta tudo com transição
suave (fade) entre os cortes, sincronizado com o áudio de cada trecho."""
import re
import subprocess
import tempfile
from pathlib import Path

import requests
import yake
from deep_translator import GoogleTranslator

from .ffprobe_utils import has_audio_stream, probe_duration
from .subtitles import burn_karaoke_subtitles, burn_subtitles, build_karaoke_ass, write_srt
from .transcribe import Segment
from .tts import WordTiming, synthesize_speech, synthesize_speech_edge_with_words

HORIZONTAL_RESOLUTION = (1920, 1080)
VERTICAL_RESOLUTION = (1080, 1920)
FPS = 25
FADE_SECONDS = 0.35
# Usado pra decidir se um arquivo enviado manualmente pelo usuário
# (foto ou vídeo) deve virar um segmento animado (zoompan) ou um clipe
# de vídeo de verdade, baseado só na extensão.
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
# Trechos menores = mais cortes de imagem/vídeo no resultado final, no
# ritmo de vídeo de notícia/redes sociais (uma mídia nova a cada poucos
# segundos, não uma a cada frase longa).
MAX_WORDS_PER_CHUNK = 8

# Consultas genéricas de "notícia" pra usar como último recurso antes do
# fundo sólido, girando entre elas por índice do trecho — evita que um
# vídeo inteiro vire uma sequência de fundos sólidos só porque o trecho
# não tinha nenhuma palavra-chave "buscável" (ex: conectivos, transições).
_GENERIC_NEWS_QUERIES = [
    "news studio broadcast",
    "newspaper press",
    "city skyline brazil",
    "press conference microphone",
    "office meeting discussion",
    "crowd people street",
]
# Quantos candidatos pedir por busca — usado pra poder pular os que já
# foram usados noutro trecho do mesmo vídeo (evita repetir mídia).
CANDIDATES_PER_SEARCH = 12

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
    phrases = extract_keyphrases(chunk_text)
    return phrases[0] if phrases else chunk_text


def extract_keyphrases(chunk_text: str) -> list[str]:
    """Como `extract_keyphrase`, mas devolve todas as frases candidatas
    (ordenadas da mais pra menos relevante) em vez de só a melhor — usado
    pra tentar buscas alternativas quando a primeira frase-chave não acha
    nenhuma mídia."""
    keywords = _yake_extractor.extract_keywords(chunk_text)
    if not keywords:
        return []
    ordered = sorted(keywords, key=lambda kw: kw[1])
    return [phrase for phrase, _score in ordered]


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


def search_pexels_photo(
    query: str, api_key: str, used_ids: set[str], orientation: str = "landscape"
) -> bytes | None:
    """Busca uma foto no Pexels, pulando qualquer resultado já usado
    noutro trecho do mesmo vídeo (evita repetir a mesma imagem).
    `orientation`: "landscape" (vídeo horizontal) ou "portrait" (vertical)
    — pede direto ao Pexels resultados nesse formato, em vez de cortar
    depois uma foto horizontal pra caber num vídeo vertical (ou vice
    versa), o que geralmente perde o enquadramento."""
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query[:80], "per_page": CANDIDATES_PER_SEARCH, "orientation": orientation},
            timeout=15,
        )
        resp.raise_for_status()
        for photo in resp.json().get("photos", []):
            media_id = f"photo:{photo.get('id')}"
            if media_id in used_ids:
                continue
            image_resp = requests.get(photo["src"]["large"], timeout=15)
            image_resp.raise_for_status()
            used_ids.add(media_id)
            return image_resp.content
        return None
    except requests.RequestException:
        return None


def search_pexels_video(
    query: str, api_key: str, used_ids: set[str], orientation: str = "landscape", target_width: int = 1920
) -> bytes | None:
    """Busca um vídeo curto no Pexels (b-roll real, com movimento) — mais
    dinâmico e profissional do que zoom numa foto parada. Pula vídeos já
    usados noutro trecho. `orientation`/`target_width`: mesmo motivo do
    `search_pexels_photo` — pede o formato certo (horizontal/vertical) em
    vez de espremer depois."""
    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={"query": query[:80], "per_page": CANDIDATES_PER_SEARCH, "orientation": orientation},
            timeout=15,
        )
        resp.raise_for_status()
        for video in resp.json().get("videos", []):
            media_id = f"video:{video.get('id')}"
            if media_id in used_ids:
                continue
            files = [f for f in video.get("video_files", []) if f.get("width") and f.get("link")]
            if not files:
                continue
            files.sort(key=lambda f: abs(f["width"] - target_width))
            video_resp = requests.get(files[0]["link"], timeout=30)
            video_resp.raise_for_status()
            used_ids.add(media_id)
            return video_resp.content
        return None
    except requests.RequestException:
        return None


def _try_pexels(
    query: str, api_key: str, used_ids: set[str], orientation: str, target_width: int
) -> tuple[str, bytes, str] | None:
    """Tenta um vídeo e, se não achar, uma foto no Pexels pra essa query.
    Retorna None se nenhum dos dois achar nada (query ruim ou já toda
    usada), pra o chamador poder tentar outra query em vez de desistir."""
    video = search_pexels_video(query, api_key, used_ids, orientation=orientation, target_width=target_width)
    if video:
        return "video", video, f"pexels-video:{query}"
    photo = search_pexels_photo(query, api_key, used_ids, orientation=orientation)
    if photo:
        return "photo", photo, f"pexels-photo:{query}"
    return None


def resolve_media_for_chunk(
    chunk_text: str,
    api_key: str,
    used_ids: set[str],
    chunk_index: int = 0,
    resolution: tuple[int, int] = HORIZONTAL_RESOLUTION,
) -> tuple[str, bytes | None, str]:
    """Decide e busca a melhor mídia pro trecho. Retorna (tipo, bytes,
    descrição da fonte pro log de diagnóstico), onde tipo é "photo",
    "video" ou "color" (fundo sólido, usado só quando TODAS as tentativas
    abaixo falharem).

    Ordem de prioridade:
    1. Frase-chave extraída parece nome de pessoa -> tenta achar ESSA
       pessoa no Wikipedia primeiro (ex: "André Mendonça"). Isso vem antes
       do passo 2 de propósito: um trecho tipo "o ministro André Mendonça
       decidiu..." bate tanto com "nome de pessoa" quanto com o tema
       genérico "ministro/tribunal" — e a foto da pessoa específica é
       sempre mais relevante do que o conceito genérico da instituição.
    2. Tema de notícia com instituição brasileira conhecida (STF, TSE,
       Planalto, Congresso...) -> tenta a foto REAL dela no Wikipedia.
    3. Define a query de busca (genérica do tema, ou frase-chave
       traduzida) e tenta um VÍDEO no Pexels primeiro (mais dinâmico),
       depois uma FOTO no Pexels.
    4. Se a query principal não achar nada, tenta as outras frases-chave
       candidatas do YAKE (nem sempre a "melhor" segundo o score é a que
       tem cobertura no banco de imagens).
    5. Se ainda assim nada for encontrado, tenta uma query genérica de
       "notícia" (girando entre algumas opções) em vez de ir direto pro
       fundo sólido — um trecho sem palavra-chave específica (conectivos,
       transições) não precisa terminar sem nenhuma imagem.
    6. Só cai pro fundo sólido se NENHUMA busca acima trouxe resultado
       (banco sem internet, chave inválida, ou tudo já usado no vídeo).
    """
    keyphrases_pt = extract_keyphrases(chunk_text)
    keyphrase_pt = keyphrases_pt[0] if keyphrases_pt else chunk_text

    if looks_like_proper_name(keyphrase_pt):
        image = search_wikipedia_image(keyphrase_pt)
        if image:
            return "photo", image, f"wikipedia:{keyphrase_pt}"

    match = concept_match(chunk_text)
    if match:
        wiki_title, fallback_query = match
        if wiki_title:
            image = search_wikipedia_image(wiki_title)
            if image:
                return "photo", image, f"wikipedia:{wiki_title}"
        query = fallback_query
    elif looks_like_proper_name(keyphrase_pt):
        query = "press conference news"
    else:
        query = translate_to_english(keyphrase_pt)

    if api_key:
        width, height = resolution
        orientation = "portrait" if height > width else "landscape"

        found = _try_pexels(query, api_key, used_ids, orientation, width)
        if found:
            return found

        # Primeira query não achou nada: tenta as outras frases-chave
        # candidatas antes de desistir (traduzidas, evitando repetir a
        # primeira query já tentada).
        for alt_phrase in keyphrases_pt[1:3]:
            alt_query = translate_to_english(alt_phrase)
            if alt_query.strip().lower() == query.strip().lower():
                continue
            found = _try_pexels(alt_query, api_key, used_ids, orientation, width)
            if found:
                return found

        # Ainda nada: usa uma query genérica de notícia em vez de fundo
        # sólido, girando pela lista pra variar entre trechos.
        generic_query = _GENERIC_NEWS_QUERIES[chunk_index % len(_GENERIC_NEWS_QUERIES)]
        found = _try_pexels(generic_query, api_key, used_ids, orientation, width)
        if found:
            return found

    return "color", None, query


def _fade_filter(duration: float) -> str:
    fade = min(FADE_SECONDS, duration / 2)
    fade_out_start = max(0.0, duration - fade)
    return f"fade=t=in:st=0:d={fade:.3f},fade=t=out:st={fade_out_start:.3f}:d={fade:.3f}"


def _build_segment_from_image(
    image_path: Path, audio_path: Path, duration: float, output_path: Path,
    resolution: tuple[int, int] = HORIZONTAL_RESOLUTION,
) -> None:
    w, h = resolution
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"zoompan=z='min(zoom+0.0008,1.08)':d={int(duration * FPS)}:s={w}x{h}:fps={FPS},"
        f"{_fade_filter(duration)}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _build_segment_from_video(
    video_path: Path, audio_path: Path, duration: float, output_path: Path,
    resolution: tuple[int, int] = HORIZONTAL_RESOLUTION,
) -> None:
    w, h = resolution
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},{_fade_filter(duration)}"
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(video_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _build_segment_solid_color(
    audio_path: Path, duration: float, output_path: Path,
    resolution: tuple[int, int] = HORIZONTAL_RESOLUTION,
) -> None:
    """Usado quando nenhuma mídia relacionada foi encontrada — fundo
    sólido em vez de travar a geração do vídeo."""
    w, h = resolution
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x1d1f27:s={w}x{h}:d={duration:.3f}",
        "-i", str(audio_path),
        "-vf", _fade_filter(duration),
        "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def build_bumper_from_video(
    video_path: Path, output_path: Path, resolution: tuple[int, int] = HORIZONTAL_RESOLUTION
) -> None:
    """Converte um vídeo de abertura/encerramento próprio (ex: você
    aparecendo) pro mesmo tamanho/codec/taxa de quadros dos outros
    trechos, pra poder concatenar tudo sem erro no final. Letterbox em vez
    de cortar (não faz sentido cortar pedaços de um vídeo que o usuário
    gravou de propósito). Se o clipe não tiver áudio, adiciona uma trilha
    muda — os outros trechos sempre têm áudio (a narração), e misturar
    clipes com/sem áudio na mesma concatenação quebra a sincronia.

    IMPORTANTE: forçar `-r {FPS}` aqui é essencial — a concatenação final
    usa `-c copy` (só remuxa, sem recodificar), que exige que TODOS os
    arquivos tenham a mesma taxa de quadros/timebase. Sem isso, um vídeo
    próprio com fps diferente (ex: 30 ou 60 do celular) faz o resultado
    final "travar"/parar de tocar assim que esse trecho termina, mesmo
    com os dados dos trechos seguintes intactos no arquivo."""
    w, h = resolution
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x1d1f27,setsar=1"

    if has_audio_stream(video_path):
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", vf,
            "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", vf,
            "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-shortest",
            str(output_path),
        ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


_WEBCAM_OVERLAY_POSITIONS = {
    "bottom-right": "x=W-w-{margin}:y=H-h-{margin}",
    "bottom-left": "x={margin}:y=H-h-{margin}",
    "top-right": "x=W-w-{margin}:y={margin}",
    "top-left": "x={margin}:y={margin}",
}


def apply_webcam_overlay(
    base_video_path: Path,
    webcam_video_path: Path,
    output_path: Path,
    resolution: tuple[int, int] = HORIZONTAL_RESOLUTION,
    position: str = "bottom-right",
    size_ratio: float = 0.28,
) -> None:
    """Sobrepõe um vídeo próprio (sem narração — ex: o usuário reagindo em
    silêncio) num canto do vídeo, durante todo o conteúdo. Se o clipe da
    webcam for mais curto que o conteúdo, repete em loop; se for mais
    longo, corta no fim do conteúdo (`shortest=1`). O áudio do vídeo base
    (a narração) é preservado sem alteração — o áudio da webcam, se
    houver, é descartado."""
    w, _h = resolution
    overlay_width = round(w * size_ratio)
    margin = round(w * 0.02)
    pos_template = _WEBCAM_OVERLAY_POSITIONS.get(position, _WEBCAM_OVERLAY_POSITIONS["bottom-right"])
    overlay_pos = pos_template.format(margin=margin)

    filter_complex = (
        f"[1:v]scale={overlay_width}:-2,setsar=1[wc];"
        f"[0:v][wc]overlay={overlay_pos}:shortest=1[v]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(base_video_path),
        "-stream_loop", "-1", "-i", str(webcam_video_path),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def build_cover_thumbnail(
    image_path: Path, output_path: Path, resolution: tuple[int, int] = HORIZONTAL_RESOLUTION
) -> None:
    """Gera a imagem de capa do vídeo a partir da foto escolhida pelo
    usuário, ajustada pro tamanho/proporção do vídeo (letterbox, sem
    cortar nada da foto original — diferente dos segmentos do vídeo, aqui
    o usuário escolheu essa imagem de propósito pra representar o vídeo
    todo, então não faz sentido cortar pedaços dela)."""
    w, h = resolution
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x1d1f27"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(image_path),
        "-vf", vf,
        "-frames:v", "1",
        "-update", "1",
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
    manual_image_map: dict[int, Path] | None = None,
    subtitles_enabled: bool = False,
    subtitle_font_size: int | None = None,
    subtitle_position: str = "bottom",
    subtitle_style: str = "static",
    orientation: str = "horizontal",
    intro_video_path: Path | None = None,
    outro_video_path: Path | None = None,
    webcam_video_path: Path | None = None,
    webcam_position: str = "bottom-right",
) -> None:
    """`manual_image_map`: mapa opcional {índice do trecho: caminho do
    arquivo} para os trechos onde o usuário escolheu manualmente uma foto
    OU um vídeo (porque a busca automática às vezes traz mídia
    artificial/genérica demais pro tema) — o tipo é decidido pela
    extensão do arquivo. Um trecho sem entrada no mapa cai na busca
    automática normal — dá pra misturar os dois num mesmo vídeo, em vez
    de ser tudo automático ou tudo manual.

    `subtitles_enabled`: queima o próprio texto da narração como legenda,
    sincronizado com a duração real de cada trecho narrado — não precisa
    transcrever de novo (já sabemos exatamente o texto de cada trecho).

    `subtitle_style`: "static" (legenda fixa, padrão) ou "karaoke"
    (palavra ganha destaque de cor conforme é falada, estilo
    CapCut/Captions.app). O estilo karaokê só funciona com o motor de
    voz Edge (só ele fornece o tempo exato de cada palavra) — com o
    motor local, cai automaticamente pra "static".

    `orientation`: "horizontal" (1920x1080, YouTube/paisagem) ou
    "vertical" (1080x1920, Reels/Shorts/TikTok) — também usado pra pedir
    fotos/vídeos já no formato certo ao Pexels.

    `intro_video_path`/`outro_video_path`: vídeos próprios (ex: o usuário
    aparecendo) pra colar no início/fim do vídeo gerado — não recebem
    legenda automática nem a camada de webcam (são conteúdo próprio, já
    pronto).

    `webcam_video_path`: vídeo próprio SEM narração (ex: o usuário
    reagindo/acompanhando em silêncio) pra sobrepor num canto da tela
    durante o conteúdo narrado (não durante abertura/encerramento) — dá
    uma camada humana/autoral ao vídeo, importante pra não parecer 100%
    automatizado. Repete em loop se for mais curto que o conteúdo."""
    chunks = split_into_chunks(text)
    if not chunks:
        raise ValueError("Texto vazio.")

    resolution = VERTICAL_RESOLUTION if orientation == "vertical" else HORIZONTAL_RESOLUTION

    # Karaokê exige o tempo exato de cada palavra, que só o motor Edge
    # fornece — com o motor local, cai pro estilo estático automaticamente
    # em vez de gerar uma legenda sem efeito nenhum (ou dar erro).
    karaoke_active = subtitles_enabled and subtitle_style == "karaoke" and tts_engine == "edge"

    manual_image_map = manual_image_map or {}
    query_log_lines = []
    used_media_ids: set[str] = set()
    subtitle_segments: list[Segment] = []
    karaoke_chunks: list[list[WordTiming]] = []
    elapsed = 0.0

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        content_segment_paths = []

        for i, chunk in enumerate(chunks):
            audio_path = tmp / f"audio_{i}.mp3"
            if karaoke_active:
                words = synthesize_speech_edge_with_words(chunk, audio_path, voice_id=voice_id, rate=rate)
                karaoke_chunks.append(
                    [WordTiming(text=w.text, start=elapsed + w.start, end=elapsed + w.end) for w in words]
                )
            else:
                synthesize_speech(chunk, audio_path, engine=tts_engine, voice_id=voice_id, rate=rate)
            duration = probe_duration(audio_path)
            subtitle_segments.append(Segment(start=elapsed, end=elapsed + duration, text=chunk))
            elapsed += duration

            segment_path = tmp / f"segment_{i}.mp4"

            manual_path = manual_image_map.get(i)
            if manual_path:
                # O usuário já escolheu um arquivo específico (foto OU
                # vídeo) — usa direto do disco, sem buscar nada. O tipo é
                # decidido pela extensão do arquivo enviado.
                media_type = "video" if manual_path.suffix.lower() in _VIDEO_EXTENSIONS else "photo"
                source_desc = f"manual:{manual_path.name}"
                query_log_lines.append(f"[{i}] fonte=\"{source_desc}\" ({media_type}) | trecho=\"{chunk}\"")
                if media_type == "video":
                    _build_segment_from_video(manual_path, audio_path, duration, segment_path, resolution=resolution)
                else:
                    _build_segment_from_image(manual_path, audio_path, duration, segment_path, resolution=resolution)
            else:
                media_type, media_bytes, source_desc = resolve_media_for_chunk(
                    chunk, pexels_api_key, used_media_ids, chunk_index=i, resolution=resolution
                )
                query_log_lines.append(f"[{i}] fonte=\"{source_desc}\" ({media_type}) | trecho=\"{chunk}\"")

                if media_type == "video" and media_bytes:
                    video_path = tmp / f"media_{i}.mp4"
                    video_path.write_bytes(media_bytes)
                    _build_segment_from_video(video_path, audio_path, duration, segment_path, resolution=resolution)
                elif media_type == "photo" and media_bytes:
                    image_path = tmp / f"media_{i}.jpg"
                    image_path.write_bytes(media_bytes)
                    _build_segment_from_image(image_path, audio_path, duration, segment_path, resolution=resolution)
                else:
                    _build_segment_solid_color(audio_path, duration, segment_path, resolution=resolution)

            content_segment_paths.append(segment_path)

        # Concatena só o conteúdo narrado (sem abertura/encerramento) —
        # legendas e a camada de webcam se aplicam só a essa parte.
        content_concat = tmp / "content_concat.mp4"
        content_list = tmp / "content_concat.txt"
        content_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in content_segment_paths), encoding="utf-8"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(content_list), "-c", "copy", str(content_concat)],
            check=True, capture_output=True, text=True,
        )
        content_current = content_concat

        if karaoke_active:
            ass_path = tmp / "legendas.ass"
            build_karaoke_ass(
                karaoke_chunks, ass_path, resolution,
                font_size=subtitle_font_size, position=subtitle_position,
            )
            content_with_subs = tmp / "content_with_subs.mp4"
            burn_karaoke_subtitles(content_current, ass_path, content_with_subs)
            content_current = content_with_subs
        elif subtitles_enabled:
            srt_path = tmp / "legendas.srt"
            write_srt(subtitle_segments, srt_path)
            content_with_subs = tmp / "content_with_subs.mp4"
            burn_subtitles(
                content_current, srt_path, content_with_subs,
                font_size=subtitle_font_size, position=subtitle_position,
            )
            content_current = content_with_subs

        if webcam_video_path:
            content_with_webcam = tmp / "content_with_webcam.mp4"
            apply_webcam_overlay(
                content_current, webcam_video_path, content_with_webcam,
                resolution=resolution, position=webcam_position,
            )
            content_current = content_with_webcam

        final_segment_paths = []
        if intro_video_path:
            intro_segment_path = tmp / "intro.mp4"
            build_bumper_from_video(intro_video_path, intro_segment_path, resolution=resolution)
            final_segment_paths.append(intro_segment_path)

        final_segment_paths.append(content_current)

        if outro_video_path:
            outro_segment_path = tmp / "outro.mp4"
            build_bumper_from_video(outro_video_path, outro_segment_path, resolution=resolution)
            final_segment_paths.append(outro_segment_path)

        # -movflags +faststart move o índice (moov atom) pro início do
        # arquivo — sem isso, o navegador só consegue tocar o vídeo depois
        # de baixar o arquivo inteiro (ou só toca o primeiro trecho antes
        # disso), porque o índice fica no final. Sempre remuxa por ffmpeg
        # (mesmo sem abertura/encerramento) pra garantir isso.
        if len(final_segment_paths) == 1:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(content_current), "-c", "copy", "-movflags", "+faststart", str(output_path)],
                check=True, capture_output=True, text=True,
            )
        else:
            final_list = tmp / "final_concat.txt"
            final_list.write_text(
                "\n".join(f"file '{p.as_posix()}'" for p in final_segment_paths), encoding="utf-8"
            )
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(final_list),
                 "-c", "copy", "-movflags", "+faststart", str(output_path)],
                check=True, capture_output=True, text=True,
            )

    log_path = output_path.parent / "buscas_de_imagem.log.txt"
    log_path.write_text("\n".join(query_log_lines), encoding="utf-8")
