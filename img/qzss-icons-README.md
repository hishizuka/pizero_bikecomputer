# QZSS popup icons

`qzss_earthquake.png` and `qzss_tsunami.png` are unmodified image assets
from the Android Open Source Project (AOSP), CellBroadcastReceiver.
Retrieved on 2026-09-08 from `refs/heads/main`:

- [pict_icon_earthquake.png](https://android.googlesource.com/platform/packages/apps/CellBroadcastReceiver/+/refs/heads/main/res/drawable/pict_icon_earthquake.png)
  Git blob: `96cc90df52974394f665682b991ab5e5efffc7d5`
- [pict_icon_tsunami.png](https://android.googlesource.com/platform/packages/apps/CellBroadcastReceiver/+/refs/heads/main/res/drawable/pict_icon_tsunami.png)
  Git blob: `40e73d1f1fdce456b12999ddef232be0dc569121`

The package's [Android.bp](https://android.googlesource.com/platform/packages/apps/CellBroadcastReceiver/+/refs/heads/main/Android.bp)
declares `Android-Apache-2.0` as its default applicable license and carries
the notice `Copyright 2011 The Android Open Source Project`.
See [qzss-icons-LICENSE.txt](qzss-icons-LICENSE.txt) for the license text.
Images are scaled at display time and their yellow pixels are mapped to the
display yellow (#FFFF00). These runtime transformations do not modify the
distributed source files.

The artwork visually matches the earthquake and tsunami pictograms shown
on NTT DOCOMO's [Area Mail page](https://www.docomo.ne.jp/service/areamail/index.html).
This establishes an AOSP source for the artwork, but does not establish its
original designer or the exact software/assets shipped on any specific Pixel.

`warning.svg` is original project artwork: a yellow triangle with a red
exclamation mark. It uses the project's license.
