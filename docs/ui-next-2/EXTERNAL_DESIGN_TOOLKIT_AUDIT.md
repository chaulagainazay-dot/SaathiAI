# EXTERNAL_DESIGN_TOOLKIT_AUDIT

Location: `~/dev-toolkits/ui-design/` (outside SaathiOS git). **Not vendored.**

| Toolkit | Remote | SHA | License | Size | Purpose | SaathiOS fit | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ui-ux-pro-max-skill | nextlevelbuilder/ui-ux-pro-max-skill | `abb7f2fd5a083fa1ff55c326a963ff0d95c33f99` | MIT | ~24MB | UX audit, layout, a11y, patterns | Design intelligence only | **ADAPT** |
| design-dna | zanwei/design-dna | `9d9d79568df31cd846681f89fd3be1c3ce0c2aff` | MIT | ~344KB | Design identity methodology | Methodology → native DNA | **ADAPT** |
| motion-design-skill | LottieFiles/motion-design-skill | `f9a8a041b85185ee4881b3471d3415e939aac772` | MIT | ~244KB | Motion timing, reduced motion | Spec later Lottie | **INTEGRATE_LATER** |
| gsap-skills | greensock/gsap-skills | `aed9cfd3277740755f6bfc1155c7aa645403b760` | MIT (skill docs) | ~444KB | Timeline choreography guidance | Selective later; runtime license separate | **INTEGRATE_SELECTIVELY_LATER** |
| threejs-skills | CloudAI-X/threejs-skills | `b1c623076c661fc9b03dac19292e825a5d106823` | (see README) | ~324KB | 3D knowledge for agents | Future Yeti/spatial only | **DEFER** |

## Security surface

- Toolkits are documentation/skill repos, not runtime dependencies of SaathiOS.
- No network calls from production app to these repos.
- GSAP **runtime** licensing must be re-verified before any production GSAP bundle.

## Dependencies

None installed into SaathiOS `package.json` for this milestone.

