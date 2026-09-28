# V2A context follow-up

## Outside-circuit neurons that spiked

| Body ID | Type | Instance | Side | Spike ticks | To DNp01 | From DNp01 | To visual | From visual |
|---:|---|---|---|---|---:|---:|---:|---:|
| 10283 | DNp103 | DNp103(PVLP119)_R | R | 1161, 1203 | 155 | 20 | 27 | 3050 |
| 10417 | DNp103 | DNp103(PVLP119)_L | L | 1197 | 128 | 10 | 14 | 2350 |
| 10943 | AVLP531 | AVLP531_R | R | 1160, 1204 | 0 | 0 | 0 | 3034 |
| 11137 | DNp04 | DNp04_R | R | 1134, 1169, 1192 | 0 | 0 | 21 | 6227 |
| 11677 | PVLP151 | PVLP151_R | R | 1200 | 168 | 6 | 60 | 2420 |
| 12275 | PVLP151 | PVLP151_L | L | 1196 | 144 | 3 | 539 | 2530 |
| 12427 | PVLP069 | PVLP069_L | L | 1072, 1133, 1164, 1194 | 0 | 2 | 0 | 4858 |
| 12951 | PVLP069 | PVLP069_R | R | 1080, 1138, 1180, 1207 | 0 | 0 | 0 | 4198 |
| 16659 | PVLP011 | PVLP011_R | R | 968, 1031, 1075, 1110, 1137, 1161, 1181, 1199 | 10 | 0 | 5656 | 7400 |
| 523564 | PVLP011 | PVLP011_L | L | 1073, 1133, 1164, 1190 | 4 | 0 | 4674 | 5234 |
| 531898 | DNp04 | DNp04_L | L | 1129, 1164, 1186, 1201 | 2 | 3 | 18 | 8768 |

## DNp01 one-tick shift

- DNp01 10001 spikes at tick 1135 in the circuit and tick 1136 in the full graph. The first differing arrival is at end tick 971, with full-minus-circuit increment -0.01. At the circuit spike tick, the circuit state crosses threshold and resets while the full-graph voltage is 0.9678246486367901, below threshold. The accumulated input history therefore accounts for the one-tick delay.
  Differing presynaptic histories include 91 sources present in the accepted circuit and 4 outside sources. Outside source body IDs: 10283, 11677, 12275, 16659. No single edge is claimed as the sole cause.
- DNp01 10010 spikes at tick 1130 in the circuit and tick 1131 in the full graph. The first differing arrival is at end tick 1076, with full-minus-circuit increment -0.004. At the circuit spike tick, the circuit state crosses threshold and resets while the full-graph voltage is 0.9931638358746774, below threshold. The accumulated input history therefore accounts for the one-tick delay.
  Differing presynaptic histories include 80 sources present in the accepted circuit and 6 outside sources. Outside source body IDs: 10283, 10417, 11677, 12275, 523564, 531898. No single edge is claimed as the sole cause.

Full input traces are in `context-followup.json`.
