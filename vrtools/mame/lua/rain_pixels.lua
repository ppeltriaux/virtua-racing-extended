-- v0.4.1's streaming rain: the picture's key-coloured pixels and its mean relative luminance at each video frame's end while the
-- game is in the race (mode 0x501138 = 0x14), for tests/test_weather_streaming.py (the fill at speed, the band shares, the lit
-- streaks' share) and tests/test_weather_lightning.py (the flash rule read from the picture itself):
--   P <frame> <km/h> <magenta top> <magenta middle> <magenta bottom> <cyan> <yellow> <mean relative luminance x 10000>
-- The key colours (the test sets draw the rain's streaks in them): magenta R and B over 159, G under 97; cyan G and B over 159, R
-- under 97; yellow R and G over 159, B under 97; magenta counted in the picture's three horizontal thirds. The luminance: the
-- sRGB-linearised 0.2126 R + 0.7152 G + 0.0722 B (WCAG's relative luminance) over every 8th pixel, 0..10000.
-- VR_RPIX_LOG: the log. VR_RPIX_KEYS=0: the luminance only (the key counts written as 0).
local out = assert(io.open(os.getenv("VR_RPIX_LOG"), "w"))
local prog = manager.machine.devices[":maincpu"].spaces["program"]
local scr = manager.machine.screens[":screen"]
local keys = os.getenv("VR_RPIX_KEYS") ~= "0"
local lin = {}
for v = 0, 255 do
  local c = v / 255
  lin[v] = (c <= 0.04045) and (c / 12.92) or (((c + 0.055) / 1.055) ^ 2.4)
end
local MAGENTA, CYAN, YELLOW = "()[\160-\255][\0-\96][\160-\255]", "()[\160-\255][\160-\255][\0-\96]", "()[\0-\96][\160-\255][\160-\255]"
local fr = 0
emu.register_frame_done(function()
  fr = fr + 1
  if prog:read_u8(0x501138) ~= 0x14 then return end
  local s, w, h = scr:pixels()
  w = w or 496; h = h or 384
  local m = {0, 0, 0}
  local cy, ye = 0, 0
  if keys then
    for p in s:gmatch(MAGENTA) do                   -- bytes B G R A a pixel: a match counts only at a pixel's first byte
      if p % 4 == 1 then
        local y = ((p - 1) // 4) // w
        local k = y * 3 // h + 1
        m[k] = m[k] + 1
      end
    end
    for p in s:gmatch(CYAN) do if p % 4 == 1 then cy = cy + 1 end end
    for p in s:gmatch(YELLOW) do if p % 4 == 1 then ye = ye + 1 end end
  end
  local sum, n = 0, 0
  for i = 1, #s - 3, 32 do
    local b, g, r = string.byte(s, i, i + 2)
    sum = sum + 0.2126 * lin[r] + 0.7152 * lin[g] + 0.0722 * lin[b]
    n = n + 1
  end
  out:write(string.format("P %d %d %d %d %d %d %d %d\n", fr, prog:read_u32(0x400D14), m[1], m[2], m[3], cy, ye,
    math.floor(10000 * sum / math.max(n, 1) + 0.5)))
  if fr % 100 == 0 then out:flush() end
end)
