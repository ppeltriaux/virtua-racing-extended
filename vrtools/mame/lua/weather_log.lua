-- Weather stage 1: the select screens' palettes, frame by frame. At every frame end at which one of the palettes VR_WX_PALS names
-- (hex palette numbers, comma-separated; palette p's 16 words at 0x900000 + 32 p) differs from its last line, one line:
--   P <frame> <palette hex> <16 words hex>
-- between frames VR_WX_FROM and VR_WX_TO (inclusive; frames counted from 1 at the first frame end, as autoplay.lua counts them).
-- Loaded with VR_EXTRA_LUA alongside autoplay.lua (with dirscreen_log.lua for the screens' state). Env: VR_WX_LOG (path).
local out = assert(io.open(assert(os.getenv("VR_WX_LOG"), "weather_log.lua: VR_WX_LOG is not set"), "w"))
local from, to = tonumber(os.getenv("VR_WX_FROM") or "0"), tonumber(os.getenv("VR_WX_TO") or "999999")
local pals = {}
for p in string.gmatch(os.getenv("VR_WX_PALS") or "", "%x+") do pals[#pals + 1] = tonumber(p, 16) end
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, last = 0, {}
emu.register_frame_done(function()
  frame = frame + 1
  if frame < from or frame > to then return end
  for _, p in ipairs(pals) do
    local w = {}
    for k = 0, 15 do w[#w + 1] = string.format("%x", mem:read_u16(0x900000 + 32 * p + 2 * k)) end
    local s = table.concat(w, " ")
    if s ~= last[p] then out:write(string.format("P %d %x %s\n", frame, p, s)); last[p] = s end
  end
  out:flush()
end)
