# MaleCNS escape-pathway card v1

M04 freezes an auditable **ports-only candidate circuit** over the accepted MaleCNS v1.0 graph. It does not implement or tune neural dynamics.

## Evidence boundaries

- **SOURCE / MEASURED DATA:** pinned source bytes, source graph pair edges, and raw contact counts.
- **BIOLOGICAL ANNOTATION / PREDICTION:** MaleCNS canonical types, aliases, sides, classes, transmitter predictions, and confidences.
- **PROJECT INFERENCE:** exact canonical-type selection and the G-MAP conclusion.
- **MODEL ASSUMPTION:** effective transmitter signs, ports-only intervention, candidate LIF/encoder/decoder, and future calibration grid.
- **LITERATURE ROLE EVIDENCE:** functional roles from the cited papers; literature is not the authority for MaleCNS body IDs.

Mapping semantic SHA-256: `6652462228ddf9af863fae95608fd6cacb44fbd86fd12d0799ec65d8dabcef3d`.

## Exact MaleCNS v1.0 populations

### LC4

Exact canonical `type == LC4` matches: **126**. Side is copied from `somaSide`, never inferred. Side counts: `{'L': 71, 'R': 55}`.

12032 12349 12824 14888 15018 16128 16138 16628 16809 16917 17054 17266 17270 17340 17364 17478 17548 17608 17653 17668 17860 17926 17987 18127 18189 18396 18432 18478 19260 19420 19543 19550 19634 19794 19954 20016 20282 20399 20440 20542 20572 20588 20673 20808 20859 20917 20967 20976 21151 21165 21225 21287 21313 21336 21721 21804 22034 22194 22328 22772 22847 22922 22966 22975 23098 23202 23226 23392 23792 23929 24338 24523 25584 26112 27624 27750 27829 28945 28980 29417 29469 29514 29563 30087 30480 30803 31262 31301 31308 31429 32597 33137 34845 35262 35616 37587 38065 77614 81112 100485 107513 111787 511914 512366 512705 514508 514956 515476 515900 516909 517752 518016 518439 518544 518730 518983 519650 519931 520449 524899 526286 527408 530029 532254 533129 535341

Source evidence fields: `type`, `instance`, `synonyms`, `somaSide`, `rootSide`, `superclass`, `class`, `subclass`, `supertype`, `flywireType`, `hemibrainType`, `mancType`, `matchingNotes`, `status`, and `statusLabel`. Full per-body excerpts are in `evidence/M04/annotation-excerpts.json`.

### LPLC2

Exact canonical `type == LPLC2` matches: **185**. Side is copied from `somaSide`, never inferred. Side counts: `{'L': 94, 'R': 91}`.

11498 12384 13132 13726 13764 14030 14102 14465 15804 17059 17544 17551 17774 17775 17880 17990 18672 18900 18929 18936 19034 19146 19229 19249 19549 19589 19608 19787 19830 19842 19911 20047 20103 20162 20182 20240 20269 20329 20334 20471 20535 20584 20694 20749 20799 21045 21299 21318 21361 21562 21703 21769 21808 21862 21899 22218 22253 22261 22557 22677 23247 23349 23497 23550 23590 23665 23878 23919 24118 24187 24268 24308 24401 24568 24605 24800 24840 25027 25136 25209 25253 25267 25286 25316 25497 25511 25524 25572 25575 25636 25854 26147 26393 26416 26528 26730 26915 27023 27355 27399 27471 27566 27716 27796 28003 28011 28044 28188 28741 28871 29014 29183 29216 29287 29319 29391 29598 29702 29753 29815 29873 29955 29986 30041 30207 30512 30893 30895 30938 31105 31257 31563 31964 31988 32223 32237 32507 32737 33185 33303 33396 33406 33439 33694 33965 34051 34110 34372 34407 34655 34681 35294 35632 35680 35838 35889 37431 37613 37925 38542 39620 40811 40841 41097 50287 55627 95241 100103 111903 112292 129687 134521 514670 515971 517078 517079 517819 518731 520764 521115 524366 525844 531014 533895 536444

