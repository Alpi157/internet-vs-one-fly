# DNa01 annotation conflict

Status: UNRESOLVED. No claimant is selected.

## Claimants and totals

| Body ID | Type | Instance | Side | Total input contacts | Total output contacts |
|---:|---|---|---|---:|---:|
| 10442 | DNa01 | DNa01(VES006)_L | L | 12443 | 6244 |
| 10760 | DNa01 | DNa01(VES006)_R | R | 13339 | 5650 |
| 11563 | DNae001 | DNae001(DNa01)_R | R | 5710 | 3996 |
| 512071 | DNae001 | DNae001(DNa01)_L | L | 5763 | 4002 |

## MDN input to each claimant

| Claimant | MDN | Present | Contacts | Sign |
|---:|---:|---|---:|---|
| 10442 | 10763 | True | 9 | EXCITATORY |
| 10442 | 11332 | True | 4 | EXCITATORY |
| 10442 | 11288 | False | 0 | EXCITATORY |
| 10442 | 12348 | False | 0 | EXCITATORY |
| 10760 | 10763 | True | 4 | EXCITATORY |
| 10760 | 11332 | True | 1 | EXCITATORY |
| 10760 | 11288 | True | 11 | EXCITATORY |
| 10760 | 12348 | True | 14 | EXCITATORY |
| 11563 | 10763 | True | 1 | EXCITATORY |
| 11563 | 11332 | True | 1 | EXCITATORY |
| 11563 | 11288 | True | 1 | EXCITATORY |
| 11563 | 12348 | False | 0 | EXCITATORY |
| 512071 | 10763 | False | 0 | EXCITATORY |
| 512071 | 11332 | False | 0 | EXCITATORY |
| 512071 | 11288 | False | 0 | EXCITATORY |
| 512071 | 12348 | False | 0 | EXCITATORY |

## DNp09 connections

| Claimant | DNp09 | Direction | Present | Contacts | Sign |
|---:|---:|---|---|---:|---|
| 10442 | 10783 | from_dnp09 | False | 0 | EXCITATORY |
| 10442 | 10783 | to_dnp09 | False | 0 | EXCITATORY |
| 10442 | 11177 | from_dnp09 | False | 0 | EXCITATORY |
| 10442 | 11177 | to_dnp09 | False | 0 | EXCITATORY |
| 10760 | 10783 | from_dnp09 | False | 0 | EXCITATORY |
| 10760 | 10783 | to_dnp09 | False | 0 | EXCITATORY |
| 10760 | 11177 | from_dnp09 | True | 3 | EXCITATORY |
| 10760 | 11177 | to_dnp09 | False | 0 | EXCITATORY |
| 11563 | 10783 | from_dnp09 | False | 0 | EXCITATORY |
| 11563 | 10783 | to_dnp09 | False | 0 | EXCITATORY |
| 11563 | 11177 | from_dnp09 | False | 0 | EXCITATORY |
| 11563 | 11177 | to_dnp09 | False | 0 | EXCITATORY |
| 512071 | 10783 | from_dnp09 | True | 3 | EXCITATORY |
| 512071 | 10783 | to_dnp09 | True | 2 | EXCITATORY |
| 512071 | 11177 | from_dnp09 | False | 0 | EXCITATORY |
| 512071 | 11177 | to_dnp09 | False | 0 | EXCITATORY |

## Annotation fields that differ

