#!/bin/sh
# Builds the website's Steam Deck images: Valve's Steam Deck (LCD) front render from the official
# press kit (https://www.steamdeck.com/en/press), with DeckPad screenshots on its display.
# Needs curl and ImageMagick 7. Run from the repository root: sh docs/site-art/make-deck-images.sh
set -eu

out=site
shots=docs/screenshots
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -sSfL https://cdn.fastly.steamstatic.com/steamdeck/images/press/renderings/rendering07.png \
  -o "$work/render.png"

# Crop wide enough to keep the soft shadow, then feather the edges so no crop line shows.
magick "$work/render.png" -crop 2563x1331+318+330 +repage "$work/deck.png"
magick -size 2563x1331 xc:white -shave 90x90 -bordercolor black -border 90 -blur 0x45 "$work/feather.png"
magick "$work/deck.png" \( +clone -alpha extract "$work/feather.png" -compose multiply -composite \) \
  -alpha off -compose copy_opacity -composite "$work/deck.png"

# The display in the cropped render, measured from its pixels: 1182x739 at +691+200 (16:10).
screen_geometry=1182x739!
screen_offset=+691+200

# Screenshots are 1280x680: Steam's 1280x800 screen without its top bar and footer.
# Controller Screen: extend its own edges to fill the full screen height.
magick "$shots/controller-screen.png" -virtual-pixel edge \
  -set option:distort:viewport 1280x800+0-60 -distort SRT 0 +repage "$work/screen-controller.png"

# Quick Access: the panel on the right over a dimmed backdrop, as Steam shows it. The screenshot
# cuts a heading off at the bottom, so fade the panel column (right of the 72px tab rail) out early.
magick "$shots/qam-connected.png" \
  \( -size 449x45 gradient:'rgba(14,20,27,0)-#0E141B' -size 449x35 xc:'#0E141B' -append \) \
  -gravity southeast -composite \
  -background '#0E141B' -gravity north -splice 0x60 -extent 521x800 "$work/panel.png"
magick -size 1280x800 radial-gradient:'#1c2633-#080b0f' \
  "$work/panel.png" -gravity east -composite "$work/screen-qam.png"

for name in controller qam; do
  magick "$work/deck.png" \( "$work/screen-$name.png" -resize "$screen_geometry" \) \
    -gravity northwest -geometry "$screen_offset" -composite \
    -resize 2000x -quality 86 -define webp:alpha-quality=90 "$work/deck-$name.webp"
done

mv "$work/deck-controller.webp" "$out/deck-controller-screen.webp"
mv "$work/deck-qam.webp" "$out/deck-quick-access.webp"
