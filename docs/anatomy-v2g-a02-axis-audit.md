# Anatomical landmark audit, repair attempt a02

Status: STOP, anatomical landmark ordering conflict. No composite assets have
been exported. The a01 view is a ventral whole-CNS projection, not a frontal
brain view. Its existing frame metadata and previews remain superseded and must
not be used as the proposed composite layout.

External review: sources, pruning, budgets, N-STRENGTH demo, recompute_v2e and
acceptance are ACCEPTED. One defect blocks acceptance: the display frame is
mislabeled. The projection is not a frontal view. It is a ventral view of the
whole CNS, with the body's anterior-posterior axis vertical.

## Reproduction and fixed checks

```sh
uv run --offline python experiments/v2g_anatomy.py --audit-frame
```

Expected exit: 1, with the contradiction below. The command verifies the pinned
input hashes, decodes the original ROI chunks at 1.024 µm, and computes each
label's 3D centroid using occupied voxel centres. It reads the official volume
offsets and resolutions; it does not compute centroids from projected contours.
Every centroid, voxel count, set contrast and individual comparison is in
[the machine-readable report](anatomy-v2g-a02-axis-audit.json).

The existing annotated R/L soma rule supplies the horizontal axis and sign.
For each panel the anterior/posterior set contrast chooses the largest remaining
source coordinate contrast. The remaining coordinate is dorsal/ventral. Signs
come from the set contrasts once. Every individual dorsal/ventral and
anterior/posterior named pair is then checked against those signs, including
paired aL/bL landmarks. A group mean cannot hide a reversed pair.

## Axis assignments

These are measured assignments, not an implemented composite display frame.
Positive directions are listed; the corresponding negative directions are
fly right, anterior and dorsal.

| Panel | Source axis | Sign | Positive anatomical direction | Landmark evidence |
|---|---|---:|---|---|
| Both | x | +1 | Fly left, viewer right | Existing soma-side rule: R 97.19568567026194%, L 99.51969260326609% |
| brain | z | +1 | posterior | AL(L), AL(R), EB, aL(L), aL(R), bL(L), bL(R), gL(L), gL(R) to CA(L), CA(R), PB: 125.512058716226 µm |
| brain | y | +1 | ventral | CA(L), CA(R), PB, SMP(L), SMP(R) to AL(L), AL(R), GNG: 149.925939706448 µm |
| VNC | z | +1 | posterior | LegNp(T1)(L), LegNp(T1)(R) to LegNp(T3)(L), LegNp(T3)(R): 339.873217928938 µm |
| VNC | y | +1 | ventral | IntTct, LTct, NTct(UTct-T1)(L), NTct(UTct-T1)(R), WTct(UTct-T2)(L), WTct(UTct-T2)(R), HTct(UTct-T3)(L), HTct(UTct-T3)(R) to LegNp(T1)(L), LegNp(T1)(R), LegNp(T2)(L), LegNp(T2)(R), LegNp(T3)(L), LegNp(T3)(R), mVAC(T1)(L), mVAC(T1)(R), mVAC(T2)(L), mVAC(T2)(R), mVAC(T3)(L), mVAC(T3)(R): 69.895980084670 µm |

## Blocking relation

LTct has source y = 438.7949197017007 µm. LegNp(T3)(R) has source
y = 429.72174902137596 µm. With the inferred +y ventral direction, LTct
is 9.073170680324722 µm more ventral than LegNp(T3)(R), reversing their
requested dorsal/ventral ordering. Reversing y would reverse the other
tectulum/ventral comparisons. The overall ventral-minus-dorsal set contrast is
+69.8959800846705 µm, so the broad axis assignment and this individual exception
are both reported. This is not evidence of a source-data bug.

There are 144 individual comparisons and one contradiction. The brain's
anterior/posterior, dorsal/ventral and paired aL-above-bL checks pass. The VNC
T1-before-T3 checks pass. No landmark is dropped, moved or renamed to obtain a
passing gate. The unit tests explicitly reproduce the failed gate; their passing
does not mean the anatomical gate passes.

Per the owner's stop condition, the composite split, neck alignment, giant-fiber
soma-versus-branch-point check, lamina truncation check, re-export, new previews
and browser screenshots are not run. Existing a01 assets are unchanged. There is
no a02 acceptance claim or a02 review ZIP. Resolving the incompatible landmark
ordering requires the owner's anatomical direction before continuing.

## Original source centroids

All values below are micrometres in the original XYZ frame. Names are official
dataset labels. These include every observed ROI, not only the gate landmarks.

