-- Per-frame opponent trace: for every car entity (0x400d00 + 0x280 i) its road point (+0xa6), lap (+0x1b5), line
-- cursor (+0xe1, bytes), target (+0x1b1), working performance (+0x48, f32), x/z (+0x1e/+0x26) and lap-position quad
-- (+0x30), its rank (+0x123) and its ranking neighbours (+0x198 behind, +0x19c ahead, as car indices). Env: VR_FIELD_LOG (path), VR_FIELD_FROM / VR_FIELD_TO (frame window), VR_FIELD_EVERY (frames, default 5).
local path = os.getenv("VR_FIELD_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local from = tonumber(os.getenv("VR_FIELD_FROM") or "1500")
  local to = tonumber(os.getenv("VR_FIELD_TO") or "3000")
  local every = tonumber(os.getenv("VR_FIELD_EVERY") or "5")
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local frame = 0
  local function s16(v) if v >= 0x8000 then return v - 0x10000 end return v end
  local function f32(a) local u = mem:read_u32(a); return string.unpack("<f", string.pack("<I4", u)) end
  emu.register_frame_done(function()
    if frame >= from and frame < to and frame % every == 0 then
      for car = 0, 15 do
        local b = 0x400d00 + 0x280 * car
        local behind, ahead = mem:read_u32(b + 0x198), mem:read_u32(b + 0x19c)   -- ranking neighbours (entities)
        out:write(string.format("%d %d %d %d %d %d %d %.2f %.1f %.1f %d %d %d\n", frame, car, s16(mem:read_u16(b + 0xa6)),
          s16(mem:read_u8(b + 0x1b5) >= 128 and mem:read_u8(b + 0x1b5) - 256 or mem:read_u8(b + 0x1b5)),
          s16(mem:read_u16(b + 0xe1)), s16(mem:read_u16(b + 0x1b1)), mem:read_u16(b + 0x30), f32(b + 0x48), f32(b + 0x1e), f32(b + 0x26),
          mem:read_u8(b + 0x123), (behind - 0x400d00) // 0x280, (ahead - 0x400d00) // 0x280))
      end
      out:flush()
    end
    frame = frame + 1
  end)
end
