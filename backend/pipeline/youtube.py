"""Baixa apenas o áudio de um vídeo do YouTube (via yt-dlp) para transcrição.
Não baixa o vídeo inteiro — só a faixa de áudio, bem mais rápido e leve."""
from pathlib import Path

import yt_dlp


def download_audio(url: str, output_path: Path) -> None:
    """Baixa o áudio de `url` e salva em `output_path` (com a extensão que
    o arquivo final terá — normalmente .m4a ou .mp3, decidido pelo yt-dlp)."""
    output_template = str(output_path.with_suffix("")) + ".%(ext)s"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_path = Path(ydl.prepare_filename(info))

    if downloaded_path != output_path:
        downloaded_path.replace(output_path)
