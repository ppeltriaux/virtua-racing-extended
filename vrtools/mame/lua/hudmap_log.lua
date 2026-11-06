-- Phase 14: at race start + 300 frames, write the HUD map section's screen translate and the tile cells where the player's
-- cross is drawn (the game's columns 48..50 and the shifted 59..61, rows 21..23 of tile page 0) to VR_HUDMAP_LOG:
--   T <tx> <ty>
--   R <map_tx> <map_cross> <off_course>                 (RAM 0x50231c, 0x502328, 0x50232c: what the course loader wrote)
--   H <row> <c48> <c49> <c50> <c59> <c60> <c61>      (three rows, cell words in hex)
local out_path = os.getenv("VR_HUDMAP_LOG")
if out_path then
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local frame, done = 0, false
  local function f32(u) return (string.unpack("<f", string.pack("<I4", u))) end
  emu.register_frame_done(function()
    frame = frame + 1
    local rs = (type(_G.vr_race_start) == "function") and _G.vr_race_start() or nil
    if done or not rs or frame < rs + 300 then return end
    done = true
    local out = assert(io.open(out_path, "w"))
    local active = (mem:read_u16(0x680000) & 0x40) ~= 0 and 0x610000 or 0x600000      -- as dlist_log.lua picks the list
    out:write(string.format("T %.3f %.3f\n", f32(mem:read_u32(active + 0x48)), f32(mem:read_u32(active + 0x4c))))
    -- the per-course words the loader wrote: the map translate, the cross tile offset, the off-course limit
    out:write(string.format("R %.3f %d %d\n", f32(mem:read_u32(0x50231c)), mem:read_u32(0x502328), mem:read_u32(0x50232c)))
    for row = 21, 23 do
      local cells = {}
      for _, col in ipairs({48, 49, 50, 59, 60, 61}) do
        cells[#cells + 1] = string.format("%04x", mem:read_u16(0x700000 + (row * 64 + col) * 2))
      end
      out:write(string.format("H %d %s\n", row, table.concat(cells, " ")))
    end
    out:close()
  end)
end
