"""Wellbeing catalog: files exist, nothing invented, sessions add up (spec 11)."""

import shutil
import subprocess
from pathlib import Path
from unittest import skipIf

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

from config import wellbeing_catalog as catalog
from config.exercises import EXERCISES, image_path, poster_path, visual_path

VIDEO_DIR = Path(settings.BASE_DIR) / "static" / "quality_life" / "videos" / "wellbeing"
VIDEOS = (
    "ex-pescoco",
    "ex-abertura-peito",
    "ex-punhos",
    "ex-lateral",
    "ex-passo-largo",
    "ex-sentado",
    "ex-inclinacao-frente",
    "med-foco",
    "med-ansiedade",
    "med-relaxamento",
)
PROPOSAL = "PROPOSTA — aguardando aprovação da Quality Life"


class WellbeingVideoFilesTests(SimpleTestCase):
    def test_ten_videos_exist_under_3mb_with_posters_and_provenance(self):
        for name in VIDEOS:
            with self.subTest(video=name):
                video = VIDEO_DIR / f"{name}.mp4"
                self.assertTrue(video.is_file())
                self.assertLessEqual(video.stat().st_size, 3 * 1024 * 1024)
                self.assertTrue((VIDEO_DIR / f"{name}.webp").is_file())
        self.assertEqual(len(list(VIDEO_DIR.glob("*.mp4"))), len(VIDEOS))
        readme = (VIDEO_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("gerados por IA", readme)
        self.assertIn("PENDENTES de revisão", readme)
        self.assertIn("MEMBROS INFERIORES E SUPERIORES — QUALITYLIFE AP", readme)
        self.assertIn("áudio original gerado pela IA é mantido", readme)

    @skipIf(shutil.which("ffprobe") is None, "ffprobe not installed")
    def test_every_video_keeps_its_original_audio_track(self):
        for name in VIDEOS:
            with self.subTest(video=name):
                streams = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "a",
                        "-show_entries",
                        "stream=codec_type",
                        "-of",
                        "csv=p=0",
                        str(VIDEO_DIR / f"{name}.mp4"),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.split()
                self.assertEqual(streams, ["audio"])


class ExerciseVideoTests(SimpleTestCase):
    def test_videos_follow_slug_and_missing_ones_stay_missing(self):
        slugs = {item["slug"]: item for item in EXERCISES}
        for item in EXERCISES:
            with self.subTest(exercise=item["slug"]):
                if item.get("video"):
                    self.assertEqual(
                        item["video"],
                        f"quality_life/videos/wellbeing/ex-{item['slug']}.mp4",
                    )
                    self.assertIsNotNone(finders.find(item["video"]))
                    self.assertIsNotNone(finders.find(poster_path(item)))
                self.assertIsNotNone(finders.find(visual_path(item)))
        self.assertNotIn("video", slugs["autoabraco"])
        self.assertNotIn("video", slugs["panturrilha"])

    def test_inclinacao_frente_is_transcribed_with_video_and_no_image(self):
        item = next(i for i in EXERCISES if i["slug"] == "inclinacao-frente")
        self.assertEqual(item["title"], "Inclinação do tronco à frente")
        self.assertEqual(item["category"], "Membros inferiores")
        self.assertEqual(
            item["instruction"],
            "Membros inferiores afastados, deslize as mãos pelas pernas inclinando"
            " o tronco para frente, indo em direção ao solo. Volte à posição"
            " inicial, com o abdome contraído, para proteger a coluna vertebral.",
        )
        self.assertEqual(item["page"], "")
        self.assertIsNone(image_path(item))
        self.assertEqual(
            visual_path(item), "quality_life/videos/wellbeing/ex-inclinacao-frente.webp"
        )


class GymSessionTests(SimpleTestCase):
    def test_sessions_use_only_known_exercises_and_add_up(self):
        known = {item["slug"] for item in EXERCISES}
        self.assertTrue(catalog.GYM_SESSIONS)
        for session in catalog.GYM_SESSIONS:
            with self.subTest(session=session["slug"]):
                self.assertEqual(session["type"], "sequence")
                self.assertEqual(session["status"], catalog.AVAILABLE)
                self.assertIn(session["duration_seconds"], (180, 300, 600))
                self.assertTrue(set(session["steps"]) <= known)
                self.assertEqual(
                    len(session["steps"]) * catalog.SECONDS_PER_EXERCISE,
                    session["duration_seconds"],
                )

    def test_three_categories_in_three_lengths_and_chair_option(self):
        by_category = {}
        for session in catalog.GYM_SESSIONS:
            by_category.setdefault(session["category"], set()).add(
                (session["duration_seconds"], session["chair"])
            )
        self.assertEqual(
            set(by_category),
            {
                "Alongamento para pescoço e ombros",
                "Pausa ativa para coluna",
                "Energização matinal",
            },
        )
        for durations in by_category.values():
            self.assertTrue({(180, False), (300, False), (600, False)} <= durations)
        chair = [s for s in catalog.GYM_SESSIONS if s["chair"]]
        self.assertTrue(chair)
        for session in chair:
            self.assertIn("sentado", session["steps"])
            self.assertNotIn("punhos", session["steps"])

    def test_composition_matches_requested_exercises(self):
        expected = {
            "pescoco-ombros": {"pescoco", "abertura-peito", "punhos", "autoabraco"},
            "pausa-coluna": {
                "inclinacao-frente",
                "lateral",
                "passo-largo",
                "abertura-peito",
            },
            "energizacao": {"passo-largo", "lateral", "punhos", "abertura-peito"},
        }
        for category in catalog.GYM_CATEGORIES:
            self.assertEqual(set(category["exercises"]), expected[category["slug"]])


class MeditationAndSoundTests(SimpleTestCase):
    def test_three_meditations_available_with_videos(self):
        self.assertEqual(
            [(m["title"], m["duration_seconds"]) for m in catalog.MEDITATIONS],
            [
                ("Respiração para foco", 120),
                ("Reduzir ansiedade", 300),
                ("Relaxamento profundo", 600),
            ],
        )
        for item in catalog.MEDITATIONS:
            self.assertEqual(item["status"], catalog.AVAILABLE)
            self.assertIsNotNone(finders.find(item["file"]))

    def test_available_items_point_to_existing_files_and_pending_ones_have_none(self):
        for item in catalog.all_items():
            with self.subTest(item=item["slug"]):
                self.assertIn(
                    item["status"], (catalog.AVAILABLE, catalog.IN_PREPARATION)
                )
                self.assertIn(
                    item["type"], ("sequence", "breathing", "noise", "audio", "video")
                )
                if item["status"] == catalog.IN_PREPARATION:
                    self.assertIsNone(item["file"])
                    self.assertIsNone(
                        catalog.find_available(item["kind"], item["slug"])
                    )
                elif item["type"] in ("audio", "video", "breathing"):
                    self.assertIsNotNone(finders.find(item["file"]))

    def test_seven_generated_sounds_available_sounds_before_noises(self):
        self.assertEqual(
            [
                (item["slug"], item["title"], item["type"], item["noise"])
                for item in catalog.SOUNDS
            ],
            [
                ("natureza", "Floresta calma com pássaros", "noise", "forest"),
                ("mar", "Ondas do mar", "noise", "ocean"),
                ("chuva", "Chuva suave", "noise", "rain"),
                ("musica-concentracao", "Acordes suaves", "noise", "music"),
                ("ruido-branco", "Ruído branco", "noise", "white"),
                ("ruido-rosa", "Ruído rosa", "noise", "pink"),
                ("ruido-marrom", "Ruído marrom", "noise", "brown"),
            ],
        )
        for item in catalog.SOUNDS:
            self.assertEqual(item["status"], catalog.AVAILABLE)
            self.assertIsNone(item["file"])
        self.assertEqual(catalog.RELAX_TIMER_MINUTES, (5, 10, 15, 30))

    def test_tips_start_empty_and_proposals_are_marked(self):
        self.assertEqual(catalog.TIPS, ())
        source = Path(catalog.__file__).read_text(encoding="utf-8")
        for constant in (
            "SECONDS_PER_EXERCISE",
            "BREATH_IN_SECONDS",
            "BREATH_OUT_SECONDS",
        ):
            line = next(
                index
                for index, text in enumerate(source.splitlines())
                if text.startswith(f"{constant} =")
            )
            self.assertIn(PROPOSAL, "\n".join(source.splitlines()[line - 2 : line]))
