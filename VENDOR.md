# Vendored controller backend

The hardware-facing backend in `vendor/ugreen_leds_controller` comes from
[`miskcoo/ugreen_leds_controller`](https://github.com/miskcoo/ugreen_leds_controller)
at commit `c10c658cbcd1754e5f1970355eb293f150eb67c8`. The status output has one
small extension: breathing mode reports its on/off timing, which lets temporary
effects restore that mode exactly.

That source is licensed under the MIT License; its original license is retained
at `vendor/ugreen_leds_controller/LICENSE`. Release builds compile the backend
from this pinned source so an upstream change cannot silently alter hardware
access behavior.
