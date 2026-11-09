-- Attract mode, no input: log the ranking page's state whenever it changes (every 10 frames), and optionally poke
-- the attract group counters once. VR_RANKING_LOG = output; VR_POKE_COUNTERS="1,1,1" written at VR_POKE_FRAME (600).
-- Line: "<frame> <data index> <shown id> <table base hex> <62 title-row tile words hex>"
local out = assert(io.open(os.getenv("VR_RANKING_LOG"), "w"))
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local poke = os.getenv("VR_POKE_COUNTERS")
local poke_frame = tonumber(os.getenv("VR_POKE_FRAME") or "600")
local frame, last = 0, ""
emu.register_frame_done(function()
  frame = frame + 1
  if poke and frame == poke_frame then
    local k = 0
    for v in string.gmatch(poke, "%d+") do mem:write_u8(0x40FC6A + k, tonumber(v)); k = k + 1 end
  end
  if frame % 10 ~= 0 then return end
  local row = {}
  for c = 0, 61 do row[#row + 1] = string.format("%04x", mem:read_u16(0x700200 + 2 * c)) end
  local s = string.format("%d %d %08x %s", mem:read_u8(0x501934), mem:read_u8(0x40FC69), mem:read_u32(0x5018F0), table.concat(row))
  if s ~= last then out:write(frame .. " " .. s .. "\n"); out:flush(); last = s end
end)
