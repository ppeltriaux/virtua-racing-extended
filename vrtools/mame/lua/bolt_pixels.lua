-- Weather, the lightning's bolt visibility (task 8; tests/test_weather_lightning.py's test_the_bolt_shows_on_metropolis): on a set
-- built with lightning.module(..., measure="key" or "twin") the bolt is drawn in one key colour (the polygon palette's entry nearest
-- magenta); this counts the screen's key-coloured pixels on every frame of every strike (the lightning's phase not idle) and the six
-- frames after it. One line a frame:
--   P <frame> <strike_seq> <phase> <level> <key pixels> <misaligned matches (ignored)>
-- A key pixel: the bytes B G R of a 32-bit pixel (MAME's screen:pixels(), little-endian ARGB) with B and R at least 160 and G at
-- most 96, found aligned on a pixel. frame counts MAME frames from 1 at the first frame end. Env: VR_PIX_LOG (path), VR_PIX_STATE
-- (the lightning's state cell, hex: PHASE is its third word, LEVEL its fifteenth), VR_PIX_SEQ (strike_seq's cell, hex). Loaded by
-- autoplay.lua through VR_EXTRA_LUA.
local path = os.getenv("VR_PIX_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local prog = manager.machine.devices[":maincpu"].spaces["program"]
  local st = tonumber(os.getenv("VR_PIX_STATE") or "", 16)
  local seqa = tonumber(os.getenv("VR_PIX_SEQ") or "", 16)
  if not (st and seqa) then error("bolt_pixels.lua: VR_PIX_STATE / VR_PIX_SEQ") end
  local scr = manager.machine.screens[":screen"]
  local tail, frame = 0, 0
  emu.register_frame_done(function()
    frame = frame + 1
    local phase = prog:read_u32(st + 8)
    if phase ~= 0 then tail = 6 elseif tail > 0 then tail = tail - 1 end
    if tail > 0 then
      local s = scr:pixels()
      local n1, n2 = 0, 0
      for p in s:gmatch("()[\160-\255][\0-\96][\160-\255]") do
        local r = p % 4
        if r == 1 then n1 = n1 + 1 elseif r == 2 then n2 = n2 + 1 end
      end
      out:write(string.format("P %d %d %d %d %d %d\n", frame, prog:read_u32(seqa), phase, prog:read_u32(st + 56), n1, n2))
      out:flush()
    end
  end)
end
