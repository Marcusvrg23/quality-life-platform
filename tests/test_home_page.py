"""Public landing page at "/": content, pillars from the database, auth state."""

import re
from html import unescape
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from assessments.models import Pillar
from config.views import DEFAULT_PILLAR_ICON, PILLAR_ICONS, pillar_icon

PILLAR_NAMES = [
    "Saúde Física",
    "Comportamento Preventivo",
    "Atividade Física",
    "Alimentação e Hidratação",
    "Relacionamentos",
    "Saúde Mental e Emocional",
    "Ergonomia e Ambiente de Trabalho",
    "Sono e Recuperação",
    "Equilíbrio Vida × Trabalho",
]

# Copy required by the landing brief (docs/specs/07-landing-dark.md).
REQUIRED_TEXT = [
    "Vida em movimento",
    "Bem-estar real para uma vida extraordinária.",
    (
        "Cuidado, movimento e presença em uma experiência completa para você viver "
        "mais e melhor, todos os dias."
    ),
    "Conheça a plataforma",
    "9 pilares",
    "da qualidade de vida",
    "3 momentos",
    "do seu dia",
    "100% confidencial",
    "seu resultado é só seu",
    "Role para explorar",
    "Nossa essência",
    "Mais presença em cada fase da sua vida.",
    (
        "A Quality Life existe para tornar o bem-estar parte da sua rotina, com "
        "experiências que integram corpo, mente e propósito."
    ),
    "Equilíbrio",
    "Presença",
    "Bem-estar em todos os momentos",
    "Ao começar o dia",
    "Durante o dia",
    "Ao encerrar o dia",
    "Uma vida melhor em todas as áreas",
    "Um caminho simples",
    "Receba o convite da sua empresa",
    "Faça sua avaliação",
    "Veja seu mapa e sua prioridade",
    "Pratique no seu ritmo",
    "Para empresas",
    "5 ou mais avaliações",
    "Acesso da empresa",
    "Sua melhor versão começa agora.",
    "Movimento",
    "Bem-estar hoje. Mais vida sempre.",
    "Política de privacidade",
    "Termos de uso",
]

# Invented metrics and testimonials from the visual references.
FORBIDDEN_TEXT = ["50 mil", "10K", "95%", "96%", "4,8", "4.8", "Depoimentos"]

LANDING_IMAGES = {
    "hero-bg": (1344, 752),
    "hero-pessoa": (1344, 752),
    "hero-mobile-bg": (752, 1344),
    "hero-mobile-pessoa": (752, 1344),
    "cta-bg": (1344, 752),
    "cta-pessoa": (1344, 752),
    "hero": (1344, 752),
    "hero-mobile": (752, 1344),
    "cta": (1344, 752),
    "momento-comecar": (1168, 880),
    "momento-durante": (1168, 880),
    "momento-encerrar": (1168, 880),
    "jornada": (1168, 880),
}


def visible_text(html):
    """Collapse the rendered HTML to the text a reader sees."""
    html = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", html, flags=re.DOTALL)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def webp_info(path):
    """Return (width, height, has_alpha) from a WebP file header."""
    data = Path(path).read_bytes()
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP", path
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height, bool(data[20] & 0x10)
    if chunk == b"VP8 ":
        assert data[23:26] == b"\x9d\x01\x2a", path
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height, False
    raise AssertionError(f"Unexpected WebP chunk {chunk!r} in {path}")


def element_block(html, pattern):
    match = re.search(pattern, html, flags=re.DOTALL)
    assert match, pattern
    return match.group(0)


