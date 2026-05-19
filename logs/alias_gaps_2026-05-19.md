# Alias Gaps — Weekly v2.9 Scan 2026-05-19

Fonte: `logs/weekly_local_2026-05-19.log` (5.837 ocorrências brutas de `set mismatch rejected`).
Pares únicos `(CT_set → api_set)`: 558.
**CT codes únicos rejeitados: 162.**

Para cada CT code abaixo, mostra-se o `api_set` mais frequente (mode) + número de hits + runner-ups (api_sets alternativos retornados pelo pokemontcg.io).

Quando há **um único api_set forte** (sem runner-ups, ou runner-ups com hits muito menores), o mapeamento é alta-confiança e pode ir direto para `SET_ALIAS_TO_PTCG` no scanner v2.10.

Quando há **múltiplos api_sets concorrentes com hits comparáveis** (ex: `bs`, `c25`, `evo`, `svpromo`), o CT code provavelmente cobre **múltiplas reprints/promos** — exige investigação caso-a-caso antes de adicionar alias (risco de matching errado se mapear pro api_set errado).

## Tabela

| CT code | api_set (mode) | hits | runner-ups | Notas |
|---------|----------------|------|------------|-------|
| 1stpp | ex1 | 2 | neo1(2),base1(1),dp1(1) | 1st Edition Promos — ambíguo |
| aor | xy7 | 26 | — | Ancient Origins (XY7) — alta confiança |
| aq | base2 | 1 | ecard1(1),bw6(1),ex16(1) | Aquapolis — já tem alias `aq→ecard2`; cards rejected são mismatches reais (carta com Nº igual em base2/ecard1/etc.) |
| ba-20 | dp3 | 2 | — | Battle Arena 2020 |
| ba-2024 | svp | 7 | — | Battle Arena 2024 → SV Black Star Promos |
| bcr | bw7 | 34 | — | Boundaries Crossed (BW7) — alta confiança |
| bkp | xy9 | 15 | — | BREAKpoint (XY9) — alta confiança |
| bkt | xy8 | 38 | bw11(1),basep(1) | BREAKthrough (XY8) — alta confiança |
| blw | bw1 | 20 | ex13(2) | Black & White Base (BW1) — alta confiança |
| bog | bp | 7 | — | Best of Pokémon? Investigar |
| bs | base1 | 64 | base4(9),ru1(2),base3(2) | Base Set — base1 alta confiança; mismatches para base4 podem ser Base Set 2 reprints |
| bt | gym2 | 1 | — | Investigar |
| bus | sm3 | 47 | — | Burning Shadows (SM3) — alta confiança |
| bwbsp | sm11 | 1 | bw3(1),sm12(1) | BW Black Star Promos — ambíguo |
| c25 | cel25 | 73 | bw1(36),base1(30),pl1(28) | Celebrations 25th — `cel25` é o set base; runners são "Classic Collection" cards (reprints de eras antigas DENTRO de Celebrations) — **mapping precisa ser composto** |
| cec | sm12 | 150 | — | Cosmic Eclipse (SM12) — alta confiança |
| ces | sm7 | 61 | xy5(2) | Celestial Storm (SM7) — alta confiança |
| cg | ex14 | 84 | ex4(8),base1(4),sm7(2) | Crystal Guardians (EX14) — alta confiança |
| cinv | sm4 | 38 | — | Crimson Invasion (SM4) — alta confiança |
| clb | base4 | 15 | gym2(14),base5(12),ru1(1) | Classic Collection (Celebrations subset) — ambíguo, distribui entre múltiplos sets vintage |
| clc | sm75 | 16 | cel25(11),dp3(4) | Trainer Kit Latias-Latios? Investigar |
| clo | col1 | 47 | ex4(3),ex9(2),ex13(2) | Call of Legends (COL1) — alta confiança |
| clv | swsh12pt5 | 17 | det1(14),bw5(13) | Crown Zenith? Investigar (3 candidatos com hits similares) |
| cri | sm2 | 1 | — | Investigar |
| crz | ex12 | 8 | mcd19(7),sm4(6),xy0(1) | Crystal Zone? Investigar |
| dcr | dc1 | 34 | — | Detective Pikachu? `dc1` confere |
| deckexclusives | basep | 10 | sm9(10),sv3(10),sv10(9) | Deck Exclusives — ambíguo entre múltiplos sets (esperado para "exclusives") |
| det | det1 | 17 | hgss4(5),ex11(3) | Detective Pikachu (DET1) — alta confiança |
| dex | bw5 | 21 | bw1(1),bw9(1) | Dark Explorers (BW5) — alta confiança |
| df | ex15 | 13 | — | Dragon Frontiers (EX15) — alta confiança |
| drm | sm75 | 30 | dp3(11),ex7(2),xy7(1) | Dragon Majesty (SM75) — alta confiança |
| drv | dv1 | 4 | — | Dragon Vault (DV1) — alta confiança |
| drx | bw6 | 20 | — | Dragons Exalted (BW6) — alta confiança |
| ds | ex11 | 55 | hgss1(4),xy11(1) | Delta Species (EX11) — alta confiança |
| dx | ex8 | 75 | gym2(1),pl4(1) | Deoxys (EX8) — alta confiança |
| em | ex9 | 92 | bw7(2),col1(1) | Emerald (EX9) — alta confiança |
| epo | bw2 | 15 | bw9(7) | Emerging Powers (BW2) — alta confiança |
| evo | xy12 | 106 | xy2(10),sv7(3),swsh4(3) | Evolutions (XY12) — alta confiança |
| exbst | ex1 | 1 | ex5(1) | EX Ruby & Sapphire Booster? |
| exma | ex4 | 69 | gym2(1),sm115(1) | EX Magma vs Aqua (EX4) — alta confiança |
| fco | xy10 | 17 | sm5(1) | Fates Collide (XY10) — alta confiança |
| ffi | xy3 | 23 | me2(2) | Furious Fists (XY3) — alta confiança |
| flf | xy2 | 6 | — | Flashfire (XY2) — alta confiança |
| fli | sm6 | 56 | — | Forbidden Light (SM6) — alta confiança |
| futsal | fut20 | 8 | — | Investigar — possível promo |
| ge | dp4 | 1 | — | Great Encounters (DP4) — alta confiança |
| gen | g1 | 18 | sv7(3),basep(2),bw8(1) | Generations (G1) — alta confiança |
| gri | sm2 | 29 | xy5(2) | Guardians Rising (SM2) — alta confiança |
| gyarados | sm9 | 1 | — | Gyarados Box? |
| hggsbs | sm8 | 1 | swsh5(1) | HGSS Box Set? |
| hgs | hgss1 | 77 | — | HeartGold SoulSilver (HGSS1) — alta confiança |
| hif | sm115 | 16 | sv5(3),neo1(1),mcd22(1) | Hidden Fates (SM115) — alta confiança |
| hl | ex5 | 129 | dp1(6),ex7(5),neo1(4) | Hidden Legends (EX5) — alta confiança |
| holy | swsh7 | 5 | sv2(2),basep(1),sv4(1) | Investigar |
| hp | ex13 | 39 | hgss1(3),bw1(2) | Holon Phantoms (EX13) — alta confiança |
| kss | xy0 | 2 | — | Kalos Starter Set (XY0) — alta confiança |
| lm | ex12 | 97 | hgss4(2) | Legend Maker (EX12) — alta confiança |
| lot | sm8 | 68 | — | Lost Thunder (SM8) — alta confiança |
| lpr | sm6 | 7 | sv1(5),col1(4),sv5(4) | Investigar ambíguo |
| ltr | bw11 | 91 | bw4(3),gym2(2),xy11(1) | Legendary Treasures (BW11) — alta confiança |
| m-blk | zsv10pt5 | 30 | sv9(2),sv4(1) | Mega Black (mega-evolution promo line) |
| m-pre | sv8pt5 | 97 | base6(7),xy7(4),mcd19(3) | Mega Prerelease — runners (base6/xy7/mcd19) podem ser promos antigos reciclados como m-pre |
| m-wht | rsv10pt5 | 27 | bw3(1),sm4(1),bw2(1) | Mega White (mega-evolution promo line) |
| m24 | pl4 | 1 | — | Investigar |
| mc11 | mcd11 | 1 | — | McDonald's 2011 — trivial |
| mc12 | mcd12 | 4 | — | McDonald's 2012 |
| mc14 | mcd14 | 1 | mcd16(1) | McDonald's 2014 |
| mc15 | mcd15 | 1 | — | McDonald's 2015 |
| mc17 | mcd17 | 2 | — | McDonald's 2017 |
| mc18 | mcd18 | 2 | basep(1) | McDonald's 2018 |
| mc19 | mcd19 | 25 | — | McDonald's 2019 |
| mc21 | mcd21 | 19 | basep(9),np(5),det1(3) | McDonald's 2021 |
| md | dp5 | 6 | — | Mysterious Treasures? Verificar mapping (mt seria a sigla padrão) |
| mep | det1 | 9 | xy4(2) | Investigar |
| meproducts | sv5 | 10 | me1(4) | ME Products (mega-evolution products line) |
| mt | dp2 | 4 | — | Mysterious Treasures (DP2) — alta confiança |
| nbsp | np | 10 | xy9(3) | Nintendo Black Star Promos (NP) |
| nvi | bw3 | 47 | — | Noble Victories (BW3) — alta confiança |
| nxd | bw4 | 12 | — | Next Destinies (BW4) — alta confiança |
| p-asc | me1 | 1 | sm11(1) | Promo Ascended Heroes? |
| p-blk | zsv10pt5 | 4 | — | Promo Mega Black |
| p-pre | sv8pt5 | 8 | base6(1) | Promo Mega Prerelease |
| p-wht | rsv10pt5 | 2 | — | Promo Mega White |
| pbcr | bw7 | 3 | — | Promo BCR |
| pbkp | xy9 | 6 | — | Promo BKP |
| pbus | sm3 | 2 | — | Promo BUS |
| pcec | sm12 | 2 | — | Promo CEC |
| pces | sm7 | 3 | xy5(1) | Promo CES |
| pdp | dp1 | 3 | — | Promo DP |
| pgen | g1 | 2 | — | Promo Generations |
| phf | xy4 | 8 | — | Phantom Forces (XY4) — alta confiança |
| pk | ex16 | 53 | ex6(1),bw11(1),ex9(1) | Power Keepers (EX16) — alta confiança |
| pkm-center | svp | 67 | sv3pt5(8),sv10(5),basep(2) | Pokémon Center Exclusives — múltiplos sets, mapping primário svp |
| pl | pl1 | 7 | — | Platinum (PL1) — alta confiança |
| playprizep | sv8pt5 | 20 | sv8(14),sv10(11),sv5(10) | Play! Pokémon Prize Packs — distribuído |
| plb | bw10 | 20 | — | Plasma Blast (BW10) — alta confiança |
| plf | bw9 | 50 | — | Plasma Freeze (BW9) — alta confiança |
| pls | bw8 | 39 | — | Plasma Storm (BW8) — alta confiança |
| pltr | bw11 | 1 | — | Promo LTR |
| pplb | bw10 | 1 | — | Promo PLB |
| pplf | bw9 | 2 | — | Promo PLF |
| ppls | bw8 | 1 | — | Promo PLS |
| pr | sm11 | 9 | det1(5),basep(3),sv3pt5(3) | Promo generic — ambíguo |
| pr19 | dp4 | 1 | — | Promo 2019? |
| prc | xy5 | 36 | gym2(1) | Primal Clash (XY5) — alta confiança |
| pre-poke | svp | 12 | sm10(2),base5(1),ex8(1) | Pre-release Pokémon Center? |
| prof | sve | 8 | sm6(1),bw1(1),ex9(1) | Professor (SVE — Scarlet & Violet Energies) |
| promo-retail | swsh2 | 14 | sv6(13),sv10(11),swsh5(10) | Retail promos — ambíguo |
| pros | xy6 | 4 | — | Promo XY6? |
| prr | pl2 | 4 | — | Pre-release Rising Rivals |
| psts | xy11 | 3 | — | Promo STS |
| pwc | basep | 1 | — | Pokémon World Championships? |
| rc | det1 | 4 | xy9(4),mcd16(3) | Investigar |
| rclt | tk2b | 7 | bw4(2),ru1(1) | Trainer Kit? |
| rg | ex6 | 103 | ex11(7),gym2(3),pl2(3) | Fire Red Leaf Green (EX6) — alta confiança |
| ros | xy6 | 27 | base3(1) | Roaring Skies (XY6) — alta confiança |
| rr | pl2 | 2 | — | Rising Rivals (PL2) — alta confiança |
| rs | ex1 | 51 | xy5(7),ex8(6),dp3(3) | Ruby & Sapphire (EX1) — alta confiança |
| sa-gym | sv8 | 2 | sv1(1),swsh12(1),sm12(1) | SV: Surging Attack Gym? — ambíguo |
| sft | dp7 | 18 | pl3(1),dp5(1) | Stormfront (DP7) — alta confiança |
| shbs | base1 | 33 | base4(1) | Shadowless Base Set — mesma carta de base1 com flag shadowless; matching está correto, mas idealmente alias `shbs→base1` com flag adicional |
| shf | sm12 | 5 | sm11(2) | Shining Fates? Verificar |
| si | si1 | 18 | — | Investigar |
| skg | swsh35 | 1 | — | Skyridge alias hit no api errado |
| slg | sm35 | 45 | basep(2) | Shining Legends (SM35) — alta confiança |
| smbs | sv3pt5 | 2 | base6(1),sm9(1) | SM Black Star Promos |
| ss | ex2 | 71 | pop5(5),ex12(4),pl3(4) | Sandstorm (EX2) — alta confiança |
| sts | xy11 | 18 | — | Steam Siege (XY11) — alta confiança |
| sum | sm1 | 47 | — | Sun & Moon Base (SM1) — alta confiança |
| sv | pl3 | 30 | — | Supreme Victors (PL3) — alta confiança (CUIDADO: NÃO confundir com "sv" Scarlet & Violet) |
| svi | sve | 2 | — | Scarlet & Violet Energies (SVE) |
| svproducts | sv4pt5 | 2 | — | SV Products |
| svpromo | svp | 503 | sv8pt5(77),sv10(63),xy12(26) | **maior volume** — SV Black Star Promos (SVP); runners são cards de outros sets com mesmo número |
| sw | dp3 | 5 | — | Secret Wonders (DP3) — alta confiança |
| swshbs | bw4 | 6 | swsh3(3),swsh7(2),xy6(1) | SWSH Black Star Promos — ambíguo |
| teu | sm9 | 78 | — | Team Up (SM9) — alta confiança |
| tot23 | sv1 | 1 | — | Trick or Trade 2023 |
| tot24 | sv3 | 6 | sv6(3),sv4pt5(2),sv2(1) | Trick or Trade 2024 — ambíguo |
| tri | hgss4 | 38 | ex11(2),pl4(1) | Triumphant (HGSS4) — alta confiança |
| trickortrade | swsh2 | 1 | — | Trick or Trade |
| trr | ex7 | 131 | ex10(4),hgss1(3),dp3(2) | Team Rocket Returns (EX7) — alta confiança |
| uf | ex10 | 80 | hgss1(2),ex11(2),neo4(1) | Unseen Forces (EX10) — alta confiança |
| ul | hgss2 | 30 | base1(3),dp3(1),base3(1) | Unleashed (HGSS2) — alta confiança |
| unb | sm10 | 62 | xy11(1),dp3(1) | Unbroken Bonds (SM10) — alta confiança |
| und | hgss3 | 19 | swsh4(1),sm115(1) | Undaunted (HGSS3) — alta confiança |
| unm | sm11 | 65 | — | Unified Minds (SM11) — alta confiança |
| upr | sm5 | 49 | pl1(1) | Ultra Prism (SM5) — alta confiança |
| wcd2004 | ex4 | 15 | ex1(12),ex2(7),ecard3(5) | World Championship Deck 2004 — distribuído entre múltiplos sets (decks de torneio mixam) |
| wcd2005 | ex7 | 2 | — | WCD 2005 |
| wcd2006 | ex12 | 3 | ex10(2),ex8(2),ex16(1) | WCD 2006 |
| wcd2007 | ex11 | 2 | ex8(1),ex16(1) | WCD 2007 |
| wcd2008 | ex14 | 1 | — | WCD 2008 |
| wcd2010 | dp6 | 1 | — | WCD 2010 |
| wcd2015 | bw9 | 1 | bw10(1) | WCD 2015 |
| wcd2023 | swsh9 | 1 | — | WCD 2023 |
| wiz | basep | 72 | ex7(4),xy6(3),dv1(2) | WotC Promos (Wizards Black Star) — alta confiança |
| wpromos | gym2 | 1 | — | Investigar |
| xy-en | xy1 | 6 | sv7(2) | XY Base EN |
| xybsp | swsh12pt5 | 5 | sv7(2),bw4(2),xy4(2) | XY Black Star Promos — ambíguo |
| xytkas | tk1a | 3 | — | XY Trainer Kit Sylveon (TK1A) |
| xytkn | ecard1 | 1 | — | XY Trainer Kit Noivern? |
| xytkos | tk1b | 1 | — | XY Trainer Kit Wigglytuff (TK1B) |

## Próximos passos sugeridos para v2.10

1. **Batch alta-confiança (~110 entries):** todas as linhas com `runner-ups` vazio OU runners com hits ≤ 10% do mode podem ir direto para `SET_ALIAS_TO_PTCG`. Exemplos: `bcr→bw7`, `bkp→xy9`, `cec→sm12`, `ces→sm7`, `evo→xy12`, `lot→sm8`, `nvi→bw3`, `nxd→bw4`, `phf→xy4`, etc.
2. **Investigação caso-a-caso (~50 entries):** CT codes com múltiplos api_sets concorrentes (`bs`, `c25`, `clb`, `clv`, `crz`, `deckexclusives`, `m-pre`, `playprizep`, `pkm-center`, `promo-retail`, `pr`, `svpromo`, `wcd2004`, `xybsp`, etc.). Esses provavelmente exigem matching composto (não 1-pra-1) ou são promos que mixam várias eras.
3. **CUIDADO especial com `sv`:** CT usa `sv` para **Supreme Victors (PL3)**, NÃO Scarlet & Violet base. Confirmar antes de adicionar alias.
4. **`svpromo` é o maior volume (503 hits)** — confirma que promos modernas (SV-era) estão sendo rejeitadas em massa.