Source evidence fields: `type`, `instance`, `synonyms`, `somaSide`, `rootSide`, `superclass`, `class`, `subclass`, `supertype`, `flywireType`, `hemibrainType`, `mancType`, `matchingNotes`, `status`, and `statusLabel`. Full per-body excerpts are in `evidence/M04/annotation-excerpts.json`.

### DNp01

Exact canonical `type == DNp01` matches: **2**. Side is copied from `somaSide`, never inferred. Side counts: `{'L': 1, 'R': 1}`.

10001 10010

Source evidence fields: `type`, `instance`, `synonyms`, `somaSide`, `rootSide`, `superclass`, `class`, `subclass`, `supertype`, `flywireType`, `hemibrainType`, `mancType`, `matchingNotes`, `status`, and `statusLabel`. Full per-body excerpts are in `evidence/M04/annotation-excerpts.json`.

## Direct pathway evidence

- **LC4 -> DNp01:** 126 pair edges; 6362 raw contacts; 126 executable nonzero edges; 0 disabled edges; disabled contact mass 0.
  - DNp01 `10001` (R): 55 edges, 2580 contacts.
  - DNp01 `10010` (L): 71 edges, 3782 contacts.
  - Presynaptic consensus transmitter/sign coverage: `{'acetylcholine': 126}` / `{'1': 126}`.
- **LPLC2 -> DNp01:** 185 pair edges; 4862 raw contacts; 185 executable nonzero edges; 0 disabled edges; disabled contact mass 0.
  - DNp01 `10001` (R): 91 edges, 2220 contacts.
  - DNp01 `10010` (L): 94 edges, 2642 contacts.
  - Presynaptic consensus transmitter/sign coverage: `{'acetylcholine': 185}` / `{'1': 185}`.

All direct LC4/LPLC2 edges use predicted/annotated consensus acetylcholine and accepted effective sign `+1`. Transmitter identity is biological annotation/prediction; the effective sign is the accepted M03 model assumption. No sign was changed for M04.

## Ports-only circuit and omitted context

The induced circuit contains 313 nodes, 20607 internal pair edges, and 79112 internal contacts. Internal executable nonzero/disabled edges are 20607/0.

Cut incoming context is 146852 pair edges and 614628 contacts; 1510 edges / 2513 contacts are disabled by the accepted transform.

Cut outgoing context is 47620 pair edges and 254696 contacts; 0 edges / 0 contacts are disabled.

This omitted recurrent and contextual mass is an explicit circuit intervention, not optimization noise. No generic neighbor, strong-neighbor, or contact-threshold expansion is applied.

## Literature role evidence

- Ache et al., *Current Biology* 29 (2019), DOI [10.1016/j.cub.2019.01.079](https://doi.org/10.1016/j.cub.2019.01.079): LC4 velocity-like and LPLC2 size-like looming contributions, direct inputs to Giant Fiber, and pathway relevance to GF-mediated escape.
- Klapoetke et al., *Nature* 551 (2017), DOI [10.1038/nature24626](https://doi.org/10.1038/nature24626): LPLC2 looming selectivity and projection near Giant Fiber.

Those papers ground biological roles only. Exact body IDs and sides above come from pinned MaleCNS v1.0 annotations; no FlyWire, hemibrain, FAFB, MANC, or other-release ID was transferred.

## Limitations

The candidate omits early visual computation, retinotopy, most upstream and downstream context, compartmental morphology, electrical coupling, neuromodulation, plasticity, body mechanics, and natural sensorimotor feedback. Transmitter values are aggregate predictions/annotations, not direct physiological measurements for this experiment. M04 does not establish numerical stability, calibrated activity, escape performance, or natural behavior.

The mapping establishes the declared modeled pathway in the pinned connectome.

It does NOT establish that the eventual simplified dynamics reproduce natural fly behavior.