class HomePageTests(TestCase):
    def get_home(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        return response, response.content.decode()

    def test_home_renders_required_copy(self):
        response, body = self.get_home()
        text = visible_text(body).casefold()

        self.assertTemplateUsed(response, "home.html")
        for phrase in REQUIRED_TEXT:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.casefold(), text)
        self.assertEqual(body.count("<h1"), 1)

    def test_home_has_no_invented_metrics_or_testimonials(self):
        _, body = self.get_home()
        text = visible_text(body)

        for phrase in FORBIDDEN_TEXT:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, text)
        for absent in ("newsletter", "instagram", "youtube", "linkedin", "planos"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, body.casefold())

    def test_section_anchors_exist_for_navigation(self):
        _, body = self.get_home()

        for anchor in ("experiencias", "como-funciona", "empresas"):
            with self.subTest(anchor=anchor):
                self.assertIn(f'id="{anchor}"', body)
                self.assertIn(f'href="#{anchor}"', body)

    def test_login_button_lives_in_header_outside_the_menu(self):
        _, body = self.get_home()
        header = element_block(body, r"<header\b.*?</header>")
        menu = element_block(header, r'<nav\b[^>]*id="ql-menu".*?</nav>')

        self.assertRegex(
            header,
            rf'<a class="[^"]*ql-header__cta[^"]*" href="{reverse("login")}">Entrar</a>',
        )
        self.assertNotIn("ql-header__cta", menu)
        for label in ("Experiências", "Como funciona", "Para empresas"):
            with self.subTest(label=label):
                self.assertIn(label, menu)

    def test_menu_toggle_is_accessible(self):
        _, body = self.get_home()
        toggle = element_block(
            body, r'<button\b[^>]*class="ql-menu-toggle".*?</button>'
        )

        self.assertIn('aria-expanded="false"', toggle)
        self.assertIn('aria-controls="ql-menu"', toggle)
        self.assertRegex(toggle, r'aria-label="[^"]+"')
        self.assertIn('type="button"', toggle)

    def test_home_links_to_login_privacy_terms_and_sales(self):
        response, _ = self.get_home()

        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertContains(response, f'href="{reverse("privacy")}"')
        self.assertContains(response, f'href="{reverse("terms")}"')
        self.assertContains(response, 'href="mailto:[EMAIL-COMERCIAL]"', count=3)
        self.assertNotContains(response, "Abrir o app")

    def test_moment_cards_send_visitors_to_login_with_next_lessons(self):
        _, body = self.get_home()
        cards = re.findall(r'<a class="ql-moment[^"]*" href="([^"]+)"', body)

        expected = f"{reverse('login')}?next={reverse('lessons')}"
        self.assertEqual(cards, [expected] * 3)

    def test_home_loads_local_assets_and_deferred_scripts(self):
        _, body = self.get_home()

        for path in (
            "quality_life/brand.css",
            "quality_life/home.css",
            "quality_life/home.js",
            "quality_life/ambient.js",
            "quality_life/vendor/gsap-3.13.0.min.js",
            "quality_life/vendor/ScrollTrigger-3.13.0.min.js",
            "quality_life/images/brand/quality-life-logo-ring-192.png",
            "quality_life/fonts/cormorant-garamond-latin-500.woff2",
            "quality_life/fonts/cormorant-garamond-latin-600.woff2",
            "quality_life/fonts/OFL-CormorantGaramond.txt",
            "quality_life/fonts/figtree-latin-400.woff2",
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path))
        for script in (
            "gsap-3.13.0.min.js",
            "ScrollTrigger-3.13.0.min.js",
            "ambient.js",
            "home.js",
        ):
            with self.subTest(script=script):
                self.assertRegex(body, rf'<script defer src="[^"]*{script}">')
        self.assertNotIn("fonts.googleapis.com", body)
        self.assertNotIn("cdn.", body)

    def test_scene_layers_are_ordered_and_decorative(self):
        _, body = self.get_home()

        for scene in ("hero", "cta"):
            block = element_block(
                body, rf'<div class="ql-scene ql-scene--{scene}".*?<!-- /scene -->'
            )
            with self.subTest(scene=scene):
                layers = re.findall(r'class="ql-layer ql-layer--(\w+)"', block)
                self.assertEqual(layers, ["bg", "back", "person", "front"])
                self.assertIn(f"{scene}-bg.webp", block)
                self.assertIn(f"{scene}-pessoa.webp", block)
                self.assertIn('class="ql-scene__layers" aria-hidden="true"', block)
                canvases = re.findall(r'<canvas[^>]*aria-hidden="true"', block)
                self.assertEqual(len(canvases), 2)
                static = element_block(
                    block, r'<picture class="ql-scene__static".*?</picture>'
                )
                self.assertIn(f"{scene}.webp", static)

        hero = element_block(
            body, r'<div class="ql-scene ql-scene--hero".*?<!-- /scene -->'
        )
        self.assertIn('media="(max-width: 599px)" srcset="', hero)
        self.assertIn("hero-mobile-bg.webp", hero)
        self.assertIn("hero-mobile-pessoa.webp", hero)
        self.assertEqual(hero.count('fetchpriority="high"'), 2)
        self.assertRegex(hero, r'hero\.webp"[^>]*alt="[^"]{12,}"')

    def test_card_photos_are_lazy(self):
        _, body = self.get_home()

        for name in (
            "momento-comecar",
            "momento-durante",
            "momento-encerrar",
            "jornada",
        ):
            with self.subTest(image=name):
                self.assertRegex(body, rf'<img [^>]*{name}\.webp"[^>]*loading="lazy"')

    def test_pillars_come_from_database_in_display_order_with_icons(self):
        response, body = self.get_home()

        cards = re.findall(
            r'<li class="ql-pillar" data-pillar="([\w-]+)">.*?'
            r'<use href="#ql-i-([\w-]+)"\s*/?>.*?'
            r'<span class="ql-pillar__name">([^<]+)</span>',
            body,
            flags=re.DOTALL,
        )
        pillars = Pillar.objects.filter(is_active=True).order_by("display_order")
        self.assertEqual([unescape(name) for _, _, name in cards], PILLAR_NAMES)
        self.assertEqual([code for code, _, _ in cards], [p.code for p in pillars])
        self.assertEqual(
            [icon for _, icon, _ in cards], [PILLAR_ICONS[p.code] for p in pillars]
        )
        for icon in {icon for _, icon, _ in cards}:
            with self.subTest(icon=icon):
                self.assertIn(f'<symbol id="ql-i-{icon}"', body)
        self.assertQuerySetEqual(response.context["pillars"], pillars)

    def test_inactive_pillar_is_hidden(self):
        Pillar.objects.filter(code="relationships").update(is_active=False)

        _, body = self.get_home()

        self.assertNotIn('data-pillar="relationships"', body)
        self.assertEqual(body.count('class="ql-pillar"'), 8)

    def test_pillar_names_are_not_hardcoded_in_template(self):
        template = (Path(settings.BASE_DIR) / "templates" / "home.html").read_text(
            encoding="utf-8"
        )

        for name in PILLAR_NAMES:
            with self.subTest(pillar=name):
                self.assertNotIn(name, template)

    def test_authenticated_user_sees_open_app_and_lessons_links(self):
        user = get_user_model().objects.create_user(
            email="landing@example.test", password="test-password"
        )
        self.client.force_login(user)

        response, body = self.get_home()

        header = element_block(body, r"<header\b.*?</header>")
        self.assertIn(f'href="{reverse("app")}">Abrir o app</a>', header)
        self.assertNotIn(">Entrar<", header)
        cards = re.findall(r'<a class="ql-moment[^"]*" href="([^"]+)"', body)
        self.assertEqual(cards, [reverse("lessons")] * 3)
        self.assertContains(response, f'href="{reverse("app")}"')

    @override_settings()
    def test_renders_without_sales_email_setting(self):
        del settings.QL_SALES_EMAIL

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="mailto:[EMAIL-COMERCIAL]"')

    @override_settings(QL_SALES_EMAIL="vendas@example.test")
    def test_sales_button_uses_configured_email(self):
        response = self.client.get("/")

        self.assertContains(response, 'href="mailto:vendas@example.test"', count=3)
        self.assertContains(response, ">vendas@example.test</a>")
        self.assertContains(response, "Fale com a Quality Life")

    def test_home_does_not_expose_dpo_email_as_sales_contact(self):
        with override_settings(LEGAL_DPO_EMAIL="dpo@example.test"):
            response = self.client.get("/")

        self.assertNotContains(response, "dpo@example.test")


