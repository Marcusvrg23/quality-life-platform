"""Server-rendered navigation and identity contracts for the shared demo shell."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from config.exercises import EXERCISES, SOURCE
from config.forms import EmailAuthenticationForm


class AppShellTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get(reverse("app"))
        self.request.user = get_user_model()(email="real.member@example.test")
        self.request.resolver_match = resolve(reverse("app"))
        self.tenant = SimpleNamespace(
            organization=SimpleNamespace(name="Real Company & Partners")
        )

    def render(self, template="identity/app.html", **context):
        return render_to_string(
            template, {"tenant": self.tenant, **context}, request=self.request
        )

    def test_dashboard_uses_real_identity_and_available_destinations(self):
        html = self.render()
        self.assertIn("real.member@example.test", html)
        self.assertIn("Real Company &amp; Partners", html)
        self.assertIn("Escolha sua atividade", html)
        self.assertIn(f'href="{reverse("exercises")}"', html)
        self.assertIn(f'href="{reverse("assessment_hub")}"', html)
        self.assertNotIn('href="#"', html)
        self.assertNotIn("Mariana Alves", html)
        self.assertNotIn("Carla Souza", html)

    def test_logout_remains_post_with_csrf(self):
        html = self.render()
        self.assertIn(f'method="post" action="{reverse("logout")}"', html)
        self.assertIn('name="csrfmiddlewaretoken"', html)
        self.assertNotIn(f'href="{reverse("logout")}"', html)

    def test_assessment_reuses_navigation_and_preserves_hub_action(self):
        self.request.resolver_match = resolve(reverse("assessment_hub"))
        html = self.render("assessments/hub.html", available=True)
        self.assertIn('id="app-navigation"', html)
        self.assertIn("app-shell.js", html)
        self.assertIn("Iniciar avaliação", html)
        self.assertIn(f'action="{reverse("assessment_start")}"', html)
        self.assertIn(f'href="{reverse("assessment_hub")}" aria-current="page"', html)

    def test_drawer_has_control_relationship_and_focusable_close(self):
        html = self.render()
        self.assertIn('aria-controls="app-navigation"', html)
        self.assertIn('id="app-navigation"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('type="button" aria-label="Fechar menu" data-drawer-close', html)
        self.assertIn('href="#main"', html)

    def test_login_preserves_real_form_next_and_single_official_logo(self):
        html = self.render(
            "identity/login.html",
            form=EmailAuthenticationForm(),
            next=reverse("assessment_hub"),
        )
        self.assertIn(f'method="post" action="{reverse("login")}"', html)
        self.assertIn('name="username"', html)
        self.assertIn('name="password"', html)
        self.assertIn('name="csrfmiddlewaretoken"', html)
        self.assertIn(f'name="next" value="{reverse("assessment_hub")}"', html)
        self.assertEqual(html.count("quality-life-logo.png"), 1)
        self.assertNotIn("Esqueci minha senha", html)

    def test_identity_is_escaped_in_shell(self):
        self.request.user.email = '<script>alert("unsafe")</script>@example.test'
        html = self.render()
        self.assertNotIn('<script>alert("unsafe")</script>', html)
        self.assertIn("&lt;script&gt;", html)

    def test_exercise_fallback_and_unique_accessible_openers(self):
        self.request.resolver_match = resolve(reverse("exercises"))
        html = self.render("exercises/library.html", exercises=EXERCISES, source=SOURCE)
        self.assertEqual(html.count('<details class="exercise-instructions">'), 8)
        self.assertEqual(html.count('aria-label="Ver exercício:'), 8)
        self.assertIn('data-sequence-position aria-live="polite"', html)
        self.assertIn('class="exercise-dialog" aria-labelledby="exercise-title"', html)
        self.assertIn('class="exercise-filters exercise-enhanced"', html)
