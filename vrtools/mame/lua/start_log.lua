-- Phase 26 stage 2 (Task 5): the race start, every frame from the course load to the end of the run. The load is the first frame
-- the next-mode byte 0x501139 reads 0x11 after the select screen (0x10) has been seen; frames are counted from it (0 = the load),
-- and one L line gives its frame counted from 1 at the first frame end (race_log.lua's count; memtrace.lua's frame f is this f + 1).
--   L <load frame>
--   S <frame> <mode 0x501139, hex> <clock 0x50116c> <flag VR_DIRECTION_RAM or 0x502294> <pit state +0x191> <x +0x1e> <z +0x26>
--     <yaw +0x6a> <attr +0xeb> <road point +0xa6> <lap +0x1b5>                          the player (car 0, entity 0x400d00)
--   O <frame> <car> <road point +0xa6> <lap +0x1b5> <x> <z>                             each opponent (car 1..15)
-- (x z floats; yaw, road point and lap signed; the attribute the halfword at +0xeb..+0xec, unsigned.) Loaded by autoplay.lua when
-- VR_START_LOG (path) is set.
local out_path = os.getenv("VR_START_LOG")
if out_path then
  local out = assert(io.open(out_path, "w"))
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local flag_at = tonumber(os.getenv("VR_DIRECTION_RAM") or "502294", 16)
  local frame, select_seen, load = 0, false, nil
  local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
  local function s16(a) local v = mem:read_u16(a); return v >= 0x8000 and v - 0x10000 or v end
  local function s8(a) local v = mem:read_u8(a); return v >= 0x80 and v - 0x100 or v end
  emu.register_frame_done(function()
    frame = frame + 1
    local mode = mem:read_u8(0x501139)
    if not load then
      if mode == 0x10 then select_seen = true end
      if not (select_seen and mode == 0x11) then return end
      load = frame
      out:write(string.format("L %d\n", load))
    end
    local t, b = frame - load, 0x400d00
    out:write(string.format("S %d %02x %d %d %d %.4f %.4f %d %d %d %d\n", t, mode, mem:read_i32(0x50116c), mem:read_u8(flag_at),
      mem:read_u8(b + 0x191), f32(b + 0x1e), f32(b + 0x26), s16(b + 0x6a), mem:read_u8(b + 0xeb) | (mem:read_u8(b + 0xec) << 8),
      s16(b + 0xa6), s8(b + 0x1b5)))
    for car = 1, 15 do
      local c = 0x400d00 + 0x280 * car
      out:write(string.format("O %d %d %d %d %.4f %.4f\n", t, car, s16(c + 0xa6), s8(c + 0x1b5), f32(c + 0x1e), f32(c + 0x26)))
    end
    if t % 20 == 0 then out:flush() end
  end)
end