- `bodyId`: 10442=10442; 10760=10760; 11563=11563; 512071=512071
- `flywireType`: 10442="DNa01"; 10760="DNa01"; 11563="DNae001"; 512071="DNae001"
- `group`: 10442=10442.0; 10760=10442.0; 11563=11563.0; 512071=11563.0
- `instance`: 10442="DNa01(VES006)_L"; 10760="DNa01(VES006)_R"; 11563="DNae001(DNa01)_R"; 512071="DNae001(DNa01)_L"
- `somaSide`: 10442="L"; 10760="R"; 11563="R"; 512071="L"
- `type`: 10442="DNa01"; 10760="DNa01"; 11563="DNae001"; 512071="DNae001"
- `vfbId`: 10442="VFB_jrmc37ly"; 10760="VFB_jrmc37lx"; 11563="VFB_jrmc37mu"; 512071="VFB_jrmc37mt"
- `hemibrainType`: 10442="VES006"; 10760="VES006"; 11563="DNa01"; 512071="DNa01"
- `mancBodyid`: 10442=10760.0; 10760=10751.0; 11563=13466.0; 512071=12939.0
- `mancGroup`: 10442=10751.0; 10760=10751.0; 11563=12939.0; 512071=12939.0
- `mancType`: 10442="DNa01"; 10760="DNa01"; 11563="DNxl022"; 512071="DNxl022"
- `somaLocation`: 10442=[61859, 18689, 15971]; 10760=[35932, 19030, 15516]; 11563=[34835, 19572, 15809]; 512071=[63133, 18510, 16118]

## Literature connection consistency

| Reported connection | Source | Target | Target type | Present | Contacts | Sign |
|---|---:|---:|---|---|---:|---|
| DNp09 to DNa02 | 10783 | 10360 |  | False | 0 | EXCITATORY |
| DNp09 to DNa02 | 10783 | 523769 |  | True | 45 | EXCITATORY |
| DNp09 to DNb02 | 10783 | 10805 |  | False | 0 | EXCITATORY |
| DNp09 to DNb02 | 10783 | 12767 |  | True | 24 | EXCITATORY |
| DNp09 to DNb02 | 10783 | 13922 |  | False | 0 | EXCITATORY |
| DNp09 to DNb02 | 10783 | 529488 |  | True | 15 | EXCITATORY |
| DNp09 to DNa02 | 11177 | 10360 |  | True | 9 | EXCITATORY |
| DNp09 to DNa02 | 11177 | 523769 |  | False | 0 | EXCITATORY |
| DNp09 to DNb02 | 11177 | 10805 |  | False | 0 | EXCITATORY |
| DNp09 to DNb02 | 11177 | 12767 |  | False | 0 | EXCITATORY |
| DNp09 to DNb02 | 11177 | 13922 |  | True | 2 | EXCITATORY |
| DNp09 to DNb02 | 11177 | 529488 |  | False | 0 | EXCITATORY |
| MDN to DNa01 claimant | 10763 | 10442 | DNa01 | True | 9 | EXCITATORY |
| MDN to DNa01 claimant | 10763 | 10760 | DNa01 | True | 4 | EXCITATORY |
| MDN to DNa01 claimant | 10763 | 11563 | DNae001 | True | 1 | EXCITATORY |
| MDN to DNa01 claimant | 10763 | 512071 | DNae001 | False | 0 | EXCITATORY |
| MDN to DNa01 claimant | 11332 | 10442 | DNa01 | True | 4 | EXCITATORY |
| MDN to DNa01 claimant | 11332 | 10760 | DNa01 | True | 1 | EXCITATORY |
| MDN to DNa01 claimant | 11332 | 11563 | DNae001 | True | 1 | EXCITATORY |
| MDN to DNa01 claimant | 11332 | 512071 | DNae001 | False | 0 | EXCITATORY |
| MDN to DNa01 claimant | 11288 | 10442 | DNa01 | False | 0 | EXCITATORY |
| MDN to DNa01 claimant | 11288 | 10760 | DNa01 | True | 11 | EXCITATORY |
| MDN to DNa01 claimant | 11288 | 11563 | DNae001 | True | 1 | EXCITATORY |
| MDN to DNa01 claimant | 11288 | 512071 | DNae001 | False | 0 | EXCITATORY |
| MDN to DNa01 claimant | 12348 | 10442 | DNa01 | False | 0 | EXCITATORY |
| MDN to DNa01 claimant | 12348 | 10760 | DNa01 | True | 14 | EXCITATORY |
| MDN to DNa01 claimant | 12348 | 11563 | DNae001 | False | 0 | EXCITATORY |
| MDN to DNa01 claimant | 12348 | 512071 | DNae001 | False | 0 | EXCITATORY |
