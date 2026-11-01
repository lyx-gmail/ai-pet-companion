# FluxGarage RoboEyes

Source: https://github.com/FluxGarage/RoboEyes

Commit: `b42f8e596535234932be3514ac7a813d4ced0046`

File: `src/FluxGarage_RoboEyes.h`, with one local initialization-order fix:
`spaceBetweenDefault` is declared before the coordinate members that read it.
Motion and drawing algorithms are unchanged. ESP-IDF exposed the original
uninitialized read; no compiler warning was suppressed.

Original upstream SHA-256: `04e098193efbf6656085429b85a20d40c1d56c1837e7ef500779f6557645a4d8`

Copyright (C) 2024–2025 Dennis Hoelscher. GPL-3.0-or-later; complete original license is in `LICENSE.txt`.

The project supplies a separate LVGL draw adapter; it does not claim the eye movement algorithms as original work. Distribute the linked firmware module and corresponding source under the applicable GPL terms. Backend memory code remains a separate process.
