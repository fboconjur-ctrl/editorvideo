# Video Editor Local

Editor de vídeo automático que roda **100% na sua máquina**, sem assinaturas
e sem chamadas pagas a APIs de IA. Feito para substituir tarefas repetitivas
do CapCut/Captions.app:

- Corte automático de silêncios e pausas mortas
- Legendas automáticas (transcrição local via Whisper)
- Correção automática de cor e normalização de áudio
- Remoção de fundo

## Como funciona

1. **Backend** (Python/FastAPI): recebe o vídeo, roda um pipeline de
   processamento (ffmpeg + auto-editor + faster-whisper) e disponibiliza o
   resultado para download.
2. **Frontend** (HTML/JS puro): interface simples para subir o vídeo,
   escolher quais etapas aplicar, acompanhar o progresso e baixar o
   resultado.

Nenhum dado sai da sua máquina — tudo roda localmente.

## Requisitos

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) instalado e disponível no PATH
- GPU é opcional (acelera a transcrição, mas funciona em CPU)

## Rodando localmente

### Windows (mais fácil)

1. Instale [Python](https://www.python.org/downloads/) (marque "Add Python to PATH" no instalador) e o [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (descompacte e adicione a pasta `bin` ao PATH do Windows).
2. Dê **duplo clique** em `setup_e_rodar.bat` — ele cria o ambiente, instala tudo e sobe o servidor. Deixe a janela aberta.
3. Dê duplo clique em `abrir_editor.bat` (ou abra `frontend/index.html` manualmente) para abrir a interface no navegador.

### Mac/Linux (ou manual no Windows)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Depois abra `frontend/index.html` no navegador (ou sirva com qualquer
servidor estático) — a interface já aponta para `http://localhost:8000`.

## Editor manual (timeline)

Além da edição automática, `frontend/timeline.html` oferece uma timeline
manual: sobe o vídeo, mostra os blocos na linha do tempo, e permite:

- **Dividir** o bloco selecionado no ponto atual do player.
- **Excluir** um trecho.
- **Reordenar** blocos (mover pra esquerda/direita).
- **Reproduzir a edição** (toca só os trechos mantidos, na ordem escolhida).
- **Exportar** — renderiza a lista de cortes no servidor (ffmpeg
  trim+concat) e disponibiliza o vídeo final para download.

Backend correspondente: `POST /api/uploads` (sobe o vídeo sem processar) e
`POST /api/render` (renderiza a lista de cortes).

## Pipeline automático (v1)

1. Upload do vídeo.
2. Corte automático de silêncios/pausas (via `auto-editor`).
3. Correção automática de cor e normalização de áudio (via ffmpeg `normalize`/`eq`/`loudnorm`).
4. Transcrição local do áudio (via `faster-whisper`).
5. Geração de legendas `.srt`, com opção de "queimar" (burn-in) no vídeo.
6. Download do vídeo final + arquivo de legenda.

Remoção de fundo (opcional): usa `rembg` (modelo `u2net`) processando o
vídeo frame a frame. Pode gerar um `.webm` com fundo transparente ou
compor sobre uma cor sólida (ex: green screen virtual). O primeiro uso
baixa o modelo automaticamente (~170MB); depois disso funciona 100%
offline.

Reframe vertical (opcional): usa `mediapipe` para detectar rostos numa
amostra de frames, calcula o centro médio e recorta o vídeo em 9:16
centralizado nesse ponto (recorte estático, não acompanha movimento
frame a frame). Bom para transformar vídeos horizontais em Reels/Shorts/TikTok.

Remoção de repetições/vícios de fala (opcional): transcreve o vídeo com
timestamp por palavra (Whisper), detecta repetições consecutivas
("eu eu eu vou") e vícios de fala comuns ("né", "tipo", "uhm"...) e corta
esses trechos do vídeo. Lista de vícios é conservadora de propósito, para
evitar cortar palavras ambíguas.

Estabilização (opcional): usa o filtro `vidstab` do ffmpeg (duas passadas)
para reduzir tremidos de câmera. Requer ffmpeg compilado com
`--enable-libvidstab` (a maioria dos builds recentes já vem assim; se o
filtro não existir, o passo falha e é só desmarcar essa opção).

Aumento de resolução (opcional): reamostragem Lanczos + nitidez via
ffmpeg. **Não é super-resolução por IA** (não inventa detalhe como
Real-ESRGAN) — deixa o vídeo maior e mais nítido de forma instantânea e
sem depender de GPU/modelo. Uma versão com IA real pode ser adicionada
depois integrando Real-ESRGAN, mas isso exige baixar um modelo maior e
idealmente rodar em GPU.

## Roadmap

- Interpolação de frames / slow-motion suave (ex: integrar RIFE)
- Upscale com super-resolução real (Real-ESRGAN), como alternativa mais pesada ao upscale atual
