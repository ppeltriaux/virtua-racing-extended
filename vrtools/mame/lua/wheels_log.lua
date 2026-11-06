-- Phase 15 recon: the player's four wheel heights. Every VR_WHEELS_EVERY frames (default 10) from VR_WHEELS_FROM (default 1700):
--   W <frame> <y> <h132> <h136> <h13a> <h13e> <r60> <r64> <r68> <r6c> <k142> <k144> <k146> <k148> <pitch> <roll>
-- (the player entity 0x400d00: y +0x22, the per-wheel TGP answers +0x132..+0x13e, the heights 0x501260..0x50126c the attitude
-- code reads, the wheel kinds +0x142..+0x148 in hex, +0x2e, +0x2a); and the first 20 writers of 0x501260..0x50126f after
-- VR_WHEELS_FROM as "P <frame> <pc> <address> <data>". Env: VR_WHEELS_LOG (path).
local out_path = os.getenv("VR_WHEELS_LOG")
if out_path then
  local out = assert(io.open(out_path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local mem = cpu.spaces["program"]
  local from, every = tonumber(os.getenv("VR_WHEELS_FROM") or "1700"), tonumber(os.getenv("VR_WHEELS_EVERY") or "10")
  local base, frame, writes = 0x400d00, 0, 0
  local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
  local function s16(a) local v = mem:read_u16(a); return v >= 0x8000 and v - 0x10000 or v end
  _G.vr_wheels_tap = mem:install_write_tap(0x501260, 0x50126f, "wheels", function(offset, data, mask)
    if frame >= from and writes < 20 then
      writes = writes + 1
      out:write(string.format("P %d %x %x %08x\n", frame, cpu.state["PC"].value, offset, data)); out:flush()
    end
  end)
  emu.register_frame_done(function()
    frame = frame + 1
    if frame < from or frame % every ~= 0 then return end
    out:write(string.format("W %d %.2f %.2f %.2f %.2f %.2f %.2f %.2f %.2f %.2f %x %x %x %x %d %d\n", frame, f32(base + 0x22),
      f32(base + 0x132), f32(base + 0x136), f32(base + 0x13a), f32(base + 0x13e), f32(0x501260), f32(0x501264), f32(0x501268), f32(0x50126c),
      mem:read_u16(base + 0x142), mem:read_u16(base + 0x144), mem:read_u16(base + 0x146), mem:read_u16(base + 0x148), s16(base + 0x2e), s16(base + 0x2a)))
    out:flush()
  end)
end
