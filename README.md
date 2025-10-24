# Cinematic Minecraft — Vanilla+ Performance & Polish (Fabric 1.21.1)

A **Vanilla-first** modpack that keeps the core gameplay intact while delivering **high, stable FPS**, **cinematic draw distance**, **subtle visual upgrades**, and **clean UI/UX**.
This repository exists primarily for **issue tracking**, feature requests, and documentation.

![huge_2025-10-22_11.22.09.png](screenshots/huge_2025-10-22_11.22.09.png)



> Target game: **Minecraft 1.21.1**
> Loader: **Fabric**
> Java: **21** (Adoptium/Temurin recommended)

---

## Contents
![huge_2025-10-23_08.27.58.png](screenshots/huge_2025-10-23_08.27.58.png)
* [What You Get](#what-you-get)
* [Quick Install](#quick-install)
* [Minimum Hardware](#minimum-hardware)
* [Reporting Issues](#reporting-issues)
* [Feature Requests](#feature-requests)
* [Configuration Notes](#configuration-notes)
* [Included (Highlights)](#included-highlights)
* [Included Resource Packs](#included-resource-packs)
* [Compatibility & Known Limits](#compatibility--known-limits)
* [Roadmap](#roadmap)
* [License & Credits](#license--credits)

---

## What You Get
![huge_2025-10-23_10.45.33.png](screenshots/huge_2025-10-23_10.45.33.png)
* **Performance first:** Sodium, Lithium, FerriteCore, Krypton, Noisium, Alternate Current, C2ME, VMP, ServerCore, MoreCulling, EntityCulling, ImmediatelyFast, ThreadTweak, and others trim CPU/GPU waste, smooth frametimes, and speed world loading.
* **Cinematic distance:** **Distant Horizons** (LOD terrain) + **Bobby** (server-side view distance caching) let you see far without tanking FPS.
* **Shaders that behave:** **Iris** + **Euphoria Patcher** for high-compatibility shader support (e.g., Complementary).
* **World that still feels vanilla:** **Dungeons & Taverns** (including Stronghold/Ancient City overhauls), **Nature’s Spirit**, **ATI Structures**, **Fabric Seasons**, and **Snow! Real Magic!** add believable variety while respecting balance.
* **Clean HUD & QoL:** BetterF3, JEI, Controlling, Searchables, Shulker Box Tooltip, Durability/Status bars, Mod Menu—information where you need it, no clutter.
* **Animation polish:** NotEnoughAnimations, Vintage Animations, Player Animation Library, Camera Overhaul, Better Third Person, ETF/EMF, CIT Resewn.
* **Subtle weather & audio:** Particlerain, Cool Rain, Atmosfera, armor sound tweaks—to make storms less noisy and more atmospheric.

---

## Quick Install
![huge_2025-10-23_10.50.38.png](screenshots/huge_2025-10-23_10.50.38.png)
1. **Install Java 21.**
2. **Install a Fabric-friendly launcher** (Prism Launcher or your preferred choice).
3. **Create a new Fabric 1.21.1 instance.**
4. **Import the pack** (e.g., from a `.mrpack`/release archive) **or** drop the `mods/` and `resourcepacks/` from the distribution into the instance.
5. Launch once, then open **Mod Menu** → tweak options (Sodium, Reese’s Sodium Options, Iris, Distant Horizons) as described below.

> This repo does not ship binaries; it’s used for **issues and documentation**. If you’re here from a distribution page, use that page’s downloads.

---

## Minimum Hardware

* **RAM:** 16 GB system RAM (allocate **6–8 GB** to Minecraft).
* **CPU:** Modern 6+ core CPU with strong single-thread; DH benefits from higher clocks.
* **GPU:** Recent discrete GPU. RTX 4070-class handles shaders + far LODs comfortably.
* **Storage:** SSD/NVMe recommended (faster chunk/pack loads).

---

## Reporting Issues

Open a **New Issue** and use this template:

```
Title: [Bug/Crash/Performance] One-line summary

Game version: 1.21.1
Java version: 21 (vendor + build)
Launcher: Prism / MultiMC / Other
GPU + driver: (e.g., NVIDIA 552.xx)
CPU + RAM: (e.g., 12700K + 32GB)
Mods added/removed: (list anything you changed)
Shader pack: (if any)

What happened:
- Step 1
- Step 2
- Step 3
Expected:
Actual:

Logs:
- latest.log (paste/attach)
- crash report (if any)
Screenshots/video:
- (attach if visual/animation/culling related)
```

**Please attach `latest.log`** (from the instance `logs/` folder) and any crash report. Reproduce with **only this pack** before filing.

---

## Feature Requests

Open a **Feature request** issue and include:

* The “why” (user problem this solves).
* Proposed mod(s) or change.
* Impact on performance, SMP, or vanilla feel.
* Any known conflicts or alternatives.

Requests that increase bloat, duplicate existing features, or break vanilla progression are likely to be declined.

---

## Configuration Notes

* **Sodium / Reese’s Sodium Options / Sodium Extra**
  Start with the “High” preset, then enable Chunk Render Distance to your preference. If VRAM-bound, reduce MIP bias and disable costly particles.
* **Iris + Shaders**
  Complementary/Reimagined variants are recommended. With rain-heavy areas, pair with **Particlerain** and **Cool Rain** for clarity.
* **Distant Horizons**
  Set DH Render Distance ~2–4× your Minecraft distance, then adjust DH Quality until frametimes stabilize. Keep DH VRAM budgeting conservative on mid GPUs.
* **Bobby** (multiplayer)
  Allow caching; set a sensible cap for disk usage.
* **Fabric Seasons**
  Keep defaults for subtle color changes. Disable if you need absolute visual parity with vanilla screenshots.

---

## Included (Highlights)

**Performance & Core:** Sodium, Reese’s Sodium Options, Sodium Extra, Lithium, FerriteCore, Krypton, Noisium, Alternate Current, C2ME, VMP, ServerCore, MoreCulling, EntityCulling, ImmediatelyFast, ThreadTweak, AsyncParticles, Cloth Config, Architectury, Fabric API, Forge Config API Port, YACL, Fabric Language Kotlin, owo-lib, OctoLib, MidnightLib, Puzzles Lib, Flow, Kiwi, Fzzy Config, SuperMartijn642’s Config Lib, Architecturey, TinxLib, MRU (LTS), Placeholder API.

**Visuals, Weather, Shaders:** Iris, Euphoria Patcher, Particlerain, Cool Rain, Atmosfera, Perception (Fabric), LambDynamicLights.

**World & Exploration:** Dungeons & Taverns (+ Stronghold & Ancient City overhauls), Nature’s Spirit, ATI Structures, Roadarchitect (+ Encounters), Fabric Seasons (+ Nature’s Spirit compat), Snow! Real Magic!, Distant Horizons, Bobby, TerraBlender.

**UI & QoL:** BetterF3, JEI, HMI, Controlling, Searchables, Mod Menu, Mouse Tweaks, Shulker Box Tooltip, Durability Tooltip, Status Effect Bars, Detail Armor Bar, LeaveMyBarsAlone, Satisfying Buttons, Fabrishot.

**Animation & Camera:** NotEnoughAnimations, Vintage Animations, Player Animation Library, Camera Overhaul, Better Third Person, CIT Resewn, Entity Model Features (EMF), Entity Texture Features (ETF).

---

## Included Resource Packs

* Angel’s Weather v1.9.1 (hf)
* Vocal Villagers
* 8bu Unobtrusive Weather 58
* Gentler Weather Sounds 2.x
* Better Lanterns (1.21)
* Crops-3D
* Cubic Leaves 2.0 (Performance)
* DoorTweaks
* Enchant Icons (1.21)
* EvenBetterEnchants v2
* Fresh Animations
* GUIRevision
* Os’ Colorful Grasses (Mix)
* SPBR-16_2
* Unique Dark – Lite (1.20.2–1.21.x)
* Vanilla Mashup 1.4.b

Enable/stack these to taste. Keep **Fresh Animations** higher than packs that override mob textures.

---

## Compatibility & Known Limits

* **OptiFine is not supported.** Use Iris + Sodium.
* Avoid stacking extra “culling/renderer hacks” not in the pack; they can fight Sodium/MoreCulling/EntityCulling or shaders.
* Extremely high particle counts, volumetric shader presets, or ultra DH settings will cost frametime even on high-end GPUs.
* Mods not shipped here may crash due to missing APIs; if you add mods, list them in your bug report.

---

## Roadmap

* Preset profiles: **Performance-Only**, **Balanced**, **Cinematic**.
* Optional “SMP Minimal” variant (client-side only, stricter compatibility).
* Tuning guide per GPU tier with before/after frametime charts.

---

## License & Credits

* **This repository:** docs/configs under a permissive license (MIT unless noted).
* **All individual mods and resource packs** retain their original authors’ licenses—credit to their maintainers.
* If you are a mod author and would like adjustments to how your work is referenced here, open an issue.

---

### Changelog

Track changes in **Releases** (versioned by Minecraft + date) or the `CHANGELOG.md` when present.

---

Questions that aren’t bugs? Open a **Q&A** issue.
If you’re reporting a crash, include **`latest.log`** and the **crash report**—that’s the difference between a same-day fix and guesswork.
