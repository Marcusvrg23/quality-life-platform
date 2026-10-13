/* Landing page behaviour. The header and the section menu work for everyone;
   motion is progressive enhancement: without JS or with
   prefers-reduced-motion: reduce nothing animates and the CSS shows the
   static photos. Tweens only touch transform and opacity. Endless tweens are
   tagged data: "loop" and scroll-scrubbed ones data: "parallax"; loops pause
   while their section is off screen or the tab is hidden. */
(function () {
    "use strict";

    var header = document.querySelector(".ql-header");
    var toggle = document.querySelector(".ql-menu-toggle");
    var menu = document.getElementById("ql-menu");
    var desktopQuery = window.matchMedia("(min-width: 900px)");
    var reduceQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

    function updateHeader() {
        header.classList.toggle("is-scrolled", window.scrollY > 24);
    }

    window.addEventListener("scroll", updateHeader, { passive: true });
    updateHeader();

    function menuOpen() {
        return toggle.getAttribute("aria-expanded") === "true";
    }

    function setMenu(open, restoreFocus) {
        toggle.setAttribute("aria-expanded", String(open));
        menu.classList.toggle("is-open", open);
        header.classList.toggle("is-open", open);
        if (open) {
            menu.querySelector("a").focus();
            if (window.gsap && !reduceQuery.matches) {
                window.gsap.from(menu.children, {
                    y: -8,
                    opacity: 0,
                    duration: 0.3,
                    ease: "power2.out",
                    stagger: 0.04,
                });
            }
        } else if (restoreFocus) {
            toggle.focus();
        }
    }

    toggle.addEventListener("click", function () {
        setMenu(!menuOpen(), true);
    });
    menu.addEventListener("click", function (event) {
        if (event.target.closest("a") && menuOpen()) {
            setMenu(false, false);
        }
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && menuOpen()) {
            setMenu(false, true);
        }
    });
    document.addEventListener("click", function (event) {
        if (menuOpen() && !header.contains(event.target)) {
            setMenu(false, false);
        }
    });
    desktopQuery.addEventListener("change", function () {
        if (menuOpen()) {
            setMenu(false, false);
        }
    });

    var gsap = window.gsap;
    var ScrollTrigger = window.ScrollTrigger;
    var ambient = window.QLAmbient;
    if (!gsap || !ScrollTrigger) {
        return;
    }
    gsap.registerPlugin(ScrollTrigger);

    function q(selector) {
        return document.querySelector(selector);
    }

    gsap.matchMedia().add("(prefers-reduced-motion: no-preference)", function () {
        var hero = q(".ql-hero");
        var cta = q(".ql-cta");
        var heroRig = q(".ql-scene--hero .ql-scene__rig");
        var ctaRig = q(".ql-scene--cta .ql-scene__rig");
        var loops = [];
        var visible = new Set();

        function loop(target, vars) {
            vars.data = "loop";
            vars.repeat = -1;
            vars.yoyo = true;
            var section = target.closest("section");
            var tween = gsap.to(target, vars);
            loops.push({ tween: tween, section: section });
            return tween;
        }

        function syncLoops() {
            loops.forEach(function (item) {
                var on = !document.hidden && visible.has(item.section);
                item.tween.paused(!on);
            });
        }

        function parallax(target, from, to, trigger, start, end) {
            to.ease = "none";
            to.data = "parallax";
            to.scrollTrigger = {
                trigger: trigger,
                start: start || "top top",
                end: end || "bottom top",
                scrub: 1,
            };
            gsap.fromTo(target, from, to);
        }

        // Hero entrance: the scene zooms out, words rise from their mask.
        var intro = gsap.timeline({ defaults: { ease: "power3.out" } });
        intro
            .from(header, { opacity: 0, y: -12, duration: 0.6 }, 0)
            .from(heroRig, { scale: 1.08, duration: 2.4, ease: "power2.out" }, 0)
            .from(".ql-h1 .ql-word > span", {
                yPercent: 110,
                duration: 1.1,
                ease: "expo.out",
                stagger: 0.08,
            }, 0.15)
            .from("[data-hero]", { y: 36, opacity: 0, duration: 0.9, stagger: 0.12 }, 0.45);

        gsap.utils.toArray("[data-count]").forEach(function (element) {
            var end = Number(element.getAttribute("data-count"));
            var suffix = element.getAttribute("data-suffix") || "";
            var state = { value: 0 };
            element.textContent = "0" + suffix;
            intro.to(state, {
                value: end,
                duration: 1.6,
                ease: "power2.out",
                onUpdate: function () {
                    element.textContent = Math.round(state.value) + suffix;
                },
            }, 0.9);
        });

        // Breathing starts once the zoom-out ends; the wrapper keeps the photo
        // and the cut-out locked together.
        loop(heroRig, { scale: 1.02, duration: 7, ease: "sine.inOut", delay: 2.4 });
        gsap.from(ctaRig, {
            scale: 1.08,
            duration: 2.2,
            ease: "power2.out",
            scrollTrigger: { trigger: cta, start: "clamp(top 82%)", once: true },
            onComplete: function () {
                loop(ctaRig, { scale: 1.02, duration: 7, ease: "sine.inOut" });
                syncLoops();
            },
        });

        gsap.utils.toArray("[data-float]").forEach(function (element, index) {
            loop(element, {
                y: -6,
                duration: 2.6 + (index % 4) * 0.35,
                ease: "sine.inOut",
                delay: (index % 5) * 0.3,
            });
        });

        // Scroll reveals.
        gsap.utils.toArray("[data-reveal]").forEach(function (element) {
            gsap.from(element, {
                y: 48,
                opacity: 0,
                duration: 1,
                ease: "power3.out",
                scrollTrigger: { trigger: element, start: "clamp(top 82%)", once: true },
            });
        });
        gsap.utils.toArray("[data-reveal-group]").forEach(function (group) {
            gsap.from(group.children, {
                y: 48,
                opacity: 0,
                scale: 0.96,
                rotationX: 8,
                transformPerspective: 900,
                transformOrigin: "50% 100%",
                duration: 1,
                ease: "power3.out",
                stagger: 0.14,
                scrollTrigger: { trigger: group, start: "clamp(top 82%)", once: true },
            });
        });

        // Parallax: wrapper, back and front canvases move at different speeds.
        parallax(heroRig, { yPercent: 0 }, { yPercent: 10 }, hero);
        parallax(".ql-scene--hero .ql-layer--back", { yPercent: 0 }, { yPercent: -5 }, hero);
        parallax(".ql-scene--hero .ql-layer--front", { yPercent: 0 }, { yPercent: -12 }, hero);
        parallax(".ql-hero__copy", { y: 0 }, { y: -70 }, hero);
        var through = ["top bottom", "bottom top"];
        parallax(ctaRig, { yPercent: 6 }, { yPercent: -6 }, cta, through[0], through[1]);
        parallax(".ql-scene--cta .ql-layer--back", { yPercent: 4 }, { yPercent: -4 }, cta, through[0], through[1]);
        parallax(".ql-scene--cta .ql-layer--front", { yPercent: 10 }, { yPercent: -10 }, cta, through[0], through[1]);
        gsap.utils.toArray(".ql-moment__media img, .ql-how__photo img").forEach(function (image) {
            parallax(image, { yPercent: -6 }, { yPercent: 6 }, image.parentNode, through[0], through[1]);
        });

        // Canvas scenes and loops run only while their section is on screen.
        if (ambient) {
            ambient.scene(
                "hero",
                q(".ql-scene--hero .ql-layer--back"),
                q(".ql-scene--hero .ql-layer--front")
            );
            ambient.scene(
                "cta",
                q(".ql-scene--cta .ql-layer--back"),
                q(".ql-scene--cta .ql-layer--front")
            );
            ScrollTrigger.addEventListener("refresh", ambient.refresh);
        }
        var sections = gsap.utils.toArray("main > section");
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                var section = entry.target;
                if (entry.isIntersecting) {
                    visible.add(section);
                } else {
                    visible.delete(section);
                }
                section.classList.toggle("ql-paused", !entry.isIntersecting);
                if (ambient && section === hero) {
                    ambient.setActive("hero", entry.isIntersecting);
                } else if (ambient && section === cta) {
                    ambient.setActive("cta", entry.isIntersecting);
                }
            });
            syncLoops();
        });
        sections.forEach(function (section) {
            observer.observe(section);
        });
        document.addEventListener("visibilitychange", syncLoops);

        // Hover: magnetic buttons, 3D tilt and spotlight (fine pointers only).
        if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
            gsap.utils.toArray(".ql-btn").forEach(function (button) {
                button.addEventListener("pointermove", function (event) {
                    var box = button.getBoundingClientRect();
                    gsap.to(button, {
                        x: (event.clientX - box.left - box.width / 2) * 0.16,
                        y: (event.clientY - box.top - box.height / 2) * 0.26,
                        duration: 0.4,
                        ease: "power3.out",
                        overwrite: "auto",
                    });
                });
                button.addEventListener("pointerleave", function () {
                    gsap.to(button, {
                        x: 0,
                        y: 0,
                        duration: 0.6,
                        ease: "elastic.out(1, 0.5)",
                        overwrite: "auto",
                    });
                });
            });
            gsap.utils.toArray(".ql-moment, .ql-pillar, .ql-company").forEach(function (card) {
                var tilt = card.classList.contains("ql-company") ? 0 : 6;
                card.addEventListener("pointermove", function (event) {
                    var box = card.getBoundingClientRect();
                    var px = (event.clientX - box.left) / box.width;
                    var py = (event.clientY - box.top) / box.height;
                    card.style.setProperty("--mx", (px * 100).toFixed(1) + "%");
                    card.style.setProperty("--my", (py * 100).toFixed(1) + "%");
                    if (tilt) {
                        gsap.to(card, {
                            rotationY: (px - 0.5) * tilt,
                            rotationX: (0.5 - py) * tilt,
                            transformPerspective: 900,
                            duration: 0.5,
                            ease: "power2.out",
                            overwrite: "auto",
                        });
                    }
                });
                card.addEventListener("pointerleave", function () {
                    if (tilt) {
                        gsap.to(card, {
                            rotationX: 0,
                            rotationY: 0,
                            duration: 0.7,
                            ease: "power3.out",
                            overwrite: "auto",
                        });
                    }
                });
            });
        }

        return function () {
            observer.disconnect();
            document.removeEventListener("visibilitychange", syncLoops);
            if (ambient) {
                ScrollTrigger.removeEventListener("refresh", ambient.refresh);
            }
            sections.forEach(function (section) {
                section.classList.remove("ql-paused");
            });
        };
    });
})();
