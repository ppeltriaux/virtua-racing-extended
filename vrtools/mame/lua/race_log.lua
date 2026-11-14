-- Phase 26: the race's own record, from VR_RACE_LOG_FROM (default 1400), one line per frame for the player (car 0, entity 0x400d00):
--   P <frame> <x> <z> <yaw +0x6a> <heading +0x36> <attr +0xeb> <road point +0xa6> <lap +0x1b5> <checkpoints +0x57> <clock 0x50116c> <off-course 0x50115c>
-- (x z floats; yaw, heading, road point and lap signed; the attribute the halfword at +0xeb..+0xec, unsigned; the clock 1/32 s;
-- frames count from 1 at the first frame end, fieldtrace.lua's samples from 0), and one J line when the smoke counter (+0x1aa) of an
-- opponent (car 1..15) rises from 0:  J <frame> <car> <road point> <x> <z>. Env: VR_RACE_LOG (path), VR_RACE_LOG_FROM.
-- Phase 26 stage 2 (after the owner's drive): with VR_RACE_CARS_TO, also one O line per opponent per frame before that frame
-- (the standing grid and the start):  O <frame> <car> <road point +0xa6> <x> <z> <yaw +0x36, signed 1/65536 turn> <speed +0x14 u32>.
local out_path = os.getenv("VR_RACE_LOG")
if out_path then
  local out = assert(io.open(out_path, "w"))
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local from = tonumber(os.getenv("VR_RACE_LOG_FROM") or "1400")
  local cars_to = tonumber(os.getenv("VR_RACE_CARS_TO") or "0")
  local frame, smoke = 0, {}
  local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
  local function s16(a) local v = mem:read_u16(a); return v >= 0x8000 and v - 0x10000 or v end
  local function s8(a) local v = mem:read_u8(a); return v >= 0x80 and v - 0x100 or v end
  emu.register_frame_done(function()
    frame = frame + 1
    for car = 1, 15 do
      local b = 0x400d00 + 0x280 * car
      local s = mem:read_u8(b + 0x1aa)
      if frame >= from and s > 0 and (smoke[car] or 0) == 0 then
        out:write(string.format("J %d %d %d %.4f %.4f\n", frame, car, s16(b + 0xa6), f32(b + 0x1e), f32(b + 0x26)))
      end
      smoke[car] = s
      if frame >= from and frame < cars_to then
        out:write(string.format("O %d %d %d %.4f %.4f %d %d\n", frame, car, s16(b + 0xa6), f32(b + 0x1e), f32(b + 0x26), s16(b + 0x36),
          mem:read_u32(b + 0x14)))
      end
    end
    if frame >= from then
      local b = 0x400d00
      out:write(string.format("P %d %.4f %.4f %d %d %d %d %d %d %d %d\n", frame, f32(b + 0x1e), f32(b + 0x26), s16(b + 0x6a), s16(b + 0x36),
        mem:read_u8(b + 0xeb) | (mem:read_u8(b + 0xec) << 8), s16(b + 0xa6), s8(b + 0x1b5), mem:read_u8(b + 0x57), mem:read_i32(0x50116c), mem:read_u32(0x50115c)))
      if frame % 20 == 0 then out:flush() end
    end
  end)
end
