-- Phase 26 stage 2 (Task 7): the Acropolis template's three start figures, every frame from the course load for VR_FIGURES_LOG_FRAMES
-- frames (default 1800, 30 s). The load is start_log.lua's: the first frame the next-mode byte 0x501139 reads 0x11 after the select
-- screen (0x10) has been seen; frames are counted from it (0 = the load), and one L line gives its frame counted from 1.
--   L <load frame> <flag on the select screen's last frame>                           the direction byte (VR_DIRECTION_RAM or 0x502294)
--   P <frame> <x +0x1e> <z +0x26> <yaw +0x6a> <flag>                                  the player (entity 0x400d00) and the byte
-- (Task 8: the flag columns show that direction.lua's 1 reached the byte before the load and that the loader wrote back 0
-- for an entry without a variant; direction.lua is loaded before this file, so on a select frame it has written already.)
--   G <frame> <figure> <flags +0, hex> <character record +0x1ab, hex> <x +0x1e> <z +0x26> <root x +0x17b> <root z +0x193>
--     <heading +0x2c> <walk +0x36>                                                     pool objects 0-2 of [0x501350]
-- (x z floats; yaw signed; heading and walk the halfwords, unsigned. Bit 31 of the flags: the object is live; bit 0x1e: its
-- animation has ended. The root offsets are the animation's translation so far: the figure is drawn at x + root x, z + root z,
-- 0xff5df4, and they are added to x, z when the animation ends, 0xff6a14.) No G lines while the pool pointer is 0. Loaded by
-- autoplay.lua when VR_FIGURES_LOG (path) is set.
local out_path = os.getenv("VR_FIGURES_LOG")
if out_path then
  local out = assert(io.open(out_path, "w"))
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local span = tonumber(os.getenv("VR_FIGURES_LOG_FRAMES") or "1800")
  local flag_at = tonumber(os.getenv("VR_DIRECTION_RAM") or "502294", 16)
  local frame, select_seen, load, select_flag = 0, false, nil, -1
  local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
  local function s16(a) local v = mem:read_u16(a); return v >= 0x8000 and v - 0x10000 or v end
  emu.register_frame_done(function()
    frame = frame + 1
    local mode = mem:read_u8(0x501139)
    if not load then
      if mode == 0x10 then select_seen, select_flag = true, mem:read_u8(flag_at) end
      if not (select_seen and mode == 0x11) then return end
      load = frame
      out:write(string.format("L %d %d\n", load, select_flag))
    end
    local t, b = frame - load, 0x400d00
    if t > span then return end
    out:write(string.format("P %d %.4f %.4f %d %d\n", t, f32(b + 0x1e), f32(b + 0x26), s16(b + 0x6a), mem:read_u8(flag_at)))
    local pool = mem:read_u32(0x501350)
    if pool ~= 0 then
      for i = 0, 2 do
        local e = pool + 0x280 * i
        out:write(string.format("G %d %d %08x %08x %.4f %.4f %.4f %.4f %d %d\n", t, i, mem:read_u32(e), mem:read_u32(e + 0x1ab),
          f32(e + 0x1e), f32(e + 0x26), f32(e + 0x17b), f32(e + 0x193), mem:read_u16(e + 0x2c), mem:read_u16(e + 0x36)))
      end
    end
    if t % 20 == 0 or t == span then out:flush() end
  end)
end
