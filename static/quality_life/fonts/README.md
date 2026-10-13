# Local fonts

Variable upright fonts from Google Fonts' upstream repository, converted to WOFF2
with fontTools and subset to Latin/Latin Extended-A + general punctuation.
Portuguese accents are included; no fonts are requested from Google at runtime.

- Figtree (400–700 used): https://github.com/google/fonts/tree/main/ofl/figtree
- Quicksand (600–700 used): https://github.com/google/fonts/tree/main/ofl/quicksand

Each family retains its SIL Open Font License in the adjacent `*-OFL.txt` file.
Use `font-display: swap` and the family/weight ranges defined in `brand.css`.
