# Vídeos de bem-estar — procedência

Vídeos ilustrativos gerados por IA (Higgsfield, MiniMax H3) a partir das
instruções do material MEMBROS INFERIORES E SUPERIORES — QUALITYLIFE AP;
pessoa genérica, não a do material; exercícios PENDENTES de revisão por
profissional de educação física da Quality Life.

| Arquivo | Uso |
|---|---|
| ex-pescoco.mp4 | Alongamento do pescoço |
| ex-abertura-peito.mp4 | Abertura do peito |
| ex-punhos.mp4 | Braços e punhos |
| ex-lateral.mp4 | Alongamento lateral |
| ex-passo-largo.mp4 | Passo largo e braços elevados |
| ex-sentado.mp4 | Dedos e punhos na cadeira |
| ex-inclinacao-frente.mp4 | Inclinação do tronco à frente (começa e termina em pé) |
| med-foco.mp4 | Meditação: Respiração para foco |
| med-ansiedade.mp4 | Meditação: Reduzir ansiedade |
| med-relaxamento.mp4 | Meditação: Relaxamento profundo e fundo do Relaxamento |

Não existe vídeo de Autoabraço nem de Panturrilha: essas telas mostram a imagem
do material.

Formato: 5 s, 832×480, H.264, feitos para tocar em loop, `muted` e
`playsinline`. A trilha de som ambiente gerada pela IA foi removida por remux
(`ffmpeg -c:v copy -an -movflags +faststart`, sem recompressão do vídeo). Cada
`.webp` é o primeiro quadro do vídeo de mesmo nome (poster). Para trocar um
vídeo, mantenha o nome, o limite de 3 MB e gere o poster de novo:
`ffmpeg -i x.mp4 -frames:v 1 -c:v libwebp -quality 80 x.webp`.