| Volume | Label | Official name | Voxels | Source x µm | Source y µm | Source z µm |
|---|---:|---|---:|---:|---:|---:|
| VNC | 4 | CV-posterior | 360804 | 401.529564594628 | 425.964717907784 | 492.098564938304 |
| VNC | 5 | LegNp(T1)(L) | 983634 | 469.905380383354 | 466.835627983579 | 595.087846414418 |
| VNC | 6 | LegNp(T1)(R) | 1005854 | 327.019104466453 | 466.213344266663 | 599.594938907635 |
| VNC | 7 | LegNp(T2)(L) | 794175 | 458.831059491926 | 484.498709830957 | 771.615323111405 |
| VNC | 8 | LegNp(T2)(R) | 771429 | 340.258366890537 | 475.382396544594 | 775.187871941553 |
| VNC | 9 | LegNp(T3)(L) | 956649 | 451.375189520921 | 439.127762077836 | 935.175389259802 |
| VNC | 10 | LegNp(T3)(R) | 998085 | 360.513595567512 | 429.721749021376 | 939.253831920127 |
| VNC | 11 | Ov(L) | 151143 | 440.166135434655 | 471.194277842838 | 684.575185513057 |
| VNC | 12 | Ov(R) | 151866 | 352.541880657948 | 467.532732909275 | 686.133058986211 |
| VNC | 13 | IntTct | 643674 | 400.704730009290 | 408.387711294848 | 696.070618803929 |
| VNC | 14 | LTct | 489039 | 397.973925515143 | 438.794919701701 | 688.637481035255 |
| VNC | 15 | NTct(UTct-T1)(L) | 73078 | 447.436448288131 | 392.869304578669 | 639.791985549687 |
| VNC | 16 | NTct(UTct-T1)(R) | 69259 | 354.133357975137 | 387.051500483692 | 644.463771524278 |
| VNC | 17 | WTct(UTct-T2)(L) | 365339 | 446.052340166257 | 383.998210363525 | 717.458593229850 |
| VNC | 18 | WTct(UTct-T2)(R) | 380665 | 357.809254772569 | 377.315897263999 | 719.077614175193 |
| VNC | 19 | HTct(UTct-T3)(L) | 105012 | 431.160684112292 | 393.975233611397 | 817.488048146878 |
| VNC | 20 | HTct(UTct-T3)(R) | 112441 | 372.327118542169 | 388.843415907009 | 816.151518823205 |
| VNC | 21 | ANm | 971403 | 405.329501514819 | 382.137916988109 | 947.968033996189 |
| VNC | 22 | mVAC(T1)(L) | 38561 | 433.208257462203 | 477.464729649127 | 621.603438085112 |
| VNC | 23 | mVAC(T1)(R) | 40770 | 359.732204660289 | 477.834090556782 | 621.886175913662 |
| VNC | 24 | mVAC(T2)(L) | 40232 | 421.954787035196 | 480.703172797773 | 735.450763173593 |
| VNC | 25 | mVAC(T2)(R) | 36875 | 375.741172718644 | 476.883159213559 | 732.883214752542 |
| VNC | 26 | mVAC(T3)(L) | 16584 | 421.689917993247 | 462.446278822962 | 857.735347805113 |
| VNC | 27 | mVAC(T3)(R) | 19795 | 384.471236574893 | 458.495030058095 | 862.053300732508 |
| brain | 1 | AL(L) | 350626 | 448.695252034932 | 215.246110716262 | 121.186348987240 |
| brain | 2 | AL(R) | 349158 | 327.795539394773 | 230.409273417765 | 127.194080754272 |
| brain | 3 | AME(L) | 3941 | 572.838877442274 | 260.127049987313 | 207.898113169246 |
| brain | 4 | AME(R) | 15556 | 212.097678580612 | 268.430843918745 | 219.978055026999 |
| brain | 5 | AMMC(L) | 92025 | 458.969557576745 | 284.067186264602 | 216.502525704971 |
| brain | 6 | AMMC(R) | 102296 | 324.792897786815 | 294.929077344178 | 218.139227653085 |
| brain | 7 | AOTU(L) | 60495 | 523.046580907513 | 125.474835804612 | 148.293421935697 |
| brain | 8 | AOTU(R) | 59631 | 253.316531334373 | 133.568548439570 | 155.556617732388 |
| brain | 9 | ATL(L) | 11996 | 414.229511170390 | 125.779569189730 | 239.310148716239 |
| brain | 10 | ATL(R) | 11046 | 360.362898424769 | 127.592940068803 | 239.431705956907 |
| brain | 11 | AVLP(L) | 519526 | 533.156425079784 | 199.265887135581 | 171.782596043316 |
| brain | 12 | AVLP(R) | 519183 | 245.609865284495 | 209.922117295828 | 178.121903929828 |
| brain | 13 | BU(L) | 6547 | 448.473758362609 | 150.050409653276 | 167.845361845120 |
| brain | 14 | BU(R) | 6681 | 326.980856757970 | 157.991888639425 | 168.551610836701 |
| brain | 15 | CA(L) | 45659 | 472.762122692131 | 103.283258590858 | 265.388251516678 |
| brain | 16 | CA(R) | 58662 | 300.981759912720 | 111.516239337220 | 271.396430534247 |
| brain | 17 | CAN(L) | 11620 | 415.441999311532 | 258.806394492255 | 236.215209638554 |
| brain | 18 | CAN(R) | 13532 | 369.987045817322 | 264.543044634939 | 235.538615430092 |
| brain | 19 | CRE(L) | 105030 | 430.773254727221 | 131.837976958964 | 131.184822317433 |
| brain | 20 | CRE(R) | 99510 | 344.426572766556 | 138.690267751985 | 133.420048155964 |
| brain | 21 | EB | 64726 | 388.196507863919 | 163.392389580694 | 163.652305163304 |
| brain | 22 | EPA(L) | 31284 | 458.385004475131 | 195.967950901419 | 205.166439074287 |
| brain | 23 | EPA(R) | 25654 | 322.623266547127 | 203.083301161612 | 203.791646994621 |
| brain | 24 | FB | 175461 | 388.005421512473 | 151.396711337562 | 194.995203355731 |
| brain | 25 | FLA(L) | 58919 | 415.108690371527 | 275.273659905973 | 188.060661450466 |
| brain | 26 | FLA(R) | 60714 | 366.171261718879 | 282.383069736799 | 187.511309813223 |
| brain | 27 | GA(L) | 2767 | 482.034029634984 | 172.927768702566 | 142.500128659198 |
| brain | 28 | GA(R) | 2834 | 296.248547635850 | 182.916606916020 | 143.733973182781 |
| brain | 29 | GNG | 1293587 | 389.802027979564 | 322.790051242012 | 229.154343647547 |
| brain | 30 | GOR(L) | 29135 | 432.203477604256 | 186.491734065557 | 218.187301870602 |
| brain | 31 | GOR(R) | 29278 | 348.930430767129 | 191.345791379193 | 216.941069745201 |
| brain | 32 | IB | 129415 | 387.899860263493 | 169.706693536298 | 253.192448603330 |
| brain | 33 | ICL(L) | 135168 | 458.026962121212 | 152.153090909091 | 222.161780303030 |
| brain | 34 | ICL(R) | 140834 | 320.819671158953 | 159.166990243833 | 224.887316642288 |
| brain | 35 | IPS(L) | 119331 | 450.423666608006 | 247.007415139402 | 279.161998541871 |
| brain | 36 | IPS(R) | 131501 | 333.279154379054 | 254.690080349199 | 282.486968038266 |
| brain | 37 | LA(L) | 409546 | 688.841349045040 | 238.333718449210 | 205.353287943235 |
| brain | 38 | LA(R) | 375740 | 89.289717698408 | 283.210528471816 | 213.741964038963 |
| brain | 39 | LAL(L) | 171956 | 454.889085114797 | 197.914112726511 | 166.074076252064 |
| brain | 40 | LAL(R) | 159149 | 325.034077399167 | 208.467233096030 | 168.782019767639 |
| brain | 41 | LH(L) | 175967 | 550.321946092165 | 108.308159416254 | 232.372119590605 |
| brain | 42 | LH(R) | 176705 | 223.897334880168 | 119.821371891005 | 238.326199258651 |
| brain | 43 | LO(L) | 811253 | 566.154581557171 | 243.120200874450 | 274.430008808596 |
| brain | 44 | LO(R) | 838553 | 212.190018109768 | 250.650205599408 | 280.308293739334 |
| brain | 45 | LOP(L) | 394316 | 602.059212773512 | 261.574769474229 | 311.280891224297 |
| brain | 46 | LOP(R) | 430945 | 177.987406689949 | 269.535430386708 | 319.776917722679 |
| brain | 47 | ME(L) | 2418649 | 643.449560067625 | 263.300509545618 | 254.932582915504 |
| brain | 48 | ME(R) | 2555781 | 133.830054402940 | 279.483217242792 | 265.469805283003 |
| brain | 49 | NO | 16286 | 389.680414589218 | 195.571173277662 | 188.578786196733 |
| brain | 50 | PB | 32468 | 388.116216336085 | 129.426182086978 | 256.954740914131 |
| brain | 51 | PED(L) | 21280 | 484.587308270677 | 144.596547368421 | 203.067669172932 |
| brain | 52 | PED(R) | 21363 | 293.664846323082 | 154.092922529607 | 206.055494078547 |
| brain | 53 | PLP(L) | 272415 | 503.907990499789 | 176.522408119964 | 255.681880190151 |
| brain | 54 | PLP(R) | 311037 | 274.726891733138 | 185.502643505435 | 259.299058980121 |
| brain | 55 | PRW | 104091 | 388.691737191496 | 283.109064799070 | 153.484128464517 |
| brain | 56 | PVLP(L) | 291425 | 523.785571505533 | 201.084188000343 | 212.891536086472 |
| brain | 57 | PVLP(R) | 267490 | 256.313317432427 | 210.165194960559 | 218.743764626715 |
| brain | 58 | ROB(L) | 1241 | 463.033244157937 | 165.843029814666 | 126.853466559226 |
| brain | 59 | ROB(R) | 1075 | 314.816178604651 | 172.678310697674 | 130.400922790698 |
| brain | 60 | RUB(L) | 737 | 446.803712347354 | 145.846360922659 | 139.221622795115 |
| brain | 61 | RUB(R) | 795 | 330.343044025157 | 152.697720754717 | 142.966500628931 |
| brain | 62 | SAD | 328084 | 389.120920739811 | 291.755653991051 | 204.551119347484 |
| brain | 63 | SCL(L) | 142833 | 481.765832377672 | 119.165592041055 | 212.480623721409 |
| brain | 64 | SCL(R) | 147846 | 293.401224950286 | 127.457199518418 | 216.234022536964 |
| brain | 65 | SIP(L) | 152500 | 466.292124957377 | 99.805660747541 | 171.497250413115 |
| brain | 66 | SIP(R) | 169016 | 305.588976380934 | 105.891806314195 | 170.729207554314 |
| brain | 67 | SLP(L) | 337791 | 507.585610273808 | 83.311362967042 | 204.498513696339 |
| brain | 68 | SLP(R) | 343358 | 265.630961596934 | 90.714456444877 | 208.469651943453 |
| brain | 69 | SMP(L) | 282776 | 419.858001188220 | 91.408002263276 | 178.991963334936 |
| brain | 70 | SMP(R) | 295659 | 351.038145539287 | 95.479011482823 | 178.220600570252 |
| brain | 71 | SPS(L) | 191425 | 438.606620786209 | 201.735095917461 | 260.940403479169 |
| brain | 72 | SPS(R) | 204272 | 340.560347144983 | 209.155183206705 | 262.581307433226 |
| brain | 73 | VES(L) | 158509 | 432.017417509416 | 237.459213445293 | 204.337569122258 |
| brain | 74 | VES(R) | 164076 | 349.957454642970 | 245.022736975548 | 205.421941636802 |
| brain | 75 | WED(L) | 198466 | 491.955122348412 | 256.696681789324 | 231.190704705088 |
| brain | 76 | WED(R) | 205308 | 290.887986439885 | 265.505402147018 | 235.157833343075 |
| brain | 77 | a'L(L) | 11345 | 461.428525694138 | 99.622383076245 | 152.392817276333 |
| brain | 78 | a'L(R) | 15041 | 310.833971145536 | 105.645639518649 | 151.292987434346 |
| brain | 79 | aL(L) | 23759 | 460.140255061240 | 101.649142809041 | 161.439381792163 |
| brain | 80 | aL(R) | 28576 | 312.817487122060 | 104.445276595745 | 162.317796192609 |
| brain | 81 | b'L(L) | 22477 | 427.845418516706 | 141.402955910486 | 136.785366018597 |
| brain | 82 | b'L(R) | 21247 | 349.677830470184 | 144.889300889537 | 139.727660375582 |
| brain | 83 | bL(L) | 17993 | 437.341419440894 | 155.358692824987 | 132.271883510254 |
| brain | 84 | bL(R) | 18151 | 341.048105338549 | 161.397288083301 | 136.483132830147 |
| brain | 85 | gL(L) | 74679 | 441.597405000067 | 140.366179086490 | 121.255749434245 |
| brain | 86 | gL(R) | 68172 | 329.782690840814 | 145.850348412838 | 125.809061784897 |
| brain | 93 | AB(R) | 1371 | 381.704402625821 | 179.231743253100 | 195.315489423778 |
| brain | 94 | AB(L) | 362 | 395.131049723757 | 177.457502762431 | 196.129944751381 |
| brain | 95 | CV-anterior | 229408 | 392.584713070163 | 385.290520853676 | 379.775138513042 |
| brain | 96 | CRN | 25978 | 390.157126183694 | 313.424136731080 | 385.318215720995 |