class LandingAssetTests(SimpleTestCase):
    def test_landing_images_are_webp_with_expected_sizes(self):
        for name, size in LANDING_IMAGES.items():
            with self.subTest(image=name):
                path = finders.find(f"quality_life/images/landing/{name}.webp")
                self.assertIsNotNone(path)
                width, height, alpha = webp_info(path)
                self.assertEqual((width, height), size)
                self.assertEqual(alpha, name.endswith("-pessoa"))

    def test_person_cutouts_match_their_background_frame(self):
        for prefix in ("hero", "hero-mobile", "cta"):
            with self.subTest(scene=prefix):
                bg = finders.find(f"quality_life/images/landing/{prefix}-bg.webp")
                person = finders.find(
                    f"quality_life/images/landing/{prefix}-pessoa.webp"
                )
                self.assertEqual(webp_info(bg)[:2], webp_info(person)[:2])

    def test_landing_images_have_provenance_readme(self):
        readme = finders.find("quality_life/images/landing/README.md")
        self.assertIsNotNone(readme)
        content = Path(readme).read_text(encoding="utf-8")
        self.assertIn("Higgsfield", content)
        for name in LANDING_IMAGES:
            with self.subTest(image=name):
                self.assertIn(f"{name}.webp", content)

    def test_pillar_icon_falls_back_for_unknown_codes(self):
        self.assertEqual(pillar_icon("sleep_recovery"), "moon")
        self.assertEqual(pillar_icon("unknown-code"), DEFAULT_PILLAR_ICON)
        self.assertEqual(len(PILLAR_ICONS), 9)
