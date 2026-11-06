-- Phase 15: every VR_ATTITUDE_EVERY frames (default 10) from VR_ATTITUDE_FROM (default 1700), for cars 0..VR_ATTITUDE_CARS-1
-- (default 4; entity 0x400d00 + 0x280 i):
--   A <frame> <car> <x> <y> <z> <pitch +0x2a> <roll +0x2e> <disp pitch +0x4c> <yaw +0x4e> <disp roll +0x50> <yaw raw +0x6a>
-- (+0x2a is the pitch, positive climbing; +0x2e the roll, negative right side up: Phase 16 recon §1)
-- (angles signed, 1/65536 turn). Env: VR_ATTITUDE_LOG (path).
local out_path = os.getenv("VR_ATTITUDE_LOG")
if out_path then
  local out = assert(io.open(out_path, "w"))
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local from, every = tonumber(os.getenv("VR_ATTITUDE_FROM") or "1700"), tonumber(os.getenv("VR_ATTITUDE_EVERY") or "10")
  local cars = tonumber(os.getenv("VR_ATTITUDE_CARS") or "4")
  local frame = 0
  local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
  local function s16(a) local v = mem:read_u16(a); return v >= 0x8000 and v - 0x10000 or v end
  emu.register_frame_done(function()
    frame = frame + 1
    if frame < from or frame % every ~= 0 then return end
    for car = 0, cars - 1 do
      local b = 0x400d00 + 0x280 * car
      local wheels = ""
      if os.getenv("VR_ATTITUDE_WHEELS") then          -- Phase 22a: the per-wheel surface kinds (1 << kind; wall 0x20)
        wheels = string.format(" W %x %x %x %x R %d %d %d %d %d %d %d", mem:read_u16(b + 0x142), mem:read_u16(b + 0x144), mem:read_u16(b + 0x146), mem:read_u16(b + 0x148),
          s16(b + 0x12b), mem:read_u8(b + 0x124), mem:read_u8(b + 0x56), mem:read_u8(b + 0x1aa), mem:read_u8(b + 0x1ba), s16(b + 0x36), mem:read_u32(b + 0x14))
        -- Phase 22m: the car's road point (+0xa6), its line cursor (+0xe1, 16 per point) and target (+0x1b1): the band's run-on
        wheels = wheels .. string.format(" C %d %d %d", mem:read_u16(b + 0xa6), mem:read_u16(b + 0xe1) // 16, mem:read_u8(b + 0x1b1))
        if car == 0 then                                 -- Phase 22m: the race clock (1/32 s) and the player's checkpoint counter (+0x57)
          wheels = wheels .. string.format(" K %d %d", mem:read_i32(0x50116c), mem:read_u8(b + 0x57))
        end
        if car == 0 then                                 -- the player's four wheel heights (FL FR RL RR), compared at 0xfebe46
          wheels = wheels .. string.format(" H %.2f %.2f %.2f %.2f", f32(0x501264), f32(0x501260), f32(0x50126c), f32(0x501268))
          local function u32b(a) return mem:read_u8(a) | (mem:read_u8(a + 1) << 8) | (mem:read_u8(a + 2) << 16) | (mem:read_u8(a + 3) << 24) end
          wheels = wheels .. string.format(" Q %x %x %x %x %x", u32b(b + 0x17f), u32b(b + 0x183), u32b(b + 0x187), u32b(b + 0x18b), u32b(b + 0x17b))
          wheels = wheels .. string.format(" O %d %d", mem:read_u32(0x50115c), mem:read_u32(0x50232c))   -- off-course counter, limit
        end
      end
      out:write(string.format("A %d %d %.1f %.2f %.1f %d %d %d %d %d %d%s\n", frame, car, f32(b + 0x1e), f32(b + 0x22), f32(b + 0x26),
        s16(b + 0x2a), s16(b + 0x2e), s16(b + 0x4c), s16(b + 0x4e), s16(b + 0x50), s16(b + 0x6a), wheels))
    end
    out:flush()
  end)
end
