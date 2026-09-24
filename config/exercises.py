"""Small, versioned selection from the supplied Quality Life exercise PDF.

Page numbers are one-based. Instructions are transcribed, not generated.
Images are extracted illustrations, never screenshots of complete PDF pages.
"""

SOURCE = "MEMBROS INFERIORES E SUPERIORES — QUALITYLIFE AP"
START_POSITION = (
    "Ereto, com os pés paralelos e afastados na largura do quadril, mantenha as "
    "orelhas afastadas dos ombros, quadris e tornozelos alinhados e imagine um "
    "fio puxando pela cabeça como se você estivesse crescendo."
)
EXERCISES = (
    {
        "slug": "autoabraco",
        "title": "Autoabraço",
        "category": "Membros superiores",
        "summary": "Um autoabraço com o olhar em direção à região umbilical.",
        "instruction": "Realize um autoabraço e olhe em direção à região umbilical, mantendo o quadril encaixado e os joelhos levemente dobrados.",
        "position": START_POSITION,
        "page": "2",
        "image_page": 2,
    },
    {
        "slug": "abertura-peito",
        "title": "Abertura do peito",
        "category": "Membros superiores",
        "summary": "Palmas das mãos na região lombar e abertura do peito.",
        "instruction": "Coloque as palmas das mãos na região lombar baixa das costas, abrindo bem o peito e olhe para o teto.",
        "position": START_POSITION,
        "page": "2–3",
        "image_page": 3,
    },
    {
        "slug": "pescoco",
        "title": "Alongamento do pescoço",
        "category": "Membros superiores",
        "summary": "Inclinação da cabeça com a mão apoiada na bochecha.",
        "instruction": "Erga a mão direita e descanse-a contra a bochecha direita, com os dedos apontados para baixo. Incline a orelha esquerda em direção ao ombro esquerdo. Fique por 3 ciclos respiratórios e relaxe. Repita 3 vezes e faça o mesmo para o outro lado.",
        "position": START_POSITION,
        "page": "6–7",
        "image_page": 7,
    },
    {
        "slug": "punhos",
        "title": "Braços e punhos",
        "category": "Membros superiores",
        "summary": "Braços à frente, na linha dos ombros, com as mãos espalmadas.",
        "instruction": "Estenda os braços à frente do corpo, na linha dos ombros, unindo os punhos com as mãos espalmadas.",
        "position": START_POSITION,
        "page": "7–8",
        "image_page": 8,
    },
    {
        "slug": "lateral",
        "title": "Alongamento lateral",
        "category": "Membros inferiores",
        "summary": "Pernas afastadas e um braço deslizando pela lateral da perna.",
        "instruction": "Membros inferiores afastados (na largura do quadril), deslize o braço pela perna do mesmo lado e levante o braço oposto seguindo com o olhar em direção ao teto. Repita para o lado oposto.",
        "position": START_POSITION,
        "page": "12–13",
        "image_page": 13,
    },
    {
        "slug": "passo-largo",
        "title": "Passo largo e braços elevados",
        "category": "Membros inferiores",
        "summary": "Um passo largo com elevação dos braços acima da cabeça.",
        "instruction": "Dê um passo largo com o pé direito. Inspirando, eleve os dois braços, junte as palmas das mãos acima da cabeça e incline o tronco para trás olhando para o teto. Repita o movimento com os membros inferiores opostos.",
        "page": "22–23",
        "image_page": 23,
    },
    {
        "slug": "panturrilha",
        "title": "Panturrilha com apoio",
        "category": "Panturrilha",
        "summary": "Demonstração visual de alongamento da panturrilha.",
        "instruction": "Consulte a demonstração visual do material. O PDF apresenta esta posição em imagem, sem detalhar a execução, o tempo ou as repetições. Para aprender a se posicionar e realizar o alongamento, procure orientação de um profissional de fisioterapia ou educação física, conforme a orientação do material.",
        "page": "25 e 28",
        "image_page": 25,
        "visual_only": True,
    },
    {
        "slug": "sentado",
        "title": "Dedos e punhos na cadeira",
        "category": "Alongamentos sentados",
        "summary": "Extensão dos dedos e punhos, abrindo a palma da mão.",
        "instruction": "Extensão dos dedos e punhos (abrir a palma da mão). Consulte a posição na ilustração do material.",
        "page": "26",
        "image_page": 26,
    },
)
