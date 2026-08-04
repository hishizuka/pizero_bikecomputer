# QZSS area lookup data

`qzss_japan_area.csv` is a compact runtime lookup table for coarse popup
relevance filtering. It maps QZSS/JMA prefecture codes and labels to a
representative coordinate and a deliberately conservative radius.

The table is not an administrative boundary dataset and must not be used to
decide whether a position is legally inside an alert area. Runtime evaluation
adds a configurable margin and suppresses a popup only when every decoded
target is resolved and all target circles are far from the current position.
Unknown targets therefore fail open.

The coordinates are prefectural-government representative points. Radii are
coarse enclosing values chosen for notification filtering, including remote
islands where practical. More detailed JMA code namespaces can be added as
additional rows without changing the runtime algorithm.
