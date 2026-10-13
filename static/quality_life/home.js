/* Motion is optional: all content is visible until GSAP takes over. */
(() => {
  "use strict";
  if (!window.gsap || !window.ScrollTrigger) return;
  const { gsap, ScrollTrigger } = window;
  gsap.registerPlugin(ScrollTrigger);
  const media = gsap.matchMedia();
  media.add("(prefers-reduced-motion: no-preference)", () => {
    gsap.from(".site-header", { opacity: 0, duration: 0.6, clearProps: "opacity" });
    gsap.from(".hero-item", {
      y: 24, opacity: 0, duration: 0.7, stagger: 0.08,
      ease: "power2.out", clearProps: "transform,opacity",
    });
    gsap.from(".app-preview", {
      scale: 0.96, opacity: 0, duration: 0.9,
      ease: "power2.out", clearProps: "transform,opacity",
    });
    gsap.utils.toArray("[data-parallax]").forEach((element) => {
      const factor = Number(element.dataset.parallax);
      if (!Number.isFinite(factor)) return;
      gsap.to(element, {
        yPercent: gsap.utils.clamp(-40, 40, factor * 40), ease: "none",
        scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true },
      });
    });
    gsap.utils.toArray('[data-anim="reveal"], [data-anim="stagger"]').forEach((element) => {
      const stagger = element.dataset.anim === "stagger";
      gsap.from(stagger ? element.children : element, {
        y: 24, opacity: 0, duration: 0.6, stagger: stagger ? 0.08 : 0,
        ease: "power2.out", clearProps: "transform,opacity",
        scrollTrigger: { trigger: element, start: "top 90%", once: true },
      });
    });
  });
})();
