-- Phase 32: the whole tile RAM (0x700000-0x70ffff: the four tile layers, their scroll words and window masks) at given frames
-- after the race load, for comparing two sets' screens cell for cell. Loaded by autoplay.lua when VR_TILE_DUMP_DIR is set.
-- Env: VR_TILE_DUMP_DIR (a directory), VR_TILE_DUMP_AT ("8,60,300": frames after the first frame end the mode byte 0x501138
-- reads 0x11). Writes <dir>/tile_<n>.bin (0x10000 bytes, each word low byte first) and a line "<n> <frame>" to <dir>/frames.txt
-- (frame counted from 1 at the first frame end, as autoplay.lua counts).
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local dir = os.getenv("VR_TILE_DUMP_DIR")
local at = {}
for f in string.gmatch(os.getenv("VR_TILE_DUMP_AT") or "", "%d+") do at[tonumber(f)] = true end
local frame, load = 0, nil
emu.register_frame_done(function()
  frame = frame + 1
  if not load and mem:read_u8(0x501138) == 0x11 then load = frame end
  if load and at[frame - load] then
    local t = {}
    for a = 0x700000, 0x70fffe, 2 do local w = mem:read_u16(a); t[#t + 1] = string.char(w & 0xff, w >> 8) end
    local f = assert(io.open(string.format("%s/tile_%05d.bin", dir, frame - load), "wb")); f:write(table.concat(t)); f:close()
    local g = assert(io.open(dir .. "/frames.txt", "a")); g:write(string.format("%d %d\n", frame - load, frame)); g:close()
  end
end)
