# DONE-creative-streaming — adhd-focus ×1, ai-ocean-space-ambient-streaming ×4, synthwave-study-streaming ×4

Reviewed 2026-10-03 (parallel pass). 9 posts: 0 Ready / 4 Needs revision / 5 Not ready.

## Per-post scorecard

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding |
|---|---|---|---|---|---|---|---|---|---|---|
| adhd-focus-music-streaming-implementation-guide-zh.md | 2489 | 3 | 3 | 3 | 2 | 2 | 3 | 2.7 | Not ready | L1224–1227 channel-description template tells readers to publish "40Hz binaural beats **proven** to enhance focus in ADHD", contradicting L108 「目前沒有定論」 |
| ai-ocean-space-ambient-streaming-part1-foundation-zh.md | 950 | 3 | 3 | 3 | 2 | 3 | 3 | 2.8 | Not ready | L69–135 three real channels given invented subscriber/CCV figures and "品牌老化（2011 年成立）" |
| ai-ocean-space-ambient-streaming-part2-visual-zh.md | 1162 | 3 | 4 | 3 | 2 | 3 | 3 | 3.0 | Needs revision | L9/L77 sells "Midjourney V7" while every prompt pins `--v 6.1` |
| ai-ocean-space-ambient-streaming-part3-technical-zh.md | 1302 | 4 | 4 | 3 | 3 | 3 | 3 | 3.3 | Needs revision | L1289 nav says "8K 場景生成" though part 2 is 4K and says 8K has no benefit |
| ai-ocean-space-ambient-streaming-part4-growth-zh.md | 1727 | 2 | 3 | 2 | 1 | 2 | 3 | 2.2 | Not ready | L745–755 description template: "Reduce cortisol by up to 25%", "Lower blood pressure" — unsourced health claims readers are told to publish |
| synthwave-study-streaming-part1-market-culture-zh.md | 752 | 2 | 3 | 2 | 2 | 3 | 3 | 2.5 | Not ready | L99 "r/outrun 500K+" vs L307 "685K" — self-contradictory; actual ≈406K |
| synthwave-study-streaming-part2-music-production-zh.md | 938 | 3 | 4 | 3 | 2 | 3 | 3 | 3.0 | Needs revision | L74 "Take On Me" riff attributed to DX7 (commonly credited to Juno-60) ❓ |
| synthwave-study-streaming-part3-cyberpunk-visual-zh.md | 1042 | 3 | 4 | 3 | 2 | 3 | 3 | 3.0 | Needs revision | L284–444 twelve prompts hard-code `--v 6.1` |
| synthwave-study-streaming-part4-community-monetization-zh.md | 1856 | 2 | 3 | 3 | 2 | 2 | 2 | 2.3 | Not ready | L425/L512/L1414/L284 four code snippets that will not run as written |

## Patterns
- **Content quality**: prose delivered mostly inside ```yaml/```markdown fences (adhd 44 fences, synth p4 62) — checklists, personas, "預期數據" blocks with invented ranges. Motivational closers (adhd L2467–2483, ocean p4 L1692–1710). 22 verbatim lines shared across series: OBS output settings, restart cron, Discord server trees ×3, bot blocks ×2, sponsor email ×2.
- **Structure**: no series rules apply, yet every post is 750–2,489 lines; length comes from templates (fifty Shorts titles, a 97-line description template). Only ocean p3 states a problem before the solution. Series nav drift: ocean nav says "8K" ×3; synth p1–p3 nav entries are bold text, not links.
- **Depth**: the author hedges honestly ("示意估算，非實測數據" in every market section) — so the quantitative core is invented, then growth curves are built on it (ocean p4 L1606–1647; synth p1 L548–550). Genuine depth exists in ocean p3 (encoder/egress/monitoring L59–74, L482–530), synth p2 (energy-curve curation L680–780), synth p4 L1600–1636 "何時該放棄或轉型".
- **Direction**: four treatments of one business plan (niche → AI audio → AI visuals → OBS → Shorts → Discord → memberships). Gaps: a real post-mortem with actual YouTube Studio data; AI-music copyright / Content ID; photosensitivity for neon visuals. Stale pins: Runway "Gen-3 Alpha", `--v 6.1`, Patreon tiers.
- **Accuracy**: see claims. Science claims (adhd L52–130, ocean p1 L143–205) have zero citations.
- **Format**: readTime understated ~2× everywhere (adhd 39 vs ~78 min); `summary` and `description` identical in 8 posts; synth p4 bare date, 12 tags, missing `business` category; every post ends with a fake "**標籤**: #…" hashtag line that is not Hugo taxonomy.

## Verified / unverified claims (abridged)
✅ YPP thresholds (1,000 subs / 4,000 h); Suno Pro $10 / Premier $30; Midjourney $10/$30/$60; Runway credit tiers; Udio 15-min max; ADHD prevalence (Song 2021; Kessler 2006 — 20 years old); ChilledCow→Lofi Girl 2021; obs-websocket in OBS 28 port 4455; 1.9 TB/mo egress at 6,000 kbps; all membership/product arithmetic.
❌ Lofi Girl "1200 萬" (≈15.8 M); r/ADHD 1.2 M (≈2.3 M); r/outrun 500K/685K (≈406K); Patreon "5–12 %" (flat 10 % since Aug 2025); Brain.fm $6.99 (now $14.99); Gumroad +$0.30 (+$0.50); synth p1 L62–71 timeline puts Drive (2011) and Streets of Rage (1991) under "1980s"; synth p4 code: `commands.Bot` without `intents`, `asyncio` unimported, `filters='video==SHORT'` not a YouTube Analytics filter, `vfx.blur` not in MoviePy; synth p4 L1458 "CPM $10 × 20,000 觀看時數" misuses CPM.
❓ Market-size figures labelled 示意 then used as the business case; growth projections with no comparable.

## Top findings
1. blocker — adhd L1224–1227, L1162–1163: publishable "proven" health claim contradicting L108.
2. blocker — ocean p4 L745–755, L431: cortisol / blood-pressure claims, no source.
3. blocker — synth p4 broken code (L425, L512, L510, L1414, L284).
4. major — ocean p1 L69–135, synth p1 L331–420: real channel names with invented stats → anonymise or use dated Social Blade counts.
5. major — synth p1 L99 vs L307 contradiction; L62–71 timeline errors.
6. major — ocean p4 three incompatible growth scenarios (L823–866 / L1595–1647 / L884).
7. major — outdated third-party prices/counts; date-stamp every one.
8. major — "V7" vs `--v 6.1`; Gen-3 Alpha; remove version pins or state "以當前預設模型為準".
9. major — duplication across adhd / ocean p3–p4 / synth p4 → one canonical "24/7 音樂直播基礎建設" post, cut ~800 lines.
10. minor — readTime drift, synth p4 front matter, nav "8K", unlinked nav, pseudo-hashtag lines.

## Recommendations
1. Remove or cite every health/science claim in publishable templates (blockers 1–2).
2. Extract the shared infrastructure (OBS, restart cron, Discord, bots, sponsor email) into one canonical post and link to it from the three series.
3. Replace invented competitor and market numbers with dated, sourced counts or anonymised examples; keep the honest "示意" hedge but stop building projections on it.
4. Run every code snippet before publishing; relabel pseudo-code as such.
5. Fix front matter mechanically: readTime, categories, duplicate summary, pseudo-hashtag lines.
