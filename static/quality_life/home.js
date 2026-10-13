/* Landing page motion: progressive enhancement only.
   Without JS or with prefers-reduced-motion: reduce nothing runs, and the CSS
   never hides content; initial states come from gsap.from() below. Only
   transform and opacity are animated. */
(function () {
    "use strict";

    var gsap = window.gsap;
    var ScrollTrigger = window.ScrollTrigger;
    if (!gsap || !ScrollTrigger) {
        return;
    }
    gsap.registerPlugin(ScrollTrigger);

    var PARALLAX_LIMIT = 40;

    function parallaxPercent(element) {
        var factor = parseFloat(element.getAttribute("data-parallax"));
        if (!isFinite(factor)) {
            return 0;
        }
        return gsap.utils.clamp(-PARALLAX_LIMIT, PARALLAX_LIMIT, factor * 100);
    }

    gsap.matchMedia().add("(prefers-reduced-motion: no-preference)", function () {
        var ease = "power2.out";

        gsap.from(".ql-header", { opacity: 0, duration: 0.6, ease: ease });

        gsap.from("[data-anim='hero'] > *", {
            y: 24,
            opacity: 0,
            duration: 0.7,
            ease: ease,
            stagger: 0.08,
            delay: 0.1,
        });

        gsap.from(".ql-preview", {
            scale: 0.96,
            opacity: 0,
            duration: 0.8,
            ease: ease,
            delay: 0.25,
        });

        gsap.utils.toArray("[data-parallax]").forEach(function (element) {
            gsap.to(element, {
                yPercent: parallaxPercent(element),
                ease: "none",
                data: "parallax",
                scrollTrigger: {
                    trigger: element.closest("section") || element,
                    start: "clamp(top bottom)",
                    end: "bottom top",
                    scrub: true,
                },
            });
        });

        gsap.utils.toArray("[data-anim='reveal']").forEach(function (element) {
            gsap.from(element, {
                y: 32,
                opacity: 0,
                duration: 0.7,
                ease: ease,
                scrollTrigger: { trigger: element, start: "top 88%", once: true },
            });
        });

        gsap.utils.toArray("[data-anim='stagger']").forEach(function (element) {
            gsap.from(element.children, {
                y: 24,
                opacity: 0,
                duration: 0.6,
                ease: ease,
                stagger: 0.08,
                scrollTrigger: { trigger: element, start: "top 88%", once: true },
            });
        });
    });
})();
